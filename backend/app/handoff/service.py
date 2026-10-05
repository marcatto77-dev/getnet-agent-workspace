from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID, uuid4

from ..administration import audit
from ..config import settings
from ..db import connection
from ..persistence import mask_sensitive
from .assignment import TechnicianCandidate, choose_technician, next_waiting_handoff

Reason = Literal["cliente_pediu", "baixa_confianca", "falha_nao_resolvida"]
Presence = Literal["online", "pausa", "offline"]
ASSIGNMENT_LOCK = 20260923
CLOSED_MESSAGE = (
    "Atendimento técnico encerrado. Inicie uma nova conversa para falar com a assistente virtual."
)


class HandoffConflict(ValueError):
    pass


def _event(c, hid, t, actor=None, old=None, new=None, note=""):
    safe_note = mask_sensitive(note)[:4000] if note else None
    c.execute(
        "INSERT INTO handoff_events(id,handoff_id,type,actor_id,from_technician_id,to_technician_id,note) VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (uuid4(), hid, t, actor, old, new, safe_note),
    )
    if actor:
        audit(c, actor, f"handoff.{t}", "handoff", hid, {"from": old, "to": new, "note_added": bool(note)})


def _capacity(c, tid):
    limit = settings().max_chats_per_tech
    return (
        limit == 0
        or c.execute(
            "SELECT count(*) AS n FROM handoffs WHERE technician_id=%s AND status='assigned'", (tid,)
        ).fetchone()["n"]
        < limit
    )


def _eligible(c, tid):
    row = c.execute(
        "SELECT u.id,p.status FROM users u JOIN technician_presence p ON p.user_id=u.id WHERE u.id=%s AND u.role='tecnico' AND u.is_active=true FOR UPDATE OF u,p",
        (tid,),
    ).fetchone()
    if not row or row["status"] != "online":
        raise PermissionError("Técnico precisa estar ativo e online.")
    if not _capacity(c, tid):
        raise HandoffConflict("Limite de atendimentos simultâneos atingido.")
    return row


def _candidates(c):
    people = c.execute(
        "SELECT u.id,p.status,p.last_assigned_at FROM users u JOIN technician_presence p ON p.user_id=u.id WHERE u.role='tecnico' AND u.is_active=true ORDER BY u.id FOR UPDATE OF p"
    ).fetchall()
    active = c.execute("SELECT technician_id,assigned_at FROM handoffs WHERE status='assigned'").fetchall()
    by = {}
    for r in active:
        by.setdefault(r["technician_id"], []).append(r["assigned_at"])
    return [
        TechnicianCandidate(r["id"], r["status"], tuple(by.get(r["id"], [])), r["last_assigned_at"])
        for r in people
    ]


def _result(c, hid):
    row = c.execute(
        "SELECT id,conversation_id,reason,summary,status,technician_id,created_at,waiting_since,assigned_at,claimed_at,first_response_at,closed_at,closed_by_id,close_category,resolution_note,version FROM handoffs WHERE id=%s",
        (hid,),
    ).fetchone()
    if row:
        row["queue_position"] = queue_position(hid, conn=c) if row["status"] == "waiting" else None
    return row


def _assign(c, hid, now):
    d = choose_technician(_candidates(c))
    if d.status == "waiting" or not _capacity(c, d.technician_id):
        return False
    row = c.execute(
        "UPDATE handoffs SET status='assigned',technician_id=%s,assigned_at=%s,claimed_at=%s,version=version+1 WHERE id=%s AND status='waiting' RETURNING conversation_id",
        (d.technician_id, now, now, hid),
    ).fetchone()
    if not row:
        return False
    c.execute("UPDATE technician_presence SET last_assigned_at=%s WHERE user_id=%s", (now, d.technician_id))
    c.execute("UPDATE conversations SET status='with_technician' WHERE id=%s", (row["conversation_id"],))
    _event(c, hid, "auto_assigned", new=d.technician_id)
    return True


def _assign_next(c, now):
    rows = c.execute(
        "SELECT id,waiting_since,created_at FROM handoffs WHERE status='waiting' ORDER BY waiting_since,id FOR UPDATE"
    ).fetchall()
    row = next_waiting_handoff(rows)
    return row["id"] if row and _assign(c, row["id"], now) else None


