"""Bounded exchange slots and public PTAX lookup; no customer data leaves this module."""

import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

import httpx

from .currencies import currency_codes
from .guardrails.scope import is_exchange_query

PTAX_URL = (
    "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
    "CotacaoMoedaPeriodo(moeda=@moeda,dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
)


def exchange_request(
    message: str, memory: dict, today: date | None = None, currency_hint=None
) -> dict | None:
    today = today or datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    previous = ""
    for item in reversed(memory.get("messages", [])):
        if item.get("sender") != "customer" or item.get("content") == message:
            continue
        previous = item.get("content", "")
        break
    short_date = bool(
        re.fullmatch(
            r"\s*(?:hoje|today|hoy|ontem|yesterday|ayer|\d{1,2}/\d{1,2}(?:/\d{2,4})?)\s*[.!?]*",
            message,
            re.I,
        )
    )
    codes = currency_codes(message)
    if (
        not is_exchange_query(message)
        and not currency_hint
        and not (short_date and is_exchange_query(previous))
    ):
        return None
    if currency_hint and (not codes or (len(codes) == 1 and currency_hint[1] != "BRL")):
        codes = currency_hint
    if not codes:
        codes = currency_codes(previous) if is_exchange_query(previous) else []
    foreign = next((code for code in codes if code != "BRL"), None)
    pair = "/".join(codes[:2]) if len(codes) >= 2 else f"{foreign}/BRL" if foreign else ""
    sides = re.split(r"\s+(?:para|to|a)\s+|/", message, maxsplit=1, flags=re.I)
    if len(sides) == 2:
        left, right = currency_codes(sides[0]), currency_codes(sides[1])
        if left and right:
            pair = f"{left[0]}/{right[0]}"
    requested = today
    latest = True
    if re.search(r"\b(?:ontem|yesterday|ayer)\b", message, re.I):
        requested, latest = today - timedelta(days=1), False
    explicit = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", message)
    if explicit:
        year = int(explicit[3]) if explicit[3] else today.year
        year = year + 2000 if year < 100 else year
        try:
            requested = date(year, int(explicit[2]), int(explicit[1]))
        except ValueError:
            return {"pair": pair, "invalid_date": True}
        latest = False
    return {"pair": pair, "date": requested.isoformat(), "latest": latest}


def public_exchange_query(request: dict) -> str:
    return f"exchange rate {request['pair']} Banco Central PTAX reference date {request['date']}; " + (
        "latest published quotation with its actual date" if request["latest"] else "exact requested date"
    )


