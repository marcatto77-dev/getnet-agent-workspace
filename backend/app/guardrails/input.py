import base64
import re
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import unquote

from ..persistence import mask_sensitive

ZERO_WIDTH = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]")
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
INJECTION = re.compile(
    r"(?:ignore|ignora|desconsidere|esqueça|olvida|forget|disregard).{0,35}(?:instruções|instrucciones|instructions|regras|rules)|"
    r"\bi[\s._-]*g[\s._-]*n[\s._-]*o[\s._-]*r[\s._-]*e[\s._-]*.{0,35}(?:instruções|instrucciones|instructions|regras|rules)|"
    r"(?:revele|revela|mostre|vaze|print|show|reveal).{0,30}(?:prompt|system message|instruções internas|internal instructions|hidden instructions|credenciais|tokens secretos)|"
    r"(?:finja|aja|role.?play).{0,30}(?:admin|administrador|developer|sistema)|"
    r"(?:jailbreak|dan|modo desenvolvedor|developer mode)|"
    r"(?:system|developer|assistant)\s*:\s*(?:ignore|override|new instructions)",
    re.I | re.S,
)
COMMAND_EXECUTION = re.compile(
    r"(?:^|[.!?:]\s*)(?:(?:getnet|por favor|please|por favor,)[,:]?\s+)*"
    r"(?:(?:pode|poderia|can you|could you|puedes|podrías)\s+)?"
    r"(?:execut[ae](?:r)?|reexecut[ae](?:r)?|rod[ae](?:r)?|run|rerun|execute|ejecut[ae](?:r)?)"
    r"\b.{0,60}\b(?:comando|c[oó]digo|script|command|code|svg|instrucciones)\b|"
    r"^(?:execute|reexecute|rode|run|rerun|ejecuta)\s+(?:novamente|de novo|again|otra vez)[.!?]*$",
    re.I | re.S,
)
CODE = re.compile(
    r"```|<\s*/?\s*(?:svg|script|foreignObject)\b|^svg$|"
    r"(?:^|\s)(?:def\s+\w+\s*\(|class\s+\w+\s*[:({]|from\s+[\w.]+\s+import\s+|"
    r"import\s+[\w.]+|lambda\s+\w+\s*:|(?:exec|eval)\s*\(|"
    r"(?:const|let|var)\s+\w+\s*=|function\s+\w*\s*\(|"
    r"(?:SELECT\s+.+\s+FROM\s+|INSERT\s+INTO\s+|DROP\s+TABLE\s+)|"
    r"(?:#!/bin/(?:ba)?sh|sudo\s+|curl\s+\S+\s*\|\s*(?:sh|bash)))",
    re.I | re.S,
)
ABUSE = re.compile(r"\b(?:idiota|imbecil|burro|lixo|merda|fuck|bitch)\b", re.I)
GETNET_SCOPE = re.compile(
    r"\b(?:getnet|get smart|get cl[aá]ssica|manual|maquininha|máquina|terminal|pix|receb\w*|venda\w*|transa[cç][aã]o|cart[aã]o|"
    r"antecipa[cç][aã]o|credi[aá]rio|link de pagamento|taxa|aluguel|senha|conta|ajuda|t[eé]cnico|atendente|ol[aá]|oi|"
    r"sales?|card machine|receivables?|bank account|transactions?|installments?|payment link|support|technician|customer)\b",
    re.I,
)
UTILITY = re.compile(
    r"\b(?:clima|previs[aã]o do tempo|chover|weather|rain|llover|pron[oó]stico del tiempo)\b",
    re.I,
)
OFF_TOPIC = re.compile(
    r"\b(?:pol[ií]tica|elei[cç][aã]o|receita|bolo|programa[cç][aã]o|c[oó]digo|poema|filme|futebol|opini[aã]o)\b",
    re.I,
)
CUSTOMER_ID = re.compile(r"\bcliente\d{1,10}\b", re.I)


@dataclass
class InputDecision:
    text: str
    safety_label: str = "ok"
    block: bool = False
    rule: str = "input_ok"
    action: str = "allow"
    severity: str = "info"
    notices: list[str] = field(default_factory=list)


def normalize(value: str) -> str:
    return " ".join(CONTROL.sub("", ZERO_WIDTH.sub("", unicodedata.normalize("NFKC", value))).split())


def decoded_candidates(text: str) -> list[str]:
    """Inspect common encodings without executing or trusting their contents."""
    candidates = [text]
    for _ in range(2):
        decoded = normalize(unquote(candidates[-1]))
        if decoded == candidates[-1]:
            break
        candidates.append(decoded)
    for candidate in list(candidates):
        for token in re.findall(
            r"(?<![A-Za-z0-9+/_-])[A-Za-z0-9+/_-]{16,}={0,2}(?![A-Za-z0-9+/_=-])", candidate
        ):
            try:
                raw = base64.b64decode(
                    token.replace("-", "+").replace("_", "/") + "=" * (-len(token) % 4), validate=True
                )
                decoded = normalize(raw.decode("utf-8"))
            except (ValueError, UnicodeError):
                continue
            if decoded and len(decoded) <= 2000:
                candidates.append(decoded)
    return candidates


def _encoded_unsafe(text: str) -> tuple[bool, bool]:
    for candidate in decoded_candidates(text):
        if INJECTION.search(candidate):
            return True, False
        if CODE.search(candidate):
            return False, True
    return False, False


def inspect_input(
    value: str, current_user_id: str, off_topic_policy: str, has_context: bool = False
) -> InputDecision:
    text = normalize(value)
    if len(text) > 2000:
        return InputDecision(text[:2000], "prompt_injection", True, "input_too_long", "block", "medium")
    mentioned = {item.casefold() for item in CUSTOMER_ID.findall(text)}
    if any(item != current_user_id.casefold() for item in mentioned):
        return InputDecision(
            mask_sensitive(text), "cross_customer_request", True, "cross_customer_id", "block", "high"
        )
    if any(COMMAND_EXECUTION.search(candidate) for candidate in decoded_candidates(text)):
        return InputDecision(
            mask_sensitive(text), "prompt_injection", True, "command_execution_request", "block", "high"
        )
    injection, code = _encoded_unsafe(text)
    if injection:
        return InputDecision(
            mask_sensitive(text), "prompt_injection", True, "prompt_injection_pattern", "block", "high"
        )
    if code:
        return InputDecision(mask_sensitive(text), "off_topic", True, "code_content", "block", "medium")
    redacted = mask_sensitive(text)
    if redacted != text:
        return InputDecision(
            redacted,
            "sensitive_data",
            False,
            "sensitive_data",
            "redact",
            "high",
            [
                "Por segurança, mascarei os dados enviados. Não compartilhe CPF, cartão, telefone ou e-mail no chat."
            ],
        )
    if ABUSE.search(text):
        return InputDecision(text, "abusive", True, "abusive_language", "block", "low")
    utility = bool(UTILITY.search(text))
    if utility:
        return InputDecision(text, "off_topic", True, "strict_utility_block", "block", "low")
    # Unknown vocabulary is not proof of being off-topic, especially in other
    # languages. The Router performs semantic scope classification afterwards.
    if OFF_TOPIC.search(text) and not GETNET_SCOPE.search(text):
        return InputDecision(text, "off_topic", True, "off_topic", "block", "low")
    return InputDecision(text)
