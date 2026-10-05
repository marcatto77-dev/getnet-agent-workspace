import re
from urllib.parse import urlparse

EXCHANGE = re.compile(
    r"\b(?:c[aâ]mbio|exchange rate|currency conversion|tipo de cambio|cotiza[cç][aãóo]o?n?|"
    r"cota[cç][aã]o|euro|d[oó]lar|usd|eur)\b",
    re.I,
)
EXCHANGE_DOMAINS = ("bcb.gov.br", "ecb.europa.eu")


def is_exchange_query(text: str) -> bool:
    return bool(EXCHANGE.search(text))


def allowed_url(url: str, domains: tuple[str, ...], allow_general: bool = False) -> bool:
    if allow_general:
        return url.startswith("https://")
    try:
        host = (urlparse(url).hostname or "").casefold()
    except ValueError:
        return False
    return any(host == domain or host.endswith("." + domain) for domain in domains)