def create_handoff(conversation_id: UUID | str, reason: Reason, summary: str):
    now = datetime.now(timezone.utc)
    cid = UUID(str(conversation_id))
    with connection() as c:
        c.execute("SELECT pg_advisory_xact_lock(%s)", (ASSIGNMENT_LOCK,))
        c.execute("SELECT id FROM conversations WHERE id=%s FOR UPDATE", (cid,)).fetchone() or (
            _ for _ in ()
        ).throw(LookupError("Conversa não localizada."))
        old = c.execute(
            "SELECT id FROM handoffs WHERE conversation_id=%s AND status<>'closed' FOR UPDATE", (cid,)
        ).fetchone()
        if old:
            return _result(c, old["id"])
        hid = uuid4()
        c.execute(
            "INSERT INTO handoffs(id,conversation_id,reason,summary,status,waiting_since) VALUES (%s,%s,%s,%s,'waiting',%s)",
            (hid, cid, reason, summary[:4000], now),
        )
        c.execute("UPDATE conversations SET status='waiting' WHERE id=%s", (cid,))
        _event(c, hid, "created")
        if settings().effective_handoff_mode == "auto":
            _assign_next(c, now)
        return _result(c, hid)


def claim(hid, tid):
    now = datetime.now(timezone.utc)
    with connection() as c:
        r = c.execute("SELECT * FROM handoffs WHERE id=%s FOR UPDATE", (hid,)).fetchone()
        if not r:
            raise LookupError("Atendimento não localizado.")
        if r["status"] != "waiting":
            raise HandoffConflict("Este atendimento já foi assumido.")
        _eligible(c, tid)
        u = c.execute(
            "UPDATE handoffs SET status='assigned',technician_id=%s,assigned_at=%s,claimed_at=%s,version=version+1 WHERE id=%s AND version=%s AND status='waiting' RETURNING conversation_id",
            (tid, now, now, hid, r["version"]),
        ).fetchone()
        if not u:
            raise HandoffConflict("Este atendimento já foi assumido.")
        c.execute("UPDATE conversations SET status='with_technician' WHERE id=%s", (u["conversation_id"],))
        c.execute("UPDATE technician_presence SET last_assigned_at=%s WHERE user_id=%s", (now, tid))
        _event(c, hid, "claimed", tid, new=tid)
        return _result(c, hid)


def pull(hid, tid, reason):
    if not settings().allow_pull:
        raise PermissionError("Puxar atendimentos está desabilitado.")
    if len(reason.strip()) < 10:
        raise ValueError("Informe um motivo com ao menos 10 caracteres.")
    now = datetime.now(timezone.utc)
    with connection() as c:
        expected = c.execute("SELECT version FROM handoffs WHERE id=%s", (hid,)).fetchone()
        r = c.execute("SELECT * FROM handoffs WHERE id=%s FOR UPDATE", (hid,)).fetchone()
        if not r or not expected or r["version"] != expected["version"] or r["status"] != "assigned":
            raise HandoffConflict("Atendimento indisponível para puxar.")
        if r["technician_id"] == tid:
            raise ValueError("Não é possível puxar o próprio atendimento.")
        _eligible(c, tid)
        c.execute(
            "UPDATE handoffs SET technician_id=%s,assigned_at=%s,claimed_at=%s,version=version+1 WHERE id=%s",
            (tid, now, now, hid),
        )
        _event(c, hid, "pulled", tid, r["technician_id"], tid, reason)
        result = _result(c, hid)
        result["previous_technician_id"] = r["technician_id"]
        return result


def transfer(hid, tid, to_tid, note):
    now = datetime.now(timezone.utc)
    with connection() as c:
        expected = c.execute("SELECT version FROM handoffs WHERE id=%s", (hid,)).fetchone()
        r = c.execute("SELECT * FROM handoffs WHERE id=%s FOR UPDATE", (hid,)).fetchone()
        if not r or not expected or r["version"] != expected["version"]:
            raise HandoffConflict("O atendimento foi alterado por outro técnico.")
        if r["status"] != "assigned" or r["technician_id"] != tid:
            raise PermissionError("Apenas o técnico responsável pode encaminhar.")
        if to_tid is None:
            c.execute(
                "UPDATE handoffs SET status='waiting',technician_id=NULL,assigned_at=NULL,version=version+1 WHERE id=%s",
                (hid,),
            )
            c.execute("UPDATE conversations SET status='waiting' WHERE id=%s", (r["conversation_id"],))
            _event(c, hid, "returned_to_queue", tid, tid, None, note)
            return _result(c, hid)
        if to_tid == tid:
            raise ValueError("Escolha outro técnico ou devolva à fila.")
        _eligible(c, to_tid)
        c.execute(
            "UPDATE handoffs SET technician_id=%s,assigned_at=%s,version=version+1 WHERE id=%s",
            (to_tid, now, hid),
        )
        _event(c, hid, "transferred", tid, tid, to_tid, note)
        result = _result(c, hid)
        result["previous_technician_id"] = tid
        return result


