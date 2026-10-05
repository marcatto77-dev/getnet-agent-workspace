import json
from uuid import UUID

from .db import connection
from .tools import get_customer_profile, get_receivables, get_terminal_status


def conversation_belongs_to_customer(conversation_id: UUID | str, customer_id: str) -> bool:
    with connection() as conn:
        return (
            conn.execute(
                "SELECT 1 FROM conversations c JOIN customers u ON u.id=c.customer_id "
                "WHERE c.id=%s AND u.external_id=%s",
                (conversation_id, customer_id),
            ).fetchone()
            is not None
        )


def technician_owns_conversation(conversation_id: UUID | str, technician_id: int) -> bool:
    with connection() as conn:
        return (
            conn.execute(
                "SELECT 1 FROM handoffs WHERE conversation_id=%s AND technician_id=%s",
                (conversation_id, technician_id),
            ).fetchone()
            is not None
        )


def list_conversations(technician_id: int) -> list[dict]:
    with connection() as conn:
        return conn.execute(
            "SELECT c.id,c.status,c.started_at,c.closed_at,c.selected_terminal_id,u.external_id,u.nome,h.id AS handoff_id,"
            "h.reason,h.status AS handoff_status,h.created_at,h.assigned_at,h.closed_at AS handoff_closed_at "
            "FROM handoffs h JOIN conversations c ON c.id=h.conversation_id "
            "JOIN customers u ON u.id=c.customer_id WHERE h.technician_id=%s "
            "ORDER BY (h.status='assigned') DESC,COALESCE(h.assigned_at,h.created_at) DESC",
            (technician_id,),
        ).fetchall()


def conversation_detail(
    conversation_id: UUID | str, technician_id: int, handoff_id: UUID | None = None
) -> dict | None:
    with connection() as conn:
        row = conn.execute(
            "SELECT c.id,c.status,c.started_at,c.closed_at,u.external_id,u.nome,h.id AS handoff_id,"
            "h.reason,h.summary,h.status AS handoff_status,h.assigned_at,h.closed_at AS handoff_closed_at,"
            "h.resolution_note,h.created_at AS handoff_created_at FROM handoffs h JOIN conversations c ON c.id=h.conversation_id "
            "JOIN customers u ON u.id=c.customer_id WHERE c.id=%s AND "
            "(h.technician_id=%s OR (h.status='closed' AND h.technician_id IS NULL AND "
            "EXISTS (SELECT 1 FROM handoff_events e WHERE e.handoff_id=h.id AND e.type='customer_closed'))) "
            "AND (%s::uuid IS NULL OR h.id=%s::uuid) ORDER BY h.created_at DESC LIMIT 1",
            (conversation_id, technician_id, handoff_id, handoff_id),
        ).fetchone()
        if not row:
            return None
        previous = conn.execute(
            "SELECT max(closed_at) AS closed_at FROM handoffs "
            "WHERE conversation_id=%s AND id<>%s AND closed_at<=%s",
            (conversation_id, row["handoff_id"], row["handoff_created_at"]),
        ).fetchone()["closed_at"]
        messages = conn.execute(
            "SELECT id,sender_type,sender_id,content,visibility,created_at FROM messages "
            "WHERE conversation_id=%s AND (%s::timestamptz IS NULL OR created_at>%s::timestamptz) "
            "AND (%s::timestamptz IS NULL OR created_at<=%s::timestamptz) ORDER BY created_at,id",
            (conversation_id, previous, previous, row["handoff_closed_at"], row["handoff_closed_at"]),
        ).fetchall()
    try:
        summary = json.loads(row["summary"])
    except (json.JSONDecodeError, TypeError):
        summary = {"problem": row["summary"]}
    row["summary"] = summary
    row["messages"] = messages
    row["customer"] = get_customer_profile(row["external_id"])
    terminal = get_terminal_status(row["external_id"], row.get("selected_terminal_id"))
    row["terminals"] = [terminal] if terminal else get_terminal_status(row["external_id"])
    row["receivables"] = get_receivables(row["external_id"])
    return row
