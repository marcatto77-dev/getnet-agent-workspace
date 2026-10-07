from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from app.agents import build_graph
from app.config import Settings
from app.provider import BudgetExceeded, reserve
from app.rag import lexical_terms, retrieve
from app.schemas import Draft, Route


def test_getnet_knowledge_uses_rag_first_without_unrelated_selected_model(monkeypatch):
    queries = []

    def retrieval(query, _provider):
        queries.append(query)
        return [{"id": 1, "title": "Endereço cadastrado", "kind": "manual", "content": "Endereço de teste"}]

    monkeypatch.setattr("app.agents.retrieve", retrieval)

    class Provider:
        def structured(self, _prompt, _payload, schema):
            if schema is Route:
                return Route(
                    route="knowledge",
                    knowledge_source="web",
                    support_tools=[],
                    search_query="endereço ou localização da Getnet",
                    clarification="",
                )
            return Draft(answer="Endereço cadastrado [1]", source_ids=[1], insufficient_evidence=False)

        def web(self, _):
            pytest.fail("Não deve buscar na web quando o RAG sustenta a resposta.")

    result = build_graph(Provider()).invoke(
        {
            "message": "Onde fica a Getnet?",
            "user_id": "cliente1988",
            "steps": [],
            "customer_context": {
                "selected_terminal_id": "t1",
                "terminals": [{"id": "t1", "model": "Get Smart"}],
            },
        }
    )
    assert queries == ["endereço ou localização da Getnet"]
    assert result["sources"][0]["kind"] == "manual"
    assert result["route"].knowledge_source == "rag"


def test_hybrid_retrieval_keeps_lexical_hit_even_with_distant_embedding(monkeypatch):
    sqls = []
    row = {
        "id": 19,
        "title": "Qual o endereço da Getnet",
        "source": "manual:test",
        "origin": "manual",
        "content": "Endereço cadastrado de teste",
        "updated_at": datetime.now(timezone.utc),
        "distance": 0.99,
    }

    class Conn:
        def execute(self, sql, params=None):
            sqls.append((sql, params))
            return SimpleNamespace(
                fetchone=lambda: {"exists": 1}, fetchall=lambda: [row] if "ts_rank_cd" in sql else []
            )

    @contextmanager
    def connection(**_):
        yield Conn()

    monkeypatch.setattr("app.rag.connection", connection)
    provider = SimpleNamespace(embed=lambda _: [[0.1]])
    found = retrieve("endereço ou localização da Getnet", provider)
    assert found[0]["chunk_id"] == 19
    assert found[0]["kind"] == "manual"
    assert found[0]["url"] is None
    lexical_sql = next(sql for sql, _ in sqls if "ts_rank_cd" in sql)
    assert "review_required=false" in lexical_sql and "status_embedding='indexed'" in lexical_sql
    assert "%s" in lexical_sql


def test_lexical_terms_are_bounded_and_do_not_use_generic_getnet_term():
    assert lexical_terms("Onde fica a Getnet?") == "endereço"
    assert "getnet" not in lexical_terms("endereço ou localização da Getnet")
    assert "'" not in lexical_terms("endereço'; DROP TABLE chunks")
    assert len(lexical_terms("palavra " * 100).split(" | ")) == 1


@pytest.mark.parametrize(
    "env,demo,expected",
    [
        ("development", True, True),
        ("production", True, False),
        ("development", False, False),
    ],
)
def test_unlimited_daily_usage_is_local_demo_only(env, demo, expected):
    cfg = Settings(_env_file=None, demo_unlimited_usage=True, demo_mode=demo, app_env=env)
    assert cfg.unlimited_demo_usage is expected


@pytest.mark.parametrize("unlimited", [True, False])
def test_daily_reservation_continues_counting_but_can_bypass_local_limit(monkeypatch, unlimited):
    calls = []

    class Conn:
        def execute(self, sql, params):
            calls.append((sql, params))
            return SimpleNamespace(fetchone=lambda: {"calls": 1001} if unlimited else None)

    @contextmanager
    def connection():
        yield Conn()

    monkeypatch.setattr("app.provider.connection", connection)
    monkeypatch.setattr(
        "app.provider.settings",
        lambda: SimpleNamespace(
            daily_model_call_limit=100, daily_web_call_limit=10, unlimited_demo_usage=unlimited
        ),
    )
    if unlimited:
        reserve("model")
    else:
        with pytest.raises(BudgetExceeded):
            reserve("model")
    assert calls[-1][1][2] is unlimited
    assert "calls=calls+1" in calls[-1][0]
