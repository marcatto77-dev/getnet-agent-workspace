import re

from .scope import allowed_url

CANARY = "GETNET-GUARD-CANARY-9F3A"
INTERNAL = re.compile(r"\b(?:previsto_demo|cliente_nao_localizado|system prompt|developer message)\b", re.I)
UNVERIFIED_ACTION = re.compile(
    r"\b(?:já bloqueei|já estornei|já cancelei|alterei sua taxa|liberei o pagamento)\b", re.I
)
URL = re.compile(r"https://[^\s)\]]+")


def inspect_output(
    text: str, domains: tuple[str, ...], allow_general_web: bool = False
) -> tuple[bool, str, str]:
    if CANARY in text:
        return (
            False,
            "output_canary",
            "Não posso fornecer instruções internas. Posso ajudar com produtos e atendimento Getnet.",
        )
    if INTERNAL.search(text):
        return (
            False,
            "internal_value",
            "Não consegui apresentar essa resposta com segurança. Posso encaminhar para um técnico.",
        )
    if UNVERIFIED_ACTION.search(text):
        return (
            False,
            "unverified_action",
            "Não posso afirmar uma ação que não foi confirmada. Posso orientar ou chamar um técnico.",
        )
    if any(not allowed_url(url.rstrip(".,"), domains, allow_general_web) for url in URL.findall(text)):
        return (
            False,
            "unapproved_url",
            "Não consegui confirmar essa resposta somente com fontes oficiais da Getnet. Posso encaminhar você para um técnico.",
        )
    return True, "output_ok", text
