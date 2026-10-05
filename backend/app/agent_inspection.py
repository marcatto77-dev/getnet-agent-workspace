"""Read-only, administrator-only view of the deployed agent configuration."""

import inspect

from . import prompts
from .config import settings
from .guardrails import input as input_guard
from .guardrails import output as output_guard
from .guardrails import scope, tools
from .ingest import poisoning_signals


def inspection_snapshot() -> dict:
    cfg = settings()
    descriptions = {
        "ROUTER": "Identifica assunto, idioma, ferramentas e insatisfação; seleciona os próximos agentes.",
        "KNOWLEDGE": "Consulta RAG e busca fontes oficiais para responder com referências.",
        "SUPPORT": "Consulta dados do cliente autenticado e combina os resultados com orientações oficiais.",
        "ESCALATION": "Resume o contexto e abre atendimento somente após pedido ou aceite do cliente.",
    }

    def display_source(value: str) -> str:
        return value.replace(output_guard.CANARY, "[CANÁRIO INTERNO OCULTO]")

    guards = [
        (
            "Entrada",
            "Bloqueia ataques, código e clima; mascara dados sensíveis antes do modelo.",
            inspect.getsource(input_guard),
        ),
        (
            "Fontes",
            "Getnet para produtos e suporte; Banco Central/BCE para câmbio.",
            inspect.getsource(scope),
        ),
        (
            "Ferramentas",
            "Allowlist por agente, limite de chamadas e timeout. Identidade vem da sessão.",
            inspect.getsource(tools),
        ),
        (
            "Saída",
            "Verifica canário, URLs e afirmações de ações não realizadas.",
            inspect.getsource(output_guard),
        ),
        (
            "RAG",
            "Conteúdo suspeito fica em quarentena antes dos embeddings; revisão administrativa auditada.",
            inspect.getsource(poisoning_signals),
        ),
    ]
    return {
        "read_only": True,
        "model": cfg.openai_model,
        "embedding_model": cfg.embedding_model,
        "scope": "Getnet e consultas de câmbio. Clima e outros assuntos são recusados sem encaminhamento.",
        "handoff": "Pedido explícito abre atendimento. Após três respostas de assistência e insatisfação, a IA oferece um técnico e aguarda aceite. Recusar mantém a conversa com a IA.",
        "languages": "Respostas no idioma do cliente; fluxos de política verificados em português, inglês e espanhol.",
        "agents": [
            {
                "name": name,
                "description": description,
                "prompt": display_source(
                    getattr(prompts, name)
                    + ("\n\n" + prompts.RESPONSE_LANGUAGE if name in {"KNOWLEDGE", "SUPPORT"} else "")
                ),
            }
            for name, description in descriptions.items()
        ],
        "guardrails": [
            {"name": name, "description": description, "source": display_source(source)}
            for name, description, source in guards
        ],
        "limits": {
            "tool_timeout_seconds": cfg.guardrail_tool_timeout_seconds,
            "chat_requests_per_minute": cfg.chat_requests_per_minute,
        },
    }
