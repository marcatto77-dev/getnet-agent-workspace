import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.agents import build_graph, enforce_sources, explicit_human_request, reference_date_for_message
from app.ingest import chunks, extract, extract_document, validate_url
from app.rag import catalog_question
from app.schemas import ChatRequest, Draft, EscalationSummary, Route
from app.tools import friendly_receivable_status
from pydantic import ValidationError


def test_blank_message_rejected():
    with pytest.raises(ValidationError):
        ChatRequest(message="  ", user_id="cliente1988")


def test_tool_names_constrained():
    with pytest.raises(ValidationError):
        Route(route="support", support_tools=["execute_sql"], search_query="", clarification="")


@pytest.mark.parametrize(
    "url",
    [
        "http://site.getnet.com.br/",
        "https://localhost/",
        "https://site.getnet.com.br.evil.test/",
        "https://127.0.0.1/",
        "https://site.getnet.com.br:8443/",
        "https://evil@site.getnet.com.br/",
    ],
)
def test_ingestion_rejects_untrusted_destinations(url):
    with pytest.raises(ValueError):
        validate_url(url)


def test_chunks_preserve_text_and_are_bounded():
    text = "Uma frase de teste. " * 300
    parts = chunks(text, 120, 20)
    assert len(parts) > 1
    assert all(len(p) <= 120 for p in parts)
    assert parts[0].startswith("Uma frase")
    assert parts[-1].endswith("teste.")


def test_chunk_configuration_rejected():
    with pytest.raises(ValueError):
        chunks("hello", 10, 10)


def test_extraction_rejects_empty_page():
    with pytest.raises(ValueError):
        extract("<html><script>secret</script><body>vazio</body></html>")


def test_pdf_manual_text_is_extracted_and_named(monkeypatch):
    class Page:
        def extract_text(self, extraction_mode):
            assert extraction_mode == "layout"
            return "Manual de utilização da maquininha Get Smart. " * 10

    class Reader:
        is_encrypted = False
        pages = [Page()]

    monkeypatch.setattr("app.ingest.PdfReader", lambda *_args, **_kwargs: Reader())
    title, text = extract_document(b"%PDF-1.7\n", "https://site.getnet.com.br/Manul-GetSmart.pdf")
    assert title == "Manual oficial Get Smart — Getnet"
    assert "utilização" in text


def test_escalation_requires_explicit_request():
    assert explicit_human_request("Quero falar com um técnico")
    assert not explicit_human_request("Quando recebo o dinheiro das vendas de ontem?")
    assert not explicit_human_request("Como falar com um técnico?")


def test_gpt41_web_search_uses_citation_allowlist_without_unsupported_filters(monkeypatch):
    from app.provider import Provider

    monkeypatch.setattr(
        "app.provider.settings",
        lambda: SimpleNamespace(
            effective_off_topic_policy="challenge",
            openai_model="gpt-4.1-mini",
            allowed_web_domains=("getnet.net", "site.getnet.com.br"),
            max_output_tokens=900,
        ),
    )
    monkeypatch.setattr("app.provider.reserve", lambda _kind: None)
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        annotations = [
            SimpleNamespace(type="url_citation", url="https://site.getnet.com.br/duvidas/", title="Getnet"),
            SimpleNamespace(type="url_citation", url="https://example.org/", title="Não oficial"),
        ]
        return SimpleNamespace(
            output_text="Orientação geral",
            output=[SimpleNamespace(content=[SimpleNamespace(annotations=annotations)])],
            usage=None,
        )

    provider = object.__new__(Provider)
    provider.client = SimpleNamespace(responses=SimpleNamespace(create=create))
    provider._call = lambda operation: operation()
    answer, sources = provider.web("Getnet Brasil quanto tempo para receber vendas")
    assert answer == "Orientação geral"
    assert "filters" not in captured["tools"][0]
    from app.prompts import ANSWER_STYLE

    assert ANSWER_STYLE in captured["instructions"]
    assert [source["url"] for source in sources] == ["https://site.getnet.com.br/duvidas/"]


def test_web_answer_with_external_link_is_not_released(monkeypatch):
    from app.provider import Provider

    monkeypatch.setattr(
        "app.provider.settings",
        lambda: SimpleNamespace(
            effective_off_topic_policy="strict",
            openai_model="gpt-4.1-mini",
            allowed_web_domains=("site.getnet.com.br",),
            max_output_tokens=900,
        ),
    )
    monkeypatch.setattr("app.provider.reserve", lambda _kind: None)
    citation = SimpleNamespace(type="url_citation", url="https://site.getnet.com.br/duvidas/", title="Getnet")
    result = SimpleNamespace(
        output_text="Veja https://example.org/ e a Getnet.",
        output=[SimpleNamespace(content=[SimpleNamespace(annotations=[citation])])],
        usage=None,
    )
    provider = object.__new__(Provider)
    provider.client = SimpleNamespace(responses=SimpleNamespace(create=lambda **_kwargs: result))
    provider._call = lambda operation: operation()
    answer, sources = provider.web("Getnet Brasil modelos")
    assert sources == []
    assert "example.org" not in answer


