import threading
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from math import ceil
from typing import Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request

from .config import settings
from .db import connection

Role = Literal["admin", "tecnico", "cliente"]
password_hasher = PasswordHasher()
DUMMY_PASSWORD_HASH = password_hasher.hash("not-a-real-password-for-timing-only")


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def validate_new_password(username: str, password: str) -> None:
    if len(password) < 8:
        raise ValueError("A nova senha deve ter pelo menos 8 caracteres.")
    if password.casefold() == username.casefold():
        raise ValueError("A nova senha deve ser diferente do usuário.")
    if password.casefold() in {"123", "12345678", "password"}:
        raise ValueError("Escolha uma senha menos comum.")


def create_access_token(user: dict) -> str:
    cfg = settings()
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user["id"]),
            "username": user["username"],
            "role": user["role"],
            "ver": int(user.get("token_version", 0)),
            "iat": now,
            "exp": now + timedelta(minutes=cfg.auth_session_minutes),
        },
        cfg.auth_jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


def create_customer_token(user_id: str) -> str:
    cfg = settings()
    now = datetime.now(timezone.utc)
    with connection() as conn:
        owner = conn.execute(
            "SELECT u.id,u.token_version FROM users u JOIN customers c ON c.id=u.customer_id "
            "WHERE c.id=%s AND u.role='cliente' AND u.is_active=true",
            (user_id,),
        ).fetchone()
    return jwt.encode(
        {
            "sub": user_id,
            "kind": "customer",
            "uid": owner["id"] if owner else None,
            "ver": owner["token_version"] if owner else 0,
            "iat": now,
            "exp": now + timedelta(minutes=cfg.auth_session_minutes),
        },
        cfg.auth_jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


def decode_customer_token(token: str | None) -> str | None:
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings().auth_jwt_secret.get_secret_value(), algorithms=["HS256"])
        if payload.get("kind") != "customer":
            return None
        with connection() as conn:
            owner = conn.execute(
                "SELECT token_version,is_active FROM users WHERE id=%s AND role='cliente'",
                (payload.get("uid"),),
            ).fetchone()
        if not owner or not owner["is_active"] or int(payload.get("ver", -1)) != owner["token_version"]:
            return None
        return str(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        return None


def user_from_token(token: str | None) -> dict | None:
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings().auth_jwt_secret.get_secret_value(), algorithms=["HS256"])
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        return None
    with connection() as conn:
        user = conn.execute(
            "SELECT id,username,role,display_name,is_active,customer_id,must_change_password,token_version "
            "FROM users WHERE id=%s",
            (user_id,),
        ).fetchone()
    if not user or not user["is_active"] or int(payload.get("ver", 0)) != user["token_version"]:
        return None
    return user


def current_user(request: Request) -> dict:
    token = request.cookies.get(settings().auth_cookie_name)
    user = user_from_token(token)
    if not user:
        raise HTTPException(401, "Autenticação necessária ou sessão expirada.")
    if user["must_change_password"] and request.url.path not in {
        "/api/auth/me",
        "/api/auth/change-password",
        "/api/auth/logout",
    }:
        raise HTTPException(403, "Troca de senha obrigatória antes de continuar.")
    return user


