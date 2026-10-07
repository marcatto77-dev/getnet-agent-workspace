"""Currency slots, not a restriction on which public rates may be searched."""

import re
import unicodedata

ALIASES = {
    "USD": [
        "dolar americano",
        "dolar dos estados unidos",
        "us dollar",
        "dolar",
        "dolares",
        "dollar",
        "dollars",
    ],
    "EUR": ["euro", "euros"],
    "BRL": ["real brasileiro", "reais", "real"],
    "ARS": ["peso argentino", "pesos argentinos", "argentine peso"],
    "GBP": ["libra esterlina", "british pound", "pound sterling", "libra", "libras"],
    "JPY": ["iene japones", "iene", "yen", "japanese yen"],
    "CNY": ["yuan chines", "yuan", "renminbi"],
    "CHF": ["franco suico", "swiss franc"],
    "CAD": ["dolar canadense", "canadian dollar"],
    "AUD": ["dolar australiano", "australian dollar"],
    "NZD": ["dolar neozelandes", "new zealand dollar"],
    "CLP": ["peso chileno", "chilean peso"],
    "COP": ["peso colombiano", "colombian peso"],
    "MXN": ["peso mexicano", "mexican peso"],
    "UYU": ["peso uruguaio", "uruguayan peso"],
    "PYG": ["guarani paraguaio", "guarani"],
    "PEN": ["sol peruano", "nuevo sol"],
    "BOB": ["boliviano"],
    "INR": ["rupia indiana", "indian rupee"],
    "RUB": ["rublo russo", "rublo", "russian ruble"],
    "KRW": ["won sul coreano", "won coreano", "south korean won"],
    "TRY": ["lira turca", "turkish lira"],
    "ZAR": ["rand sul africano", "rand"],
    "DKK": ["coroa dinamarquesa", "danish krone"],
    "NOK": ["coroa norueguesa", "norwegian krone"],
    "SEK": ["coroa sueca", "swedish krona"],
    "MNT": ["tugrik", "tugrug", "togrog"],
}
# Less common currencies are resolved by the Router's validated ISO slots.
ISO_CODES = set(
    "AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND BOB BRL BSD BTN BWP BYN BZD CAD CDF CHF CLP CNY COP CRC CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD HKD HNL HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SOS SRD SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD UYU UZS VES VND VUV WST XAF XCD XOF XPF YER ZAR ZMW ZWG".split()
)


def normalize_currency(text):
    return "".join(
        c for c in unicodedata.normalize("NFD", text.casefold()) if unicodedata.category(c) != "Mn"
    )


AMBIGUOUS_CODES = {"ALL", "ANG", "BOB", "CUP", "MAD", "PEN", "TOP", "TRY", "SOS"}
WORDS = {normalize_currency(alias): code for code, aliases in ALIASES.items() for alias in aliases}
WORDS.update({code.casefold(): code for code in ISO_CODES - AMBIGUOUS_CODES})
CURRENCY_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(word) for word in sorted(WORDS, key=len, reverse=True)) + r")\b"
)


def currency_codes(text):
    matches = [
        (match.start(), WORDS[match.group()]) for match in CURRENCY_PATTERN.finditer(normalize_currency(text))
    ]
    matches += [
        (match.start(), match.group())
        for match in re.finditer(r"\b[A-Z]{3}\b", text)
        if match.group() in AMBIGUOUS_CODES
    ]
    return list(dict.fromkeys(code for _, code in sorted(matches)))