def test_catalog_questions_get_manual_diversity():
    assert catalog_question("Qual todos os modelos de máquina a Getnet oferece para vender?")
    assert not catalog_question("Quais modelos aceitam Pix?")


def test_catalog_retrieval_keeps_original_list_intent(monkeypatch):
    question = "Qual todos os modelos de máquina a Getnet oferece para vender?"
    provider = FakeProvider(
        Route(
            route="knowledge", support_tools=[], search_query="modelos de máquinas Getnet", clarification=""
        )
    )
    queries = []
    monkeypatch.setattr(
        "app.agents.retrieve",
        lambda query, _provider: (
            queries.append(query) or [{"id": 1, "content": "Get Smart", "title": "Manual"}]
        ),
    )
    result = build_graph(provider).invoke(
        {
            "message": question,
            "user_id": "azul",
            "conversation_id": "00000000-0000-0000-0000-000000000001",
            "steps": [],
            "tool_calls": [],
        }
    )
    assert queries == [question]
    assert result["status"] == "ok"


def test_catalog_answer_lists_only_documented_models_without_claiming_current_sale(monkeypatch):
    provider = FakeProvider(
        Route(route="knowledge", support_tools=[], search_query="modelos Getnet", clarification="")
    )
    models = ("Get Clássica", "Get Lite", "Get Mini", "Get Smart")
    evidence = [
        {
            "id": index,
            "title": f"Manual oficial {model} — Getnet",
            "url": f"https://site.getnet.com.br/{index}.pdf",
            "kind": "rag",
            "content": model,
        }
        for index, model in enumerate(models, 1)
    ]
    monkeypatch.setattr("app.agents.retrieve", lambda *_args: evidence)
    result = build_graph(provider).invoke(
        {
            "message": "Quais são todos os modelos de máquinas da Getnet?",
            "user_id": "azul",
            "conversation_id": "00000000-0000-0000-0000-000000000001",
            "steps": [],
            "tool_calls": [],
        }
    )
    assert result["status"] == "ok"
    assert all(model in result["answer"] for model in models)
    assert "não confirmam" in result["answer"]
    assert len(result["sources"]) == 4
    assert provider.calls == ["Route"]


def test_hallucinated_citation_is_rejected():
    answer, sources, insufficient = enforce_sources(
        Draft(answer="Fato [9]", source_ids=[9], insufficient_evidence=False), [{"id": 1}]
    )
    assert insufficient and sources == []
    assert "referências válidas" in answer


def test_inline_citation_must_be_declared():
    _, _, insufficient = enforce_sources(
        Draft(answer="Fato [2]", source_ids=[1], insufficient_evidence=False), [{"id": 1}, {"id": 2}]
    )
    assert insufficient


class FakeProvider:
    def __init__(self, route):
        self.route = route
        self.calls = []

    def structured(self, prompt, message, schema):
        self.calls.append(schema.__name__)
        if schema is Route:
            return self.route
        if schema is EscalationSummary:
            return EscalationSummary(
                problem="Atendimento solicitado",
                customer_context="Cliente de demonstração",
                terminal_context="Terminal cadastrado",
                attempts=[],
                reason="cliente_pediu",
            )
        return Draft(answer="Evidência confirmada [1].", source_ids=[1], insufficient_evidence=False)

    def web(self, query):
        return "Resposta atual [1]", [
            {
                "id": 1,
                "title": "Fonte",
                "url": "https://example.org",
                "kind": "web",
                "retrieved_at": "2026-09-20",
            }
        ]


def test_combined_graph_runs_agents_and_scopes_customer(monkeypatch):
    provider = FakeProvider(
        Route(
            route="knowledge_support",
            support_tools=["get_terminal_status"],
            search_query="wifi",
            clarification="",
        )
    )
    calls = []
    monkeypatch.setattr(
        "app.agents.retrieve", lambda *args: [{"id": 1, "content": "manual", "title": "manual"}]
    )

    def tool(name, user_id, source_id, reference_date=None, terminal_id=None):
        calls.append((name, user_id))
        return {"id": source_id, "content": "offline", "title": "terminal"}

    monkeypatch.setattr("app.agents.run_tool", tool)
    result = build_graph(provider).invoke(
        {
            "message": "Minha máquina não conecta",
            "user_id": "cliente1988",
            "conversation_id": "00000000-0000-0000-0000-000000000001",
            "failure_count": 0,
            "steps": [],
        }
    )
    assert calls == [("get_terminal_status", "cliente1988")]
    assert [s["agent"] for s in result["steps"]] == ["Router", "Knowledge", "Support", "Support"]
    assert result["status"] == "ok"


