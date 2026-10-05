import json
from datetime import date, datetime, timezone

from .db import connection


def customer_exists(user_id: str) -> bool:
    with connection() as conn:
        return (
            conn.execute(
                "SELECT id FROM customers WHERE external_id=%s AND demo=true AND is_active=true", (user_id,)
            ).fetchone()
            is not None
        )


def get_customer_profile(user_id: str):
    with connection() as conn:
        return conn.execute(
            "SELECT external_id,nome,contato,plan,demo FROM customers WHERE external_id=%s", (user_id,)
        ).fetchone()


STATUS_LABELS = {"previsto_demo": "previsto para", "paid": "pago", "pending": "pendente"}
SOURCE_LABELS = {
    "get_receivables": "Seus recebíveis",
    "get_terminal_status": "Status da sua maquininha",
    "get_customer_profile": "Seu cadastro",
    "list_customer_terminals": "Suas maquininhas",
}


def friendly_receivable_status(status: str) -> str:
    return STATUS_LABELS.get(status, status.replace("_", " "))


def get_receivables(user_id: str, reference_date: date | None = None):
    query = (
        "SELECT sale_date,expected_date,amount,currency,status FROM receivables "
        "WHERE customer_id=(SELECT id FROM customers WHERE external_id=%s) "
    )
    if reference_date:
        query += "AND sale_date=%s "
    query += "ORDER BY sale_date DESC LIMIT 30"
    with connection() as conn:
        rows = conn.execute(query, (user_id, reference_date) if reference_date else (user_id,)).fetchall()
    for row in rows:
        row["status"] = friendly_receivable_status(row["status"])
    return rows


def list_customer_terminals(user_id: str):
    with connection() as conn:
        return conn.execute(
            "SELECT t.id,mm.name AS model,t.apelido,t.serial_number,t.status AS connection_status,"
            "t.last_error,t.last_seen_at AS updated_at "
            "FROM terminals t LEFT JOIN machine_models mm ON mm.id=t.model_id "
            "WHERE t.customer_id=(SELECT id FROM customers WHERE external_id=%s) ORDER BY t.id",
            (user_id,),
        ).fetchall()


def get_terminal_status(user_id: str, terminal_id: str | None = None):
    terminals = list_customer_terminals(user_id)
    if terminal_id is None:
        return terminals
    return next((terminal for terminal in terminals if terminal["id"] == terminal_id), None)


TOOLS = {
    "get_customer_profile": get_customer_profile,
    "get_receivables": get_receivables,
    "get_terminal_status": get_terminal_status,
    "list_customer_terminals": list_customer_terminals,
}


def run_tool(
    name: str,
    user_id: str,
    source_id: int,
    reference_date: date | None = None,
    terminal_id: str | None = None,
):
    # Only the application supplies user_id, never the model's tool arguments.
    value = (
        get_receivables(user_id, reference_date)
        if name == "get_receivables"
        else get_terminal_status(user_id, terminal_id)
        if name == "get_terminal_status"
        else TOOLS[name](user_id)
        if customer_exists(user_id)
        else {"status": "cliente_nao_localizado", "message": "Cliente não localizado."}
    )
    return {
        "id": source_id,
        "title": SOURCE_LABELS[name],
        "url": None,
        "kind": "customer",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "content": json.dumps(value, ensure_ascii=False, default=str),
    }
