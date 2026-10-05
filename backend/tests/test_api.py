import pytest
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def isolate_rate_limiter(monkeypatch):
    from app.rate_limit import InMemoryRateLimiter

    monkeypatch.setattr("app.main.request_limiter", InMemoryRateLimiter())


def test_api_rejects_bad_payload():
    client = TestClient(app)
    assert client.post("/api/chat", json={"message": " ", "user_id": "cliente1988"}).status_code == 422


def test_api_unknown_customer(monkeypatch):
    monkeypatch.setattr("app.main.customer_exists", lambda _: False)
    client = TestClient(app)
    assert client.post("/api/chat", json={"message": "Olá", "user_id": "cliente9999"}).status_code == 404


def test_api_missing_key_is_honest(monkeypatch):
    from app.provider import ProviderUnavailable

    monkeypatch.setattr("app.main.customer_exists", lambda _: True)
    monkeypatch.setattr(
        "app.main.get_or_create_conversation",
        lambda _: {"id": "conversation-test", "status": "ai", "failure_count": 0},
    )
    monkeypatch.setattr("app.main.persist_message", lambda *args: None)
    monkeypatch.setattr("app.main.persist_run", lambda **kwargs: None)

    def fail():
        raise ProviderUnavailable("Configure a chave")

    monkeypatch.setattr("app.main.Provider", fail)
    response = TestClient(app).post("/api/chat", json={"message": "Olá", "user_id": "cliente1988"})
    assert response.status_code == 503
    assert response.json()["message"] == "Configure a chave"


def test_short_acknowledgement_does_not_call_provider_or_clarify(monkeypatch):
    monkeypatch.setattr("app.main.customer_exists", lambda _: True)
    monkeypatch.setattr(
        "app.main.get_or_create_conversation",
        lambda _: {"id": "00000000-0000-0000-0000-000000000001", "status": "ai", "failure_count": 0},
    )
    monkeypatch.setattr("app.main.persist_message", lambda *args: None)
    monkeypatch.setattr("app.main.persist_run", lambda **kwargs: None)
    monkeypatch.setattr(
        "app.main.Provider", lambda: (_ for _ in ()).throw(AssertionError("LLM não deve ser chamado"))
    )
    response = TestClient(app).post("/api/chat", json={"message": "ok", "user_id": "cliente1988"})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["route"] != "clarify"
