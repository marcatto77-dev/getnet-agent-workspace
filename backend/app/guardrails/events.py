from uuid import UUID

from ..db import connection
from ..persistence import mask_sensitive


def record_event(
    request_id: UUID,
    conversation_id: UUID | None,
    layer: str,
    rule: str,
    action: str,
    severity: str,
    sample: object = "",
):
    with connection() as conn:
        conn.execute(
            "INSERT INTO guardrail_events(request_id,conversation_id,layer,rule,action,severity,sample) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (request_id, conversation_id, layer, rule, action, severity, mask_sensitive(sample)[:500]),
        )


def list_events(page: int, page_size: int) -> dict:
    with connection() as conn:
        total = conn.execute("SELECT count(*) AS n FROM guardrail_events").fetchone()["n"]
        rows = conn.execute(
            "SELECT id,request_id,conversation_id,layer,rule,action,severity,sample,created_at FROM guardrail_events ORDER BY created_at DESC,id DESC LIMIT %s OFFSET %s",
            (page_size, (page - 1) * page_size),
        ).fetchall()
    return {"items": rows, "total": total, "page": page, "page_size": page_size}
