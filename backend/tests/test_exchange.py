from datetime import date
from types import SimpleNamespace

import httpx
import pytest
from app.agents import build_graph
from app.exchange import exchange_request, lookup_ptax
from app.schemas import Route

TODAY = date(2026, 10, 6)


@pytest.mark.parametrize(
    "message,pair",
    [
        ("dolar para real hoje", "USD/BRL"),
        ("euro hoje", "EUR/BRL"),
        ("USD to BRL today", "USD/BRL"),
        ("real para dólar", "BRL/USD"),
        ("Peso Argentino para real?", "ARS/BRL"),
        ("qual valor do iene", "JPY/BRL"),
        ("dolar canadense", "CAD/BRL"),
        ("dolar para euro", "USD/EUR"),
        ("franco suíço", "CHF/BRL"),
        ("CNY/BRL", "CNY/BRL"),
        ("tugrik", "MNT/BRL"),
    ],
)
def test_exchange_pair_and_date_are_resolved(message, pair):
    request = exchange_request(message, {}, TODAY)
    assert request["pair"] == pair
    assert request["date"] == "2026-10-06"


def test_unknown_currency_name_can_use_router_iso_slots():
    assert exchange_request("qual valor da pataca?", {}, TODAY, ["MOP", "BRL"])["pair"] == "MOP/BRL"
    assert exchange_request("try again", {}, TODAY) is None
    assert exchange_request("Meu problema é real", {}, TODAY) is None
    assert exchange_request("dolar para pataca", {}, TODAY, ["USD", "MOP"])["pair"] == "USD/MOP"
    assert exchange_request("dolar para dolar", {}, TODAY)["pair"] == "USD/USD"


@pytest.mark.parametrize(
    "message,pair", [("Peso Argentino para real?", "ARS/BRL"), ("dolar para euro", "USD/EUR")]
)
def test_other_currency_search_keeps_financial_topic(monkeypatch, message, pair):
    monkeypatch.setattr("app.agents.lookup_ptax", lambda *_: None)
    queries = []

    class Provider:
        def structured(self, *_):
            return Route(
                route="knowledge",
                knowledge_source="rag",
                support_tools=[],
                search_query="conversor Getnet",
                clarification="",
            )

        def web(self, query):
            queries.append(query)
            return "Cotação [1]", [{"id": 1, "kind": "web", "url": "https://www.bcb.gov.br/conversao"}]

    result = build_graph(Provider()).invoke(
        {
            "message": message,
            "user_id": "cliente1988",
            "conversation_memory": {"messages": [{"sender": "customer", "content": "Qual valor do câmbio?"}]},
        }
    )
    assert pair in queries[0]
    assert "Getnet" not in queries[0]
    assert result["status"] == "ok"


@pytest.mark.parametrize("matched", [True, False])
def test_cross_rate_requires_same_closing_timestamp(monkeypatch, matched):
    def get(url, **kwargs):
        code = kwargs["params"]["@moeda"]
        stamp = "2026-10-06 13:00:00" if matched or code == "'USD'" else "2026-10-05 13:00:00"
        return SimpleNamespace(
            raise_for_status=lambda: None,
            url=url,
            json=lambda: {
                "value": [
                    {
                        "cotacaoVenda": 5 if code == "'USD'" else 6,
                        "dataHoraCotacao": stamp,
                        "tipoBoletim": "Fechamento",
                    }
                ]
            },
        )

    monkeypatch.setattr("app.exchange.httpx.get", get)
    result = lookup_ptax(exchange_request("dolar para euro", {}, TODAY))
    if matched:
        assert "1 USD ≈ 0.833333 EUR" in result[0]
        assert len(result[1]) == 2
        assert "indicativa" in result[0]
    else:
        assert result is None


def test_short_followup_uses_only_recent_exchange_customer_context():
    memory = {"messages": [{"sender": "customer", "content": "Qual a cotação do dólar?"}]}
    assert exchange_request("hoje", memory, TODAY)["pair"] == "USD/BRL"
    assert exchange_request("Quanto recebo pelas vendas?", memory, TODAY) is None
    memory["messages"].append({"sender": "customer", "content": "Minha máquina não liga"})
    assert exchange_request("hoje", memory, TODAY) is None


def test_exchange_generic_and_invalid_date_do_not_search_without_slots():
    assert not exchange_request("Qual o valor do câmbio?", {}, TODAY)["pair"]
    assert exchange_request("dólar em 31/02/2026", {}, TODAY)["invalid_date"]


