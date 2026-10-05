import json

import pytest
from app.agent_inspection import inspection_snapshot
from app.agents import build_graph, explicit_human_request, reference_date_for_message
from app.auth import current_user
from app.conversation_policy import language_for, policy_message
from app.guardrails.input import inspect_input
from app.guardrails.output import CANARY, inspect_output
from app.guardrails.scope import EXCHANGE_DOMAINS
from app.main import app
from app.schemas import Draft, EscalationSummary, Route
from fastapi.testclient import TestClient


class PolicyProvider:
    def __init__(self, **kwargs):
        self.route = Route(
            route="knowledge", support_tools=[], search_query="Getnet Pix", clarification="", **kwargs
        )

    def structured(self, prompt, message, schema):
        if schema is Route:
            return self.route.model_copy(deep=True)
        if schema is EscalationSummary:
            return EscalationSummary(
                problem="Pedido",
                customer_context="Demo",
                terminal_context="Demo",
                attempts=[],
                reason="cliente_pediu",
            )
        return Draft(answer="Orientação oficial [1]", source_ids=[1], insufficient_evidence=False)


@pytest.fixture
def policy_dependencies(monkeypatch):
    monkeypatch.setattr(
        "app.agents.retrieve", lambda *_args: [{"id": 1, "title": "Getnet", "content": "Manual oficial"}]
    )
    monkeypatch.setattr("app.agents.run_tool", lambda *_args: {"id": 1, "title": "Demo", "content": "{}"})
    handoffs = []

    def create(*args):
        handoffs.append(args)
        return {"id": "handoff", "status": "waiting", "queue_position": 1}

    monkeypatch.setattr("app.agents.create_handoff", create)
    return handoffs


def invoke(provider, message, count=0, offered=False):
    return build_graph(provider).invoke(
        {
            "message": message,
            "user_id": "cliente1988",
            "conversation_id": "00000000-0000-0000-0000-000000000001",
            "conversation_memory": {"assistance_count": count, "handoff_offered": offered},
            "steps": [],
        }
    )


@pytest.mark.parametrize(
    "count,dissatisfied,status",
    [(0, True, "ok"), (2, True, "ok"), (3, False, "ok"), (3, True, "needs_handoff")],
)
def test_offer_requires_three_actual_assistance_answers_and_dissatisfaction(
    policy_dependencies, count, dissatisfied, status
):
    result = invoke(
        PolicyProvider(customer_dissatisfied=dissatisfied), "Não resolveu meu problema Getnet", count
    )
    assert result["status"] == status
    assert policy_dependencies == []
    if status == "needs_handoff":
        assert "Gostaria" in result["answer"]
        assert len(result["quick_replies"]) == 2


@pytest.mark.parametrize(
    "message,language",
    [
        ("Quero falar com um técnico", "pt"),
        ("I need a human technician", "en"),
        ("Quiero hablar con un técnico", "es"),
    ],
)
def test_explicit_human_request_does_not_require_three_answers(policy_dependencies, message, language):
    result = invoke(PolicyProvider(language=language), message)
    assert result["status"] == "waiting"
    assert len(policy_dependencies) == 1
    assert result["answer"] == policy_message("queue", language).format(position=1)


@pytest.mark.parametrize("offered", [False, True])
def test_yes_only_confirms_a_pending_server_offer(policy_dependencies, offered):
    result = invoke(PolicyProvider(accepts_human_offer=True), "Sim", count=3, offered=offered)
    assert (result["status"] == "waiting") is offered
    assert len(policy_dependencies) == int(offered)


def test_declining_offer_overrides_erroneous_model_acceptance(policy_dependencies):
    result = invoke(
        PolicyProvider(accepts_human_offer=True, customer_dissatisfied=True),
        "Não, quero continuar por aqui",
        count=3,
        offered=True,
    )
    assert result["status"] == "needs_clarification"
    assert result["answer"] == policy_message("continue", "pt")
    assert policy_dependencies == []
    assert not explicit_human_request("Não quero falar com um técnico")


@pytest.mark.parametrize(
    "message,language",
    [("Vai chover amanhã?", "pt"), ("Will it rain tomorrow?", "en"), ("¿Va a llover mañana?", "es")],
)
def test_weather_never_reaches_human_queue(message, language):
    assert inspect_input(message, "cliente1988", "challenge", has_context=True).block
    assert language_for(message) == language
    assert "técnico" not in policy_message("scope", language)


@pytest.mark.parametrize(
    "message",
    [
        "Qual o câmbio do euro?",
        "What's the euro exchange rate today?",
        "¿Cuál es el tipo de cambio del euro?",
        "Minha máquina mostra código de erro",
        "Qual o tempo para receber minha venda?",
    ],
)
def test_financial_and_machine_questions_are_not_false_positives(message):
    assert not inspect_input(message, "cliente1988", "getnet_exchange").block


def test_currency_sources_are_limited_to_financial_official_sites():
    assert inspect_output("Fonte https://www.bcb.gov.br/", EXCHANGE_DOMAINS)[0]
    assert not inspect_output("Fonte https://example.org/", EXCHANGE_DOMAINS)[0]


@pytest.mark.parametrize("role,status", [("admin", 200), ("tecnico", 403), ("cliente", 403)])
def test_admin_inspector_authorization_and_canary_redaction(role, status):
    app.dependency_overrides[current_user] = lambda: {"id": 1, "role": role, "must_change_password": False}
    try:
        response = TestClient(app).get("/api/admin/agents")
        assert response.status_code == status
        if status == 200:
            assert len(response.json()["agents"]) == 4
            assert CANARY not in response.text
            assert "openai_api_key" not in response.text
    finally:
        app.dependency_overrides.pop(current_user, None)


def test_inspector_disallows_anonymous_access():
    assert TestClient(app).get("/api/admin/agents").status_code == 401


def test_snapshot_uses_current_prompts_and_spanish_relative_date():
    from datetime import date

    snapshot = inspection_snapshot()
    assert "cotação" in json.dumps(snapshot, ensure_ascii=False)
    assert reference_date_for_message("ventas de ayer", date(2026, 10, 4)) == date(2026, 10, 3)
