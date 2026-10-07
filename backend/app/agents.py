import json
import re
from datetime import date, datetime, timedelta
from time import perf_counter
from typing import TypedDict
from zoneinfo import ZoneInfo

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from . import prompts
from .config import settings
from .conversation_policy import offer_choices, offer_reply, policy_message
from .exchange import exchange_request, lookup_ptax, public_exchange_query
from .guardrails.scope import is_exchange_query, is_getnet_relationship_question
from .guardrails.tools import execute_readonly, validate_tool_plan
from .handoff.service import create_handoff
from .rag import catalog_question, retrieve
from .schemas import Draft, EscalationSummary, Route
from .tools import run_tool


def reference_date_for_message(message: str, today: date | None = None) -> date | None:
    today = today or datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    normalized = message.casefold()
    if "ontem" in normalized or "yesterday" in normalized or "ayer" in normalized:
        return today - timedelta(days=1)
    match = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", message)
    if not match:
        return None
    day, month = int(match.group(1)), int(match.group(2))
    year = int(match.group(3)) if match.group(3) else today.year
    if year < 100:
        year += 2000
    try:
        return date(year, month, day)
    except ValueError:
        return None


class State(TypedDict, total=False):
    message: str
    user_id: str
    route: Route
    evidence: list[dict]
    sources: list[dict]
    answer: str
    status: str
    steps: list[dict]
    handoff_token: str | None
    tool_calls: list[dict]
    conversation_id: str
    failure_count: int
    escalation_reason: str
    terminal_id: str | None
    customer_context: dict
    conversation_memory: dict
    quick_replies: list[str]
    exchange_request: dict | None


def step(state, agent, action, start):
    return state.get("steps", []) + [
        dict(agent=agent, action=action, duration_ms=int((perf_counter() - start) * 1000))
    ]


def call(state, tool_name, input_summary, output_summary, start, success=True):
    return state.get("tool_calls", []) + [
        {
            "tool_name": tool_name,
            "input_summary": input_summary,
            "output_summary": output_summary,
            "success": success,
            "latency_ms": int((perf_counter() - start) * 1000),
        }
    ]


def enforce_sources(draft: Draft, evidence):
    valid = {item["id"] for item in evidence}
    inline = set(int(x) for x in re.findall(r"\[(\d+)\]", draft.answer))
    cited = set(draft.source_ids)
    if (
        not cited.issubset(valid)
        or not inline.issubset(cited)
        or (not draft.insufficient_evidence and not cited)
    ):
        return (
            "Não consegui produzir uma resposta com referências válidas. Você pode solicitar encaminhamento.",
            [],
            True,
        )
    return draft.answer, [s for s in evidence if s["id"] in cited], draft.insufficient_evidence


def explicit_human_request(message: str) -> bool:
    if re.search(
        r"\b(?:(?:não|nao|no)\s+(?:quero|preciso|quiero|necesito)|(?:don't|do not)\s+(?:want|need))\b",
        message,
        re.I,
    ):
        return False
    return bool(
        re.search(
            r"\b(?:quero|preciso|pode|gostaria|me\s+(?:passa|transfere|encaminha))"
            r".{0,45}\b(?:t[eé]cnic[oa]|atendente|pessoa|humano)\b|"
            r"\b(?:abrir\s+(?:um\s+)?chamado|atendimento\s+humano)\b|"
            r"\b(?:want|need|can I (?:speak|talk)|connect me|transfer me|quiero|necesito|puedo hablar)\b.{0,60}\b(?:human|technician|agent|humano|t[eé]cnico|agente)\b",
            message.casefold(),
        )
    )


def empty_customer_evidence(item: dict) -> bool:
    if item.get("kind") != "customer":
        return False
    try:
        return json.loads(item.get("content", "null")) in (None, [], {})
    except (ValueError, TypeError):
        return False


def draft_needs_public_lookup(draft: Draft) -> bool:
    """Do not let a cited but explicitly unverified public answer skip fallback."""
    return draft.insufficient_evidence or bool(
        re.search(
            r"n[aã]o (?:p[oô]de|pude|foi poss[ií]vel|consegui) (?:ser )?(?:verificar|confirmar|validar)|"
            r"pode n[aã]o estar atualizada|considerada n[aã]o confi[aá]vel|"
            r"(?:could not|cannot|unable to) (?:be )?(?:verify|confirm)|"
            r"(?:may|might) (?:be outdated|not be up.to.date)|"
            r"no (?:pude|se pudo) (?:verificar|confirmar)",
            draft.answer,
            re.I,
        )
    )


