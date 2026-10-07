import re
from urllib.parse import urlparse

from ..currencies import currency_codes

EXCHANGE = re.compile(
    r"\b(?:c[aâ]mbio|exchange rate|currency conversion|tipo de cambio|cotiza[cç][aãóo]o?n?|"
    r"cota[cç][aã]o|euro|d[oó]lar|usd|eur)\b",
    re.I,
)
EXCHANGE_DOMAINS = ("bcb.gov.br", "ecb.europa.eu")


def is_getnet_relationship_question(text: str) -> bool:
    # Exact, bounded question shapes: never a blanket exception for mentioning Getnet.
    return bool(
        re.fullmatch(
            r"\s*(?:qual (?:[ée] )?a (?:diferen[cç]a|rela[cç][aã]o) entre (?:a )?getnet e (?:o )?santander|"
            r"what(?:'s| is) the (?:difference|relationship) between getnet and santander|"
            r"cu[aá]l es la (?:diferencia|relaci[oó]n) entre getnet y santander)\s*[?.!]*\s*",
            text,
            re.I,
        )
    )


def is_exchange_query(text: str) -> bool:
    return bool(EXCHANGE.search(text) or any(code != "BRL" for code in currency_codes(text)))


def allowed_url(url: str, domains: tuple[str, ...], allow_general: bool = False) -> bool:
    if allow_general:
        return url.startswith("https://")
    try:
        host = (urlparse(url).hostname or "").casefold()
    except ValueError:
        return False
    return any(host == domain or host.endswith("." + domain) for domain in domains)
