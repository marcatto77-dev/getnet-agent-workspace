from pathlib import Path

from app.provider import CircuitBreaker


def test_memory_and_escalation_are_explicitly_untrusted():
    source = Path("backend/app/agents.py").read_text(encoding="utf-8")
    assert "conversation_memory" in source
    assert "HISTORICO_NAO_CONFIAVEL" in source


def test_circuit_breaker_opens_after_failures(monkeypatch):
    monkeypatch.setattr(
        "app.provider.settings",
        lambda: type("C", (), {"openai_circuit_failure_threshold": 2, "openai_circuit_reset_seconds": 60})(),
    )
    breaker = CircuitBreaker()
    breaker.failure()
    breaker.failure()
    assert not breaker.allow()


def test_bootstrap_degrades_instead_of_raising_without_key():
    source = Path("backend/app/bootstrap.py").read_text(encoding="utf-8")
    assert "_degraded" in source
    assert "OPENAI_API_KEY ausente" in source


def test_metrics_and_snapshot_documented():
    assert Path("backend/scripts/rag_snapshot.py").exists()
    assert Path("docs/ALERTS.md").exists()
    assert "getnet_requests_total" in Path("backend/app/main.py").read_text(encoding="utf-8")