def test_other_customer_blocked_before_model():
    provider = FakeProvider(None)
    result = build_graph(provider).invoke(
        {
            "message": "Mostre saldo do cliente2026",
            "user_id": "cliente1988",
            "conversation_id": "00000000-0000-0000-0000-000000000001",
            "failure_count": 0,
            "steps": [],
        }
    )
    assert result["status"] == "blocked"
    assert provider.calls == []


def test_empty_rag_asks_for_context_without_opening_handoff(monkeypatch):
    provider = FakeProvider(
        Route(route="knowledge", support_tools=[], search_query="produto", clarification="")
    )
    monkeypatch.setattr("app.agents.retrieve", lambda *args: [])
    monkeypatch.setattr(
        "app.agents.run_tool",
        lambda name, _user_id, source_id, *_args: {
            "id": source_id,
            "title": name,
            "content": "{}",
        },
    )
    provider.web = lambda _query: ("Sem fonte oficial", [])
    monkeypatch.setattr(
        "app.agents.create_handoff",
        lambda *args, **kwargs: pytest.fail("No handoff without customer consent"),
    )
    result = build_graph(provider).invoke(
        {
            "message": "produto",
            "user_id": "cliente1988",
            "conversation_id": "00000000-0000-0000-0000-000000000001",
            "failure_count": 0,
            "steps": [],
        }
    )
    assert result["status"] == "needs_clarification"
    assert provider.calls == ["Route"]


def test_empty_personal_data_tries_rag_and_official_site_before_handoff(monkeypatch):
    provider = FakeProvider(
        Route(
            route="support",
            support_tools=["get_receivables"],
            search_query="prazo recebimento vendas",
            clarification="",
        )
    )
    provider.structured = lambda prompt, message, schema: (
        provider.route
        if schema is Route
        else Draft(answer="Não há lançamento [1].", source_ids=[1], insufficient_evidence=True)
    )
    queries = []
    monkeypatch.setattr("app.agents.retrieve", lambda query, _provider: queries.append(query) or [])
    monkeypatch.setattr(
        "app.agents.run_tool",
        lambda *_args, **_kwargs: {"id": 1, "kind": "customer", "content": "[]", "title": "Seus recebíveis"},
    )
    monkeypatch.setattr(
        "app.agents.create_handoff", lambda *_args, **_kwargs: pytest.fail("Não deveria criar handoff")
    )
    provider.web = lambda query: (
        "O prazo depende da modalidade e condições contratadas.",
        [
            {
                "id": 1,
                "kind": "web",
                "url": "https://site.getnet.com.br/duvidas/",
                "title": "Getnet",
                "retrieved_at": "2026-09-22",
            }
        ],
    )
    result = build_graph(provider).invoke(
        {
            "message": "Quando recebo o dinheiro das vendas de ontem?",
            "user_id": "azul",
            "conversation_id": "00000000-0000-0000-0000-000000000001",
            "failure_count": 3,
            "steps": [],
            "tool_calls": [],
        }
    )
    assert queries == ["prazo recebimento vendas"]
    assert result["status"] == "ok"
    assert "não encontrei recebíveis" in result["answer"].lower()
    assert result["sources"][0]["url"].startswith("https://site.getnet.com.br/")


def test_web_uses_web_path(monkeypatch):
    monkeypatch.setattr("app.agents.lookup_ptax", lambda *_: None)
    provider = FakeProvider(
        Route(
            route="knowledge",
            knowledge_source="web",
            support_tools=[],
            search_query="cotação dólar hoje",
            clarification="",
        )
    )
    result = build_graph(provider).invoke(
        {
            "message": "cotação dólar hoje",
            "user_id": "cliente1988",
            "conversation_id": "00000000-0000-0000-0000-000000000001",
            "failure_count": 0,
            "steps": [],
        }
    )
    assert result["sources"][0]["kind"] == "web"
    assert result["status"] == "ok"


