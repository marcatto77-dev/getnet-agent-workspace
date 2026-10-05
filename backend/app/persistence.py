import json
import re
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from .db import connection

MASK = "[MASCARADO]"


def mask_sensitive(value: object) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    patterns = [
        (r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", MASK),
        (r"(?<!\d)(?:\d{3}[.\s-]?){3}\d{2}(?!\d)", MASK),
        (r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)", MASK),
        (r"(?<!\d)(?:\+?55[\s.-]?)?(?:\(?\d{2}\)?[\s.-]?)?9?\d{4}[\s.-]?\d{4}(?!\d)", MASK),
    ]
    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text[:2000]


def get_or_create_conversation(
    user_id: str, conversation_id: UUID | None = None, *, fresh: bool = False
) -> dict:
    with connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("conversation:" + user_id,))
        row = conn.execute(
            "SELECT c.id,c.status,c.selected_terminal_id,c.pending_terminal_selection FROM conversations c JOIN customers u ON u.id=c.customer_id "
            "WHERE u.external_id=%s AND c.status<>'closed' ORDER BY c.started_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        if conversation_id is not None and (not row or row["id"] != conversation_id):
            raise PermissionError("Esta conversa não está ativa para este cliente.")
        if row and fresh and row["status"] == "ai":
            conn.execute("UPDATE conversations SET status='closed',closed_at=now() WHERE id=%s", (row["id"],))
            row = None
        if row:
            failures = conn.execute(
                "SELECT count(*) AS total FROM agent_runs WHERE conversation_id=%s AND status='unavailable'",
                (row["id"],),
            ).fetchone()["total"]
            return {**row, "failure_count": failures, "is_new": False}
        customer = conn.execute("SELECT id FROM customers WHERE external_id=%s", (user_id,)).fetchone()
        if not customer:
            raise LookupError("Cliente não localizado no cadastro.")
        conversation_id = uuid4()
        conn.execute(
            "INSERT INTO conversations(id,customer_id,status) VALUES (%s,%s,'ai')",
            (conversation_id, customer["id"]),
        )
        return {
            "id": conversation_id,
            "status": "ai",
            "failure_count": 0,
            "selected_terminal_id": None,
            "pending_terminal_selection": False,
            "is_new": True,
        }


def persist_message(conversation_id: UUID, sender_type: str, sender_id: str | None, content: str):
    message_id = uuid4()
    with connection() as conn:
        conn.execute(
            "INSERT INTO messages(id,conversation_id,sender_type,sender_id,content) VALUES (%s,%s,%s,%s,%s)",
            (message_id, conversation_id, sender_type, sender_id, content),
        )
    return message_id


def conversation_memory(conversation_id: UUID) -> dict:
    """Server-built memory; history is never accepted from an HTTP caller or the LLM."""
    from .config import settings

    cfg = settings()
    try:
        UUID(str(conversation_id))
    except ValueError:
        return {"summary": "", "messages": []}
    with connection() as conn:
        row = conn.execute(
            "SELECT memory_summary FROM conversations WHERE id=%s", (conversation_id,)
        ).fetchone()
        messages = conn.execute(
            "SELECT sender_type,content FROM messages WHERE conversation_id=%s ORDER BY created_at DESC,id DESC LIMIT %s",
            (conversation_id, max(1, cfg.conversation_history_messages)),
        ).fetchall()
        assistance = conn.execute(
            "SELECT count(*) AS n FROM agent_runs WHERE conversation_id=%s "
            "AND route IN ('knowledge','support','knowledge_support') "
            "AND (agents_used ? 'Knowledge' OR agents_used ? 'Support') "
            "AND status IN ('ok','needs_clarification')",
            (conversation_id,),
        ).fetchone()["n"]
        last_run = conn.execute(
            "SELECT status FROM agent_runs WHERE conversation_id=%s ORDER BY created_at DESC,id DESC LIMIT 1",
            (conversation_id,),
        ).fetchone()
    # Keep the most recent context when the character budget is exhausted.  The
    # limit is deliberate: conversation history is untrusted prompt material,
    # not an unlimited second system prompt.
    remaining = max(1, cfg.conversation_history_chars)
    selected = []
    for item in messages:
        content = mask_sensitive(item["content"])[:1000]
        if remaining <= 0:
            break
        selected.append({"sender": item["sender_type"], "content": content[:remaining]})
        remaining -= len(content)
    history = list(reversed(selected))
    return {
        "summary": (row or {}).get("memory_summary", "")[: cfg.conversation_summary_chars],
        "messages": history,
        "assistance_count": assistance,
        "handoff_offered": bool(last_run and last_run["status"] == "needs_handoff"),
    }


def update_conversation_summary(conversation_id: UUID) -> None:
    """Bounded deterministic rolling memory; avoids an extra paid summarization call."""
    try:
        UUID(str(conversation_id))
    except ValueError:
        return
    from .config import settings

    cfg = settings()
    with connection() as conn:
        row = conn.execute(
            "SELECT memory_summary,memory_message_count FROM conversations WHERE id=%s FOR UPDATE",
            (conversation_id,),
        ).fetchone()
        count = conn.execute(
            "SELECT count(*) AS n FROM messages WHERE conversation_id=%s", (conversation_id,)
        ).fetchone()["n"]
        if count <= cfg.conversation_history_messages or count == row["memory_message_count"]:
            return
        messages = conn.execute(
            "SELECT sender_type,content FROM messages WHERE conversation_id=%s ORDER BY created_at DESC,id DESC LIMIT %s",
            (conversation_id, max(1, cfg.conversation_history_messages)),
        ).fetchall()
        lines = [
            f"{item['sender_type']}: {mask_sensitive(item['content'])[:350]}" for item in reversed(messages)
        ]
        summary = (row["memory_summary"] + "\n" + "\n".join(lines)).strip()[-cfg.conversation_summary_chars :]
        conn.execute(
            "UPDATE conversations SET memory_summary=%s,memory_message_count=%s WHERE id=%s",
            (summary, count, conversation_id),
        )


def persist_run(
    *,
    request_id: UUID,
    conversation_id: UUID,
    user_id: str,
    route: str,
    agents_used: list[str],
    status: str,
    latency_ms: int,
    tokens: dict,
    tool_calls: list[dict],
    answer: str | None = None,
    answer_sender_type: str = "ai",
    error: str | None = None,
):
    run_id = uuid4()
    with connection() as conn:
        if answer is not None:
            conn.execute(
                "INSERT INTO messages(id,conversation_id,sender_type,sender_id,content) "
                "VALUES (%s,%s,%s,%s,%s)",
                (
                    uuid4(),
                    conversation_id,
                    answer_sender_type,
                    "assistant" if answer_sender_type == "ai" else "system",
                    answer,
                ),
            )
        conn.execute(
            "INSERT INTO requests(id,customer_id,route,status,latency_ms,agents) VALUES (%s,%s,%s,%s,%s,%s)",
            (request_id, user_id, route, status, latency_ms, Jsonb(agents_used)),
        )
        conn.execute(
            "INSERT INTO agent_runs(id,request_id,conversation_id,user_id,route,agents_used,status,latency_ms,tokens,cost,error) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,%s)",
            (
                run_id,
                request_id,
                conversation_id,
                user_id,
                route,
                Jsonb(agents_used),
                status,
                latency_ms,
                Jsonb(tokens),
                mask_sensitive(error) if error else None,
            ),
        )
        for call in tool_calls:
            conn.execute(
                "INSERT INTO tool_calls(agent_run_id,tool_name,input_summary,output_summary,success,latency_ms) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (
                    run_id,
                    call["tool_name"],
                    mask_sensitive(call.get("input_summary", "")),
                    mask_sensitive(call.get("output_summary", "")),
                    call.get("success", True),
                    call.get("latency_ms", 0),
                ),
            )
    return run_id