def close_handoff(hid, resolution_note, technician_id=None, close_category="resolvido"):
    now = datetime.now(timezone.utc)
    with connection() as c:
        r = c.execute("SELECT * FROM handoffs WHERE id=%s FOR UPDATE", (hid,)).fetchone()
        if not r:
            raise LookupError("Handoff não localizado.")
        if technician_id is not None and r["technician_id"] != technician_id:
            raise PermissionError("Apenas o técnico responsável pode encerrar.")
        if r["status"] == "closed":
            raise HandoffConflict("Este atendimento já foi encerrado.")
        c.execute(
            "UPDATE handoffs SET status='closed',closed_at=%s,closed_by_id=%s,close_category=%s,resolution_note=%s,version=version+1 WHERE id=%s",
            (now, technician_id, close_category, resolution_note[:4000], hid),
        )
        c.execute(
            "UPDATE conversations SET status='closed',closed_at=%s WHERE id=%s", (now, r["conversation_id"])
        )
        message_id = uuid4()
        c.execute(
            "INSERT INTO messages(id,conversation_id,sender_type,sender_id,content,created_at) VALUES (%s,%s,'system','system',%s,%s)",
            (message_id, r["conversation_id"], CLOSED_MESSAGE, now),
        )
        _event(c, hid, "closed", technician_id, r["technician_id"], None, resolution_note)
        result = _result(c, hid)
        result["message_id"] = message_id
        return result


def close_customer_conversation(conversation_id: UUID, customer_id: str, actor_id: int):
    """Customer-owned close; never reopens a technician handoff in another chat."""
    now = datetime.now(timezone.utc)
    with connection() as c:
        c.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("conversation:" + customer_id,))
        row = c.execute(
            "SELECT c.id,c.status FROM conversations c JOIN customers u ON u.id=c.customer_id WHERE c.id=%s AND u.external_id=%s",
            (conversation_id, customer_id),
        ).fetchone()
        if not row:
            raise PermissionError("Conversa não pertence à sessão do cliente.")
        handoff = c.execute(
            "SELECT id,status,technician_id FROM handoffs WHERE conversation_id=%s AND status<>'closed' FOR UPDATE",
            (conversation_id,),
        ).fetchone()
        row = c.execute(
            "SELECT status FROM conversations WHERE id=%s FOR UPDATE", (conversation_id,)
        ).fetchone()
        if row["status"] == "closed":
            return {"conversation_id": conversation_id, "status": "closed", "handoff_id": None}
        if handoff:
            c.execute(
                "UPDATE handoffs SET status='closed',closed_at=%s,closed_by_id=%s,close_category='outro',resolution_note='Encerrado pelo cliente',version=version+1 WHERE id=%s",
                (now, actor_id, handoff["id"]),
            )
            _event(c, handoff["id"], "customer_closed", actor_id, handoff["technician_id"], None)
        message_id = uuid4()
        c.execute(
            "INSERT INTO messages(id,conversation_id,sender_type,sender_id,content,created_at) VALUES (%s,%s,'system','system','Você encerrou este atendimento.',%s)",
            (message_id, conversation_id, now),
        )
        c.execute("UPDATE conversations SET status='closed',closed_at=%s WHERE id=%s", (now, conversation_id))
        audit(
            c,
            actor_id,
            "conversation.customer_closed",
            "conversation",
            conversation_id,
            {"had_handoff": bool(handoff)},
        )
        return {
            "conversation_id": conversation_id,
            "status": "closed",
            "handoff_id": handoff["id"] if handoff else None,
            "message_id": message_id,
        }


