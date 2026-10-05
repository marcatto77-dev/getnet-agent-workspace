"""Transport and request security kept independent from business handlers."""

import re
from urllib.parse import urlparse

from fastapi import HTTPException, Request, WebSocket

from .config import settings

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
CONTROL = re.compile(r"[\r\n\x00-\x08\x0b\x0c\x0e-\x1f\x7f]+")


def safe_log_value(value: object, limit: int = 500) -> str:
    text = CONTROL.sub(" ", str(value))
    return text[:limit]


def client_ip(request: Request) -> str:
    # Do not trust forwarding headers unless a trusted proxy layer is configured.
    return request.client.host if request.client else "unknown"


def origin_allowed(origin: str | None) -> bool:
    if not origin:
        return False
    parsed = urlparse(origin)
    normalized = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    return parsed.scheme in {"http", "https"} and normalized in settings().trusted_csrf_origins


def enforce_csrf(request: Request) -> None:
    if request.method not in UNSAFE_METHODS:
        return
    cfg = settings()
    has_session = bool(
        request.cookies.get(cfg.auth_cookie_name) or request.cookies.get(cfg.customer_cookie_name)
    )
    origin = request.headers.get("origin")
    # Cookie-authenticated browser writes are origin-bound. In non-production an absent
    # Origin is retained for CLI/backward-compatible integration clients.
    if has_session and (cfg.production or origin) and not origin_allowed(origin):
        raise HTTPException(403, "Origem não autorizada para esta operação.")


def websocket_origin_allowed(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin")
    return origin_allowed(origin) if (settings().production or origin) else True


def security_headers(response) -> None:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
        "form-action 'self'; img-src 'self' data: https:; connect-src 'self' ws: wss:; "
        "script-src 'self'; style-src 'self' 'unsafe-inline'"
    )
    if settings().production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"


def route_role(path: str, method: str) -> str:
    """Single fail-closed authorization registry exported into OpenAPI."""
    if path.startswith("/api/admin"):
        return "admin"
    if path.startswith("/api/tech") or path == "/api/tecnico":
        return "tecnico"
    if path.startswith("/api/customer"):
        return "cliente"
    if path in {"/api/auth/me", "/api/auth/logout", "/api/auth/change-password"}:
        return "authenticated"
    if path.startswith("/api/chat/conversations") or path == "/api/chat/current":
        return "cliente-session"
    if path in {
        "/api/auth/login",
        "/api/chat",
        "/api/health/live",
        "/api/health/ready",
        "/api/demo/customers",
        "/api/metrics",
    }:
        return "public"
    if path == "/metrics":
        return "internal"
    raise RuntimeError(f"Rota sem política de autorização: {method} {path}")


def annotate_openapi(schema: dict) -> dict:
    for path, operations in schema.get("paths", {}).items():
        for method, operation in operations.items():
            if method.casefold() in {"get", "post", "put", "patch", "delete"}:
                operation["x-required-role"] = route_role(path, method.upper())
    return schema