def lookup_ptax(request: dict, language: str = "pt"):
    supported = {"USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "DKK", "NOK", "SEK"}
    base, _, quote = request.get("pair", "").partition("/")
    if base in supported | {"BRL"} and quote in supported and not request.get("invalid_date"):
        return lookup_cross_ptax(request, language)
    if request.get("pair") not in {f"{code}/BRL" for code in supported} or request.get("invalid_date"):
        return None
    end = date.fromisoformat(request["date"])
    start = end - timedelta(days=14) if request["latest"] else end
    params = {
        "@moeda": f"'{request['pair'][:3]}'",
        "@dataInicial": f"'{start:%m-%d-%Y}'",
        "@dataFinalCotacao": f"'{end:%m-%d-%Y}'",
        "$format": "json",
        "$top": "100",
        "$select": "cotacaoCompra,cotacaoVenda,dataHoraCotacao,tipoBoletim",
    }
    try:
        response = httpx.get(PTAX_URL, params=params, timeout=8, follow_redirects=False)
        response.raise_for_status()
        rows = sorted(response.json()["value"], key=lambda row: row["dataHoraCotacao"], reverse=True)
        for row in rows:
            stamp = datetime.fromisoformat(row["dataHoraCotacao"])
            buy, sell = Decimal(str(row["cotacaoCompra"])), Decimal(str(row["cotacaoVenda"]))
            if not (start <= stamp.date() <= end):
                continue
            if row.get("tipoBoletim") != "Fechamento":
                continue
            if not all(value.is_finite() and value > 0 for value in (buy, sell)):
                continue
            shown = stamp.strftime("%d/%m/%Y %H:%M")
            amounts = f"compra R$ {buy:.4f}; venda R$ {sell:.4f}".replace(".", ",")
            answer = (
                f"PTAX {request['pair']} — Banco Central, fechamento de {shown}: {amounts} [1]. "
                "Esta é uma cotação de referência, não uma taxa aplicada pela Getnet."
            )
            if language == "en":
                answer = f"BCB PTAX {request['pair']}, closing quotation on {shown}: buy BRL {buy:.4f}; sell BRL {sell:.4f} [1]. This is a reference rate, not a Getnet rate."
            elif language == "es":
                answer = f"PTAX {request['pair']} del Banco Central, cierre del {shown}: compra BRL {buy:.4f}; venta BRL {sell:.4f} [1]. Es una cotización de referencia, no una tasa de Getnet."
            if stamp.date() != end:
                answer += {
                    "en": " The requested day's closing rate is unavailable; this is the latest published closing quotation.",
                    "es": " El cierre del día solicitado no está disponible; este es el último cierre publicado.",
                }.get(
                    language,
                    " O fechamento do dia solicitado não está disponível; este é o último fechamento publicado.",
                )
            return answer, [
                {
                    "id": 1,
                    "title": "Banco Central do Brasil — PTAX",
                    "url": str(response.url),
                    "kind": "web",
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                }
            ]
    except (httpx.HTTPError, ValueError, KeyError, TypeError, InvalidOperation):
        return None
    return None


def lookup_cross_ptax(request: dict, language: str):
    """Indicative conversion from sell references with exactly matching closing timestamps."""
    base, quote = request["pair"].split("/")
    end = date.fromisoformat(request["date"])
    start = end - timedelta(days=14) if request["latest"] else end
    rates, sources = {}, []
    try:
        for code in dict.fromkeys([base, quote]):
            if code == "BRL":
                continue
            response = httpx.get(
                PTAX_URL,
                params={
                    "@moeda": f"'{code}'",
                    "@dataInicial": f"'{start:%m-%d-%Y}'",
                    "@dataFinalCotacao": f"'{end:%m-%d-%Y}'",
                    "$format": "json",
                    "$top": "100",
                    "$select": "cotacaoVenda,dataHoraCotacao,tipoBoletim",
                },
                timeout=8,
                follow_redirects=False,
            )
            response.raise_for_status()
            rates[code] = {}
            for row in response.json()["value"]:
                stamp = datetime.fromisoformat(row["dataHoraCotacao"])
                value = Decimal(str(row["cotacaoVenda"]))
                if (
                    row["tipoBoletim"] == "Fechamento"
                    and start <= stamp.date() <= end
                    and value.is_finite()
                    and value > 0
                ):
                    rates[code][stamp] = value
            sources.append(
                {
                    "id": len(sources) + 1,
                    "title": f"Banco Central do Brasil — PTAX {code}",
                    "url": str(response.url),
                    "kind": "web",
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        common = set.intersection(*(set(values) for values in rates.values()))
        if not common:
            return None
        stamp = max(common)
        numerator = Decimal(1) if base == "BRL" else rates[base][stamp]
        result = numerator / rates[quote][stamp]
        refs = "".join(f"[{source['id']}]" for source in sources)
        shown = stamp.strftime("%d/%m/%Y %H:%M")
        note = {
            "en": "Indicative cross rate calculated from BCB PTAX sell references at the same closing timestamp; not a retail or Getnet rate.",
            "es": "Conversión indicativa calculada con referencias de venta PTAX del mismo cierre; no es una tasa comercial ni de Getnet.",
        }.get(
            language,
            "Conversão indicativa calculada com referências de venda PTAX do mesmo fechamento; não é uma taxa comercial nem da Getnet.",
        )
        answer = f"1 {base} ≈ {result:.6f} {quote} — {shown} {refs}. {note}"
        if stamp.date() != end:
            answer += {
                "en": " Latest available common closing quotation.",
                "es": " Último cierre común disponible.",
            }.get(language, " Último fechamento comum disponível, não uma cotação de hoje.")
        return answer, sources
    except (httpx.HTTPError, ValueError, KeyError, TypeError, InvalidOperation, ZeroDivisionError):
        return None