def build_graph(provider):
    def router(state):
        start = perf_counter()
        # Identity probes are denied before any tool or LLM call.
        mentioned = re.findall(r"cliente\d+", state["message"], flags=re.IGNORECASE)
        if any(x.lower() != state["user_id"] for x in mentioned):
            route = Route(route="blocked", support_tools=[], search_query="", clarification="")
            calls = call(state, "policy.identity_guard", state["message"], route.model_dump(), start)
            reason = ""
        else:
            try:
                route = provider.structured(
                    prompts.ROUTER,
                    json.dumps(
                        {
                            "message": state["message"],
                            "content_classification": "USUARIO_NAO_CONFIAVEL",
                            "customer_context": state.get("customer_context", {}),
                            "conversation_memory": state.get("conversation_memory", {}),
                            "memory_classification": "HISTORICO_NAO_CONFIAVEL",
                        },
                        ensure_ascii=False,
                        default=str,
                    ),
                    Route,
                )
            except (ValidationError, ValueError, TypeError):
                route = Route(
                    route="clarify",
                    support_tools=[],
                    search_query="",
                    clarification="Não consegui classificar o pedido com segurança. Pode reformular?",
                    safety_label="prompt_injection",
                )
            memory = state.get("conversation_memory", {})
            if route.safety_label == "off_topic" and is_getnet_relationship_question(state["message"]):
                route.safety_label = "ok"
                route.route = "knowledge"
                route.support_tools = []
                route.search_query = state["message"]
            reply = offer_reply(state["message"]) if memory.get("handoff_offered") else None
            if route.safety_label != "ok":
                route.route = "blocked"
                route.support_tools = []
            elif explicit_human_request(state["message"]) or (
                memory.get("handoff_offered")
                and reply is not False
                and (reply is True or route.accepts_human_offer)
            ):
                route.route = "escalation"
                route.support_tools = []
            elif route.route == "escalation":
                # A model's low-confidence label is not evidence that RAG and the
                # official site both failed. Try the normal retrieval path first.
                route.route = "knowledge_support" if route.support_tools else "knowledge"
            if reply is False and route.route not in {"blocked", "escalation"}:
                route.route = "clarify"
                route.clarification = policy_message("continue", route.language)
                route.customer_dissatisfied = False
                route.support_tools = []
            if route.route == "knowledge_support":
                route.knowledge_source = "rag"
            currency_hint = (
                [route.currency_base, route.currency_quote or "BRL"] if route.currency_base else None
            )
            exchange = exchange_request(state["message"], memory, currency_hint=currency_hint)
            if route.route in {"knowledge", "knowledge_support"} and not exchange:
                # Getnet knowledge always tries the internal corpus before live web.
                route.knowledge_source = "rag"
            if exchange and route.route not in {"blocked", "escalation"}:
                route.support_tools = []
                route.customer_dissatisfied = False
                if not exchange.get("pair") or exchange.get("invalid_date"):
                    route.route = "clarify"
                    route.clarification = policy_message(
                        "exchange_date" if exchange.get("invalid_date") else "exchange_pair",
                        route.language,
                    )
                else:
                    route.route = "knowledge"
                    route.knowledge_source = "web"
                    route.search_query = public_exchange_query(exchange)
            if (
                route.route not in {"blocked", "escalation"}
                and route.customer_dissatisfied
                and memory.get("assistance_count", 0) >= 3
            ):
                route.route = "clarify"
                route.clarification = policy_message("offer", route.language)
                route.support_tools = []
                return {
                    "route": route,
                    "sources": [],
                    "evidence": [],
                    "handoff_token": None,
                    "status": "needs_handoff",
                    "tool_calls": call(
                        state,
                        "policy.human_offer",
                        {},
                        {"assistance_count": memory["assistance_count"]},
                        start,
                    ),
                    "quick_replies": offer_choices(route.language),
                    "steps": step(
                        state, "Router", "Oferta de humano após três respostas; aguarda aceite", start
                    ),
                }
            calls = call(state, "llm.router", state["message"], route.model_dump(), start)
            reason = "cliente_pediu" if route.route == "escalation" else ""
        return {
            "route": route,
            "exchange_request": exchange_request(state["message"], state.get("conversation_memory", {})),
            "evidence": [],
            "sources": [],
            "handoff_token": None,
            "tool_calls": calls,
            "escalation_reason": reason,
            "steps": step(state, "Router", "Rota selecionada: " + route.route, start),
        }

    def knowledge(state):
        start = perf_counter()
        route = state["route"]
        # The Router may shorten "quais são todos os modelos" to a generic
        # product query, losing the list intent needed for corpus diversity.
        query = (
            state["message"] if catalog_question(state["message"]) else route.search_query or state["message"]
        )
        context = state.get("customer_context", {})
        selected_id = context.get("selected_terminal_id")
        selected = next(
            (item for item in context.get("terminals", []) if item.get("id") == selected_id), None
        )
        if (
            route.knowledge_source != "web"
            and route.route == "knowledge_support"
            and selected
            and selected.get("model")
            and selected["model"].casefold() not in query.casefold()
        ):
            query = f"{query} modelo {selected['model']}"
        if route.knowledge_source == "web":
            request = state.get("exchange_request")
            ptax = lookup_ptax(request, route.language) if request and request.get("pair") else None
            if ptax:
                answer, sources = ptax
                return {
                    "answer": answer,
                    "sources": sources,
                    "status": "ok",
                    "tool_calls": call(state, "bcb_ptax", request, {"sources": sources}, start),
                    "steps": step(
                        state, "Knowledge", "Cotação pública consultada na API PTAX do Banco Central", start
                    ),
                }
            query += f". Response language: {route.language}"
            answer, sources = provider.web(query)
            return {
                "answer": answer,
                "sources": sources,
                "status": "ok" if sources else "needs_escalation",
                "escalation_reason": "" if sources else "baixa_confianca",
                "tool_calls": call(
                    state,
                    "web_search",
                    route.search_query or state["message"],
                    {"answer": answer, "sources": sources},
                    start,
                ),
                "steps": step(state, "Knowledge", "Busca web com fontes atuais", start),
            }
        evidence = retrieve(query, provider)
        return {
            "evidence": evidence,
            "tool_calls": call(
                state,
                "rag.retrieve",
                query,
                {"chunks": len(evidence), "ids": [item.get("chunk_id") for item in evidence]},
                start,
            ),
            "steps": step(state, "Knowledge", f"RAG: {len(evidence)} trechos recuperados", start),
        }

    def support(state):
        start = perf_counter()
        evidence = list(state.get("evidence", []))
        names = validate_tool_plan("Support", list(state["route"].support_tools))
        calls = list(state.get("tool_calls", []))
        for name in names:
            tool_start = perf_counter()
            reference_date = (
                reference_date_for_message(state["message"]) if name == "get_receivables" else None
            )
            result = execute_readonly(
                run_tool,
                name,
                state["user_id"],
                len(evidence) + 1,
                reference_date,
                state.get("terminal_id"),
                timeout=settings().guardrail_tool_timeout_seconds,
            )
            evidence.append(result)
            calls = calls + [
                {
                    "tool_name": name,
                    "input_summary": {
                        "user_id": state["user_id"],
                        "reference_date": reference_date.isoformat() if reference_date else None,
                        "terminal_id": state.get("terminal_id"),
                    },
                    "output_summary": result.get("content", ""),
                    "success": True,
                    "latency_ms": int((perf_counter() - tool_start) * 1000),
                }
            ]
        if names and all(empty_customer_evidence(item) for item in evidence):
            query = state["route"].search_query or state["message"]
            public = retrieve(query, provider)
            for item in public:
                item = dict(item)
                item["id"] = len(evidence) + 1
                evidence.append(item)
            calls = call({"tool_calls": calls}, "rag.retrieve", query, {"chunks": len(public)}, start)
        return {
            "evidence": evidence,
            "tool_calls": calls,
            "steps": step(state, "Support", "Ferramentas: " + ", ".join(names), start),
        }

    def compose(state):
        start = perf_counter()
        evidence = state.get("evidence", [])
        if not evidence:
            return {
                "answer": "Ainda não tenho evidências suficientes na base para responder. "
                "A base pode estar vazia ou não cobrir este assunto.",
                "sources": [],
                "status": "needs_escalation",
                "escalation_reason": "baixa_confianca",
                "steps": step(state, "Knowledge", "Sem evidências disponíveis", start),
            }
        if (
            state["route"].route == "knowledge"
            and catalog_question(state["message"])
            and state["route"].language == "pt"
        ):
            manuals = []
            seen_models = set()
            for item in evidence:
                match = re.fullmatch(r"Manual oficial (Get [^—]+) — Getnet", item.get("title", ""))
                if (
                    match
                    and item.get("kind") == "rag"
                    and (item.get("url") or "").startswith("https://site.getnet.com.br/")
                    and match.group(1).strip() not in seen_models
                ):
                    manuals.append((match.group(1).strip(), item))
                    seen_models.add(match.group(1).strip())
            if len(manuals) >= 2:
                cited = [item for _, item in manuals]
                answer = (
                    "Encontrei manuais oficiais da Getnet para estes modelos: "
                    + ", ".join(f"{name} [{item['id']}]" for name, item in manuals)
                    + ". Esses são os modelos documentados na base; os manuais não confirmam "
                    "que essa seja a lista completa nem que todos estejam à venda hoje."
                )
                return {
                    "answer": answer,
                    "sources": cited,
                    "status": "ok",
                    "escalation_reason": "",
                    "tool_calls": call(
                        state,
                        "policy.catalog_evidence",
                        state["message"],
                        {"source_ids": [item["id"] for item in cited]},
                        start,
                    ),
                    "steps": step(
                        state, "Knowledge", "Modelos citados diretamente dos manuais oficiais", start
                    ),
                }
        is_support = state["route"].route in ("support", "knowledge_support")
        prompt = prompts.SUPPORT if is_support else prompts.KNOWLEDGE
        prompt += "\n\n" + prompts.RESPONSE_LANGUAGE.format(language=state["route"].language)
        payload = json.dumps(
            {
                "message": state["message"],
                "content_classification": "USUARIO_NAO_CONFIAVEL",
                "evidence": evidence,
                "response_language": state["route"].language,
                "evidence_classification": "EVIDENCIA_NAO_CONFIAVEL",
                "today": datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat(),
                "conversation_memory": state.get("conversation_memory", {}),
                "memory_classification": "HISTORICO_NAO_CONFIAVEL",
            },
            ensure_ascii=False,
        )
        draft = provider.structured(prompt, payload, Draft)
        answer, sources, insufficient = enforce_sources(draft, evidence)
        if state["route"].route == "knowledge":
            insufficient = insufficient or draft_needs_public_lookup(draft)
        return {
            "answer": answer,
            "sources": sources,
            "status": "needs_escalation" if insufficient else "ok",
            "escalation_reason": "baixa_confianca" if insufficient else "",
            "tool_calls": call(
                state,
                "llm.compose",
                payload,
                {
                    "answer": answer,
                    "source_ids": [item["id"] for item in sources],
                    "insufficient": insufficient,
                },
                start,
            ),
            "steps": step(
                state, "Support" if is_support else "Knowledge", "Resposta fundamentada nas evidências", start
            ),
        }

    def official_web_fallback(state):
        start = perf_counter()
        route = state["route"]
        # Only public topic terms leave the application. Customer identity and
        # personal tool output never become search inputs.
        query = route.search_query or state["message"]
        query = re.sub(r"\bcliente\w+\b", "", query, flags=re.IGNORECASE).strip()
        query = f"site:site.getnet.com.br Getnet Brasil {query}"[:300]
        query += f". Response language: {route.language}"
        answer, sources = provider.web(query)
        calls = call(state, "web_search", query, {"answer": answer, "sources": sources}, start)
        if sources:
            missing_personal = any(empty_customer_evidence(item) for item in state.get("evidence", []))
            if missing_personal:
                answer = policy_message("personal_missing", route.language) + answer
            return {
                "answer": answer,
                "sources": sources,
                "status": "ok",
                "escalation_reason": "",
                "tool_calls": calls,
                "steps": step(state, "Knowledge", "Busca complementar no site oficial", start),
            }
        return {
            "tool_calls": calls,
            "status": "needs_escalation",
            "escalation_reason": "baixa_confianca",
            "steps": step(state, "Knowledge", "Sem resposta verificável no site oficial", start),
        }

    def escalation(state):
        start = perf_counter()
        calls = list(state.get("tool_calls", []))
        context = []
        for name in ("get_customer_profile", "get_terminal_status"):
            tool_start = perf_counter()
            result = execute_readonly(
                run_tool,
                name,
                state["user_id"],
                len(context) + 1,
                None,
                state.get("terminal_id"),
                timeout=settings().guardrail_tool_timeout_seconds,
            )
            context.append(result)
            calls.append(
                {
                    "tool_name": name,
                    "input_summary": {"user_id": state["user_id"], "terminal_id": state.get("terminal_id")},
                    "output_summary": result.get("content", ""),
                    "success": True,
                    "latency_ms": int((perf_counter() - tool_start) * 1000),
                }
            )
        payload = json.dumps(
            {
                "message": state["message"],
                "reason": state.get("escalation_reason") or "cliente_pediu",
                "customer": context[0]["content"],
                "terminal": context[1]["content"],
                "attempts": [item["action"] for item in state.get("steps", [])],
                "conversation_memory": state.get("conversation_memory", {}),
                "memory_classification": "HISTORICO_NAO_CONFIAVEL",
            },
            ensure_ascii=False,
        )
        summary_start = perf_counter()
        summary = provider.structured(prompts.ESCALATION, payload, EscalationSummary)
        summary.reason = state.get("escalation_reason") or summary.reason
        calls.append(
            {
                "tool_name": "llm.escalation",
                "input_summary": payload,
                "output_summary": summary.model_dump(),
                "success": True,
                "latency_ms": int((perf_counter() - summary_start) * 1000),
            }
        )
        handoff = create_handoff(state["conversation_id"], summary.reason, summary.model_dump_json())
        response_status = "with_technician" if handoff["status"] == "assigned" else "waiting"
        answer = policy_message(
            "assigned" if response_status == "with_technician" else "queue",
            state["route"].language,
        ).format(position=handoff.get("queue_position", 1))
        calls = calls + [
            {
                "tool_name": "handoff.create",
                "input_summary": {"conversation_id": state["conversation_id"], "reason": summary.reason},
                "output_summary": {"handoff_id": str(handoff["id"]), "status": handoff["status"]},
                "success": True,
                "latency_ms": int((perf_counter() - start) * 1000),
            }
        ]
        return {
            "answer": answer,
            "status": response_status,
            "handoff_token": None,
            "sources": [],
            "tool_calls": calls,
            "steps": step(state, "Escalation", "Handoff automático criado", start),
        }

    def finish_simple(state):
        blocked = state["route"].route == "blocked"
        return {
            "answer": policy_message("scope", state["route"].language)
            if blocked
            else state["route"].clarification or "Como posso ajudar com seu atendimento?",
            "status": "blocked" if blocked else state.get("status", "needs_clarification"),
            "sources": [],
        }

    def unresolved(state):
        return {
            "answer": policy_message(
                "missing_exchange"
                if is_exchange_query(state["route"].search_query) and state["route"].knowledge_source == "web"
                else "missing",
                state["route"].language,
            ),
            "status": "needs_clarification",
            "sources": [],
            "escalation_reason": "",
        }

    graph = StateGraph(State)
    for name, fn in [
        ("router", router),
        ("knowledge", knowledge),
        ("support", support),
        ("compose", compose),
        ("official_web_fallback", official_web_fallback),
        ("escalation", escalation),
        ("simple", finish_simple),
        ("unresolved", unresolved),
    ]:
        graph.add_node(name, fn)
    graph.add_edge(START, "router")
    graph.add_conditional_edges(
        "router",
        lambda s: {
            "knowledge": "knowledge",
            "knowledge_support": "knowledge",
            "support": "support",
            "clarify": "simple",
            "blocked": "simple",
            "escalation": "escalation",
        }[s["route"].route],
    )
    graph.add_conditional_edges(
        "knowledge",
        lambda s: (
            "unresolved"
            if s.get("status") == "needs_escalation"
            else END
            if s["route"].knowledge_source == "web"
            else "support"
            if s["route"].route == "knowledge_support"
            else "compose"
        ),
    )
    graph.add_edge("support", "compose")
    graph.add_conditional_edges(
        "compose", lambda s: "official_web_fallback" if s.get("status") == "needs_escalation" else END
    )
    graph.add_conditional_edges(
        "official_web_fallback", lambda s: "unresolved" if s.get("status") == "needs_escalation" else END
    )
    for name in ("simple", "escalation", "unresolved"):
        graph.add_edge(name, END)
    return graph.compile()
