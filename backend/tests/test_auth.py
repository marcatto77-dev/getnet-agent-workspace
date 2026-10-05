import pytest
from app.auth import (
    LoginRateLimiter,
    ensure_not_last_active_admin,
    hash_password,
    validate_new_password,
    verify_password,
)


def test_password_hash_and_verification():
    encoded = hash_password("segredo-forte")
    assert encoded != "segredo-forte"
    assert verify_password("segredo-forte", encoded)
    assert not verify_password("incorreta", encoded)


class FakeConnection:
    def __init__(self, target, active_admins):
        self.target = target
        self.active_admins = active_admins

    def execute(self, query, params=None):
        if "advisory" in query:
            return None
        value = self.target if "WHERE id=" in query else {"total": self.active_admins}
        return type("Result", (), {"fetchone": lambda self: value})()


def test_last_active_admin_cannot_be_disabled():
    with pytest.raises(ValueError, match="último administrador"):
        ensure_not_last_active_admin(FakeConnection({"role": "admin", "is_active": True}, 1), 1)


def test_admin_can_be_disabled_when_another_is_active():
    ensure_not_last_active_admin(FakeConnection({"role": "admin", "is_active": True}, 2), 1)


def test_login_rate_limit_locks_and_expires():
    limiter = LoginRateLimiter(max_failures=2, window_seconds=10, lock_seconds=20)
    assert limiter.failure("ip:user", 100) == 0
    assert limiter.failure("ip:user", 101) == 20
    assert limiter.check("ip:user", 110) == 11
    assert limiter.check("ip:user", 122) == 0


def test_success_clears_login_failures():
    limiter = LoginRateLimiter(max_failures=2, window_seconds=10, lock_seconds=20)
    limiter.failure("ip:user", 100)
    limiter.success("ip:user")
    assert limiter.failure("ip:user", 101) == 0


def test_customer_password_policy():
    for password in ("123", "12345678", "password", "clientex"):
        with pytest.raises(ValueError):
            validate_new_password("clientex", password)
    validate_new_password("clientex", "Senha-Nova-2026")