def test_graph_followup_performs_search_without_repeating_clarification(monkeypatch):
    captured = []
    monkeypatch.setattr("app.agents.lookup_ptax", lambda *_: None)

    class Provider:
        def structured(self, *_):
            return Route(route="clarify", search_query="", support_tools=[], clarification="Qual par e data?")

        def web(self, query):
            captured.append(query)
            return "USD/BRL, cotação verificada [1]", [
                {"id": 1, "kind": "web", "title": "BCB", "url": "https://www.bcb.gov.br/conversao"}
            ]

    result = build_graph(Provider()).invoke(
        {
            "message": "dolar para real hoje",
            "user_id": "cliente1988",
            "steps": [],
            "conversation_memory": {
                "messages": [
                    {"sender": "customer", "content": "Qual o valor do câmbio?"},
                    {"sender": "ai", "content": "Qual par de moedas e data?"},
                ]
            },
        }
    )
    assert result["status"] == "ok"
    assert "USD/BRL" in captured[0]
    assert "Getnet" not in captured[0]
    assert "Qual par" not in result["answer"]
    assert result["sources"]


def test_failure_does_not_ask_for_already_supplied_pair(monkeypatch):
    monkeypatch.setattr("app.agents.lookup_ptax", lambda *_: None)

    class Provider:
        def structured(self, *_):
            return Route(route="knowledge", search_query="", support_tools=[], clarification="")

        def web(self, *_):
            return "Indisponível", []

    result = build_graph(Provider()).invoke(
        {
            "message": "dólar para real hoje",
            "user_id": "cliente1988",
            "steps": [],
        }
    )
    assert result["status"] == "needs_clarification"
    assert "Qual par" not in result["answer"]
    assert not result["sources"]


def test_ptax_is_read_directly_and_previous_day_is_explicit(monkeypatch):
    captured = {}

    def get(url, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            raise_for_status=lambda: None,
            url=url,
            json=lambda: {
                "value": [
                    {
                        "cotacaoCompra": 5.1234,
                        "cotacaoVenda": 5.1242,
                        "dataHoraCotacao": "2026-10-05 13:00:00",
                        "tipoBoletim": "Fechamento",
                    },
                ]
            },
        )

    monkeypatch.setattr("app.exchange.httpx.get", get)
    answer, sources = lookup_ptax(exchange_request("dólar hoje", {}, TODAY))
    assert "5,1234" in answer and "5,1242" in answer
    assert "05/10/2026" in answer
    assert "último fechamento publicado" in answer
    assert sources[0]["title"].startswith("Banco Central")
    assert captured["follow_redirects"] is False
    assert captured["timeout"] == 8
    assert captured["params"]["@moeda"] == "'USD'"


@pytest.mark.parametrize("value", [float("nan"), -1, None, "not-a-rate"])
def test_invalid_quotes_are_never_released(monkeypatch, value):
    monkeypatch.setattr(
        "app.exchange.httpx.get",
        lambda *_args, **_kwargs: SimpleNamespace(
            raise_for_status=lambda: None,
            url="https://olinda.bcb.gov.br",
            json=lambda: {
                "value": [
                    {
                        "cotacaoCompra": value,
                        "cotacaoVenda": 5,
                        "dataHoraCotacao": "2026-10-06 13:00:00",
                        "tipoBoletim": "Fechamento",
                    },
                ]
            },
        ),
    )
    assert lookup_ptax(exchange_request("dólar hoje", {}, TODAY)) is None


def test_timeout_falls_back_without_fabrication(monkeypatch):
    def get(*_args, **_kwargs):
        raise httpx.ReadTimeout("timeout")

    monkeypatch.setattr("app.exchange.httpx.get", get)
    assert lookup_ptax(exchange_request("dólar hoje", {}, TODAY)) is None


def test_explicit_historical_date_does_not_use_previous_day(monkeypatch):
    monkeypatch.setattr(
        "app.exchange.httpx.get",
        lambda *_args, **_kwargs: SimpleNamespace(
            raise_for_status=lambda: None,
            url="https://olinda.bcb.gov.br",
            json=lambda: {
                "value": [
                    {
                        "cotacaoCompra": 5,
                        "cotacaoVenda": 5,
                        "dataHoraCotacao": "2026-10-05 13:00:00",
                        "tipoBoletim": "Fechamento",
                    },
                ]
            },
        ),
    )
    assert lookup_ptax(exchange_request("dólar em 06/10/2026", {}, TODAY)) is None
