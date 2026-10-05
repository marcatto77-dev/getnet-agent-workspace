import secrets

from .administration import audit
from .auth import hash_password
from .db import connection


def export_customer_data(customer_id: str) -> dict:
    with connection() as conn:
        customer = conn.execute(
            "SELECT id,external_id,nome,email,telefone,is_active,created_at,updated_at FROM customers WHERE id=%s",
            (customer_id,),
        ).fetchone()
        if not customer:
            raise LookupError("Cliente não localizado.")
        terminals = conn.execute(
            "SELECT id,model,status,last_seen_at,serial_number,apelido,installed_at FROM terminals WHERE customer_id=%s",
            (customer_id,),
        ).fetchall()
        conversations = conn.execute(
            "SELECT id,status,started_at,closed_at FROM conversations WHERE customer_id=%s ORDER BY started_at",
            (customer_id,),
        ).fetchall()
        messages = conn.execute(
            "SELECT m.conversation_id,m.sender_type,m.content,m.created_at FROM messages m JOIN conversations c ON c.id=m.conversation_id WHERE c.customer_id=%s ORDER BY m.created_at",
            (customer_id,),
        ).fetchall()
    return {
        "customer": customer,
        "terminals": terminals,
        "conversations": conversations,
        "messages": messages,
    }


def anonymize_customer(actor_id: int, customer_id: str) -> dict:
    with connection() as conn:
        customer = conn.execute("SELECT id FROM customers WHERE id=%s FOR UPDATE", (customer_id,)).fetchone()
        if not customer:
            raise LookupError("Cliente não localizado.")
        conn.execute(
            "UPDATE messages SET content='[CONTEÚDO ANONIMIZADO]',sender_id=NULL WHERE conversation_id IN (SELECT id FROM conversations WHERE customer_id=%s)",
            (customer_id,),
        )
        conn.execute("DELETE FROM receivables WHERE customer_id=%s", (customer_id,))
        conn.execute(
            "UPDATE terminals SET customer_id=NULL,apelido=NULL WHERE customer_id=%s", (customer_id,)
        )
        conn.execute(
            "UPDATE users SET username=%s,display_name='Cliente anonimizado',password_hash=%s,is_active=false,token_version=token_version+1,updated_at=now() WHERE customer_id=%s",
            (f"anon-{secrets.token_hex(8)}", hash_password(secrets.token_urlsafe(32)), customer_id),
        )
        conn.execute(
            "UPDATE customers SET nome='Cliente anonimizado',email=NULL,telefone=NULL,contato=NULL,is_active=false,updated_at=now() WHERE id=%s",
            (customer_id,),
        )
        audit(conn, actor_id, "customer.anonymized", "customer", customer_id, {"scope": "personal_data"})
    return {"customer_id": customer_id, "status": "anonymized"}


def apply_retention(days: int, action: str = "anonymize") -> int:
    if days < 1:
        raise ValueError("Retenção deve ser de ao menos um dia.")
    with connection() as conn:
        conn.execute("DELETE FROM login_rate_limits WHERE updated_at < now() - interval '7 days'")
        conn.execute("DELETE FROM request_rate_limits WHERE updated_at < now() - interval '7 days'")
        if action == "delete":
            rows = conn.execute(
                "DELETE FROM messages WHERE created_at < now()-(%s * interval '1 day') RETURNING id", (days,)
            ).fetchall()
        else:
            rows = conn.execute(
                "UPDATE messages SET content='[CONTEÚDO EXPIRADO]',sender_id=NULL WHERE created_at < now()-(%s * interval '1 day') AND content NOT IN ('[CONTEÚDO EXPIRADO]','[CONTEÚDO ANONIMIZADO]') RETURNING id",
                (days,),
            ).fetchall()
    return len(rows)