def require_role(*roles: Role) -> Callable:
    def dependency(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(403, "Permissão insuficiente.")
        return user

    return dependency


class LoginRateLimiter:
    def __init__(self, max_failures: int, window_seconds: int, lock_seconds: int):
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self.lock_seconds = lock_seconds
        self.failures: dict[str, deque[float]] = defaultdict(deque)
        self.locked_until: dict[str, float] = {}
        self.lockouts: dict[str, int] = defaultdict(int)
        self.lock = threading.Lock()

    def check(self, key: str, now: float) -> int:
        with self.lock:
            remaining = int(self.locked_until.get(key, 0) - now)
            if remaining > 0:
                return remaining
            self.locked_until.pop(key, None)
            return 0

    def failure(self, key: str, now: float) -> int:
        with self.lock:
            attempts = self.failures[key]
            while attempts and attempts[0] <= now - self.window_seconds:
                attempts.popleft()
            attempts.append(now)
            if len(attempts) >= self.max_failures:
                self.lockouts[key] += 1
                duration = min(self.lock_seconds * (2 ** (self.lockouts[key] - 1)), self.lock_seconds * 8)
                self.locked_until[key] = now + duration
                attempts.clear()
                return duration
            return 0

    def success(self, key: str) -> None:
        with self.lock:
            self.failures.pop(key, None)
            self.locked_until.pop(key, None)
            self.lockouts.pop(key, None)


class DatabaseLoginRateLimiter:
    """Atomic login limits shared by every API process using the same database."""

    def __init__(self, max_failures: int, window_seconds: int, lock_seconds: int):
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self.lock_seconds = lock_seconds

    @staticmethod
    def _key(key: str) -> str:
        return sha256(key.encode("utf-8")).hexdigest()

    def check(self, key: str, _now: float) -> int:
        with connection() as conn:
            row = conn.execute(
                "SELECT locked_until,now() AS db_now FROM login_rate_limits WHERE key_hash=%s",
                (self._key(key),),
            ).fetchone()
        return (
            max(0, ceil((row["locked_until"] - row["db_now"]).total_seconds()))
            if row and row["locked_until"]
            else 0
        )

    def failure(self, key: str, _now: float) -> int:
        key_hash = self._key(key)
        with connection() as conn:
            conn.execute(
                "INSERT INTO login_rate_limits(key_hash,window_started_at) VALUES (%s,now()) ON CONFLICT DO NOTHING",
                (key_hash,),
            )
            row = conn.execute(
                "SELECT attempts,window_started_at,locked_until,lockouts,now() AS db_now "
                "FROM login_rate_limits WHERE key_hash=%s FOR UPDATE",
                (key_hash,),
            ).fetchone()
            now = row["db_now"]
            if row["locked_until"] and row["locked_until"] > now:
                return ceil((row["locked_until"] - now).total_seconds())
            attempts = (
                0
                if (now - row["window_started_at"]).total_seconds() >= self.window_seconds
                else row["attempts"]
            )
            attempts += 1
            lockouts = row["lockouts"]
            duration = 0
            locked_until = None
            if attempts >= self.max_failures:
                lockouts += 1
                duration = min(self.lock_seconds * (2 ** min(lockouts - 1, 3)), self.lock_seconds * 8)
                locked_until = now + timedelta(seconds=duration)
                attempts = 0
            conn.execute(
                "UPDATE login_rate_limits SET attempts=%s,window_started_at=%s,locked_until=%s,"
                "lockouts=%s,updated_at=now() WHERE key_hash=%s",
                (
                    attempts,
                    now if attempts == 1 or duration else row["window_started_at"],
                    locked_until,
                    lockouts,
                    key_hash,
                ),
            )
            return duration

    def success(self, key: str) -> None:
        with connection() as conn:
            conn.execute("DELETE FROM login_rate_limits WHERE key_hash=%s", (self._key(key),))


def make_login_limiter() -> LoginRateLimiter | DatabaseLoginRateLimiter:
    cfg = settings()
    cls = DatabaseLoginRateLimiter if cfg.rate_limit_backend == "database" else LoginRateLimiter
    return cls(cfg.auth_login_max_failures, cfg.auth_login_window_seconds, cfg.auth_login_lock_seconds)


login_limiter = make_login_limiter()


def login_key(request: Request, username: str) -> str:
    client = request.client.host if request.client else "unknown"
    return f"{client}:{username.casefold()}"


def ensure_not_last_active_admin(conn, user_id: int) -> None:
    conn.execute("SELECT pg_advisory_xact_lock(20260921)")
    target = conn.execute("SELECT role,is_active FROM users WHERE id=%s", (user_id,)).fetchone()
    if not target or target["role"] != "admin" or not target["is_active"]:
        return
    count = conn.execute(
        "SELECT count(*) AS total FROM users WHERE role='admin' AND is_active=true"
    ).fetchone()["total"]
    if count <= 1:
        raise ValueError("Não é permitido desativar ou remover o último administrador ativo.")