def add_internal_note(hid, tid, text):
    with connection() as c:
        r = c.execute(
            "SELECT conversation_id,technician_id,status FROM handoffs WHERE id=%s FOR UPDATE", (hid,)
        ).fetchone()
        if not r or r["technician_id"] != tid or r["status"] != "assigned":
            raise PermissionError("Atendimento não atribuído a este técnico.")
        c.execute(
            "INSERT INTO messages(id,conversation_id,sender_type,sender_id,content,visibility) VALUES (%s,%s,'technician',%s,%s,'internal')",
            (uuid4(), r["conversation_id"], str(tid), text[:3000]),
        )
        _event(c, hid, "note_added", tid, note=text)
        return {"ok": True}


def queue_position(hid, *, conn=None):
    def q(c):
        r = c.execute("SELECT waiting_since,id,status FROM handoffs WHERE id=%s", (hid,)).fetchone()
        return (
            c.execute(
                "SELECT count(*) AS n FROM handoffs WHERE status='waiting' AND (waiting_since,id)<= (%s,%s)",
                (r["waiting_since"], r["id"]),
            ).fetchone()["n"]
            if r and r["status"] == "waiting"
            else None
        )

    if conn:
        return q(conn)
    with connection() as c:
        return q(c)


def active_handoff_for_conversation(cid):
    with connection() as c:
        r = c.execute(
            "SELECT id FROM handoffs WHERE conversation_id=%s AND status<>'closed'", (cid,)
        ).fetchone()
        return _result(c, r["id"]) if r else None


def service_center_counts(technician_id=None, *, conn=None):
    """Canonical live handoff counters shared by Central and dashboard."""

    def counts(c):
        rows = c.execute(
            "SELECT status,technician_id,count(*) AS total FROM handoffs WHERE status<>'closed' GROUP BY status,technician_id"
        ).fetchall()
        return {
            "queue": sum(r["total"] for r in rows if r["status"] == "waiting"),
            "in_progress": sum(r["total"] for r in rows if r["status"] == "assigned"),
            "mine": sum(
                r["total"] for r in rows if r["status"] == "assigned" and r["technician_id"] == technician_id
            ),
            "others": sum(
                r["total"] for r in rows if r["status"] == "assigned" and r["technician_id"] != technician_id
            ),
        }

    if conn:
        return counts(conn)
    with connection() as c:
        return counts(c)


def _requeue_stale(c, now):
    cutoff = now - timedelta(seconds=settings().handoff_offline_timeout_seconds)
    rows = c.execute(
        "SELECT h.id,h.conversation_id,h.technician_id FROM handoffs h JOIN technician_presence p ON p.user_id=h.technician_id WHERE h.status='assigned' AND p.status='offline' AND COALESCE(p.last_seen_at,h.assigned_at)<=%s FOR UPDATE OF h",
        (cutoff,),
    ).fetchall()
    for r in rows:
        c.execute(
            "UPDATE handoffs SET status='waiting',technician_id=NULL,assigned_at=NULL,version=version+1 WHERE id=%s",
            (r["id"],),
        )
        c.execute("UPDATE conversations SET status='waiting' WHERE id=%s", (r["conversation_id"],))
        _event(c, r["id"], "timeout_requeued", old=r["technician_id"])
    return rows


def set_technician_status(tid, status):
    now = datetime.now(timezone.utc)
    with connection() as c:
        row = c.execute(
            "SELECT u.id FROM users u JOIN technician_presence p ON p.user_id=u.id WHERE u.id=%s AND u.role='tecnico' AND u.is_active=true FOR UPDATE OF p",
            (tid,),
        ).fetchone()
        if not row:
            raise LookupError("Técnico não localizado.")
        c.execute(
            "UPDATE technician_presence SET status=%s,last_seen_at=%s WHERE user_id=%s", (status, now, tid)
        )
        assigned = (
            _assign_next(c, now)
            if status == "online" and settings().effective_handoff_mode == "auto"
            else None
        )
        return {"user_id": tid, "status": status, "assigned_handoff_id": assigned}


def reassign_stale_offline(now=None):
    now = now or datetime.now(timezone.utc)
    with connection() as c:
        rows = _requeue_stale(c, now)
        if settings().effective_handoff_mode == "auto":
            for _ in rows:
                _assign_next(c, now)
        return [r["id"] for r in rows]