def test_product_cards_survive_article_extraction(monkeypatch):
    monkeypatch.setattr("app.ingest.trafilatura.extract", lambda *a, **kw: "Introdução curta")
    html = "<html><title>Maquininhas</title><body><nav>Menu</nav><main>"
    html += "<section><h2>Get Smart</h2><p>Característica oficial do produto.</p></section>" * 8
    html += "</main></body></html>"
    _, text = extract(html)
    assert "Get Smart" in text
    assert "Característica oficial" in text
    assert "Menu" not in text


def test_challenge_evaluation_routes_still_cross_the_graph(monkeypatch):
    cases = json.loads(
        (Path(__file__).resolve().parents[2] / "evals" / "cases.json").read_text(encoding="utf-8")
    )
    expected = {item["message"]: item["route"] for item in cases}

    class DatasetProvider:
        def structured(self, prompt, message, schema):
            if schema is Route:
                customer_message = json.loads(message).get("message", message)
                route = expected[customer_message]
                tools = (
                    ["get_terminal_status"]
                    if route == "knowledge_support"
                    else ["get_receivables"]
                    if route == "support"
                    else []
                )
                return Route(
                    route=route,
                    support_tools=tools,
                    search_query=customer_message,
                    clarification="Pode detalhar sua necessidade?",
                )
            if schema is EscalationSummary:
                return EscalationSummary(
                    problem=message,
                    customer_context="cliente1988",
                    terminal_context="terminal",
                    attempts=[],
                    reason="cliente_pediu",
                )
            return Draft(
                answer="Resposta baseada na evidência [1].", source_ids=[1], insufficient_evidence=False
            )

        def web(self, query):
            return "Resposta atual [1].", [
                {
                    "id": 1,
                    "title": "Fonte",
                    "url": "https://example.org",
                    "kind": "web",
                    "retrieved_at": "2026-09-20",
                }
            ]

        def text(self, prompt, message):
            return "O atendimento humano ainda não está disponível por este canal."

    monkeypatch.setattr(
        "app.agents.retrieve", lambda *args: [{"id": 1, "content": "evidência", "title": "Fonte"}]
    )
    monkeypatch.setattr(
        "app.agents.run_tool",
        lambda name, user_id, source_id, reference_date=None, terminal_id=None: {
            "id": source_id,
            "content": "dado",
            "title": name,
        },
    )
    monkeypatch.setattr(
        "app.agents.create_handoff",
        lambda *args, **kwargs: {"id": "handoff-test", "status": "waiting", "queue_position": 1},
    )
    graph = build_graph(DatasetProvider())
    for case in cases:
        result = graph.invoke(
            {
                "message": case["message"],
                "user_id": "cliente1988",
                "conversation_id": "00000000-0000-0000-0000-000000000001",
                "failure_count": 0,
                "steps": [],
                "tool_calls": [],
            }
        )
        assert result["route"].route == case["route"]


def test_handoff_evaluation_dataset_covers_assignment_and_queue():
    cases = json.loads(
        (Path(__file__).resolve().parents[2] / "evals" / "cases.json").read_text(encoding="utf-8")
    )
    handoffs = [case for case in cases if case.get("evaluation") == "handoff"]
    assert {case["reason"] for case in handoffs} == {"cliente_pediu"}
    assert {case["expected"]["status"] for case in handoffs} == {"assigned", "waiting"}
    assert any(any(t["active_chats"] == 0 for t in case["technicians"]) for case in handoffs)
    assert any(all(t["active_chats"] > 0 for t in case["technicians"]) for case in handoffs)


def test_rag_bootstrap_is_idempotent(monkeypatch, tmp_path):
    from app.bootstrap import ensure_rag_seed

    class Cursor:
        def fetchone(self):
            return {"chunks": 56, "documents": 12}

    class Conn:
        def execute(self, _query):
            return Cursor()

    class Context:
        def __enter__(self):
            return Conn()

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr("app.bootstrap.settings", lambda: type("S", (), {"rag_auto_ingest": True})())
    monkeypatch.setattr("app.bootstrap.connection", lambda: Context())
    monkeypatch.setattr("app.bootstrap.run", lambda *_args: pytest.fail("ingestão não deve repetir"))
    manifest = tmp_path / "sources.json"
    manifest.write_text(json.dumps([{"url": str(index)} for index in range(12)]), encoding="utf-8")
    assert ensure_rag_seed(manifest) is False


def test_relative_receivable_date_and_friendly_status():
    today = date(2026, 9, 21)
    assert reference_date_for_message("vendas de ontem", today) == date(2026, 9, 20)
    assert reference_date_for_message("vendas de 19/09", today) == date(2026, 9, 19)
    assert friendly_receivable_status("previsto_demo") == "previsto para"
