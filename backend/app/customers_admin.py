from uuid import uuid4

from .administration import audit
from .auth import hash_password
from .config import settings
from .db import connection


def list_customers(search: str, page: int, page_size: int) -> dict:
    term = f"%{search}%"
    with connection() as conn:
        total = conn.execute(
            "SELECT count(*) AS n FROM customers c LEFT JOIN users u ON u.customer_id=c.id "
            "WHERE c.id ILIKE %s OR c.nome ILIKE %s OR COALESCE(c.email,'') ILIKE %s",
            (term, term, term),
        ).fetchone()["n"]
        items = conn.execute(
            "SELECT c.id,c.external_id,c.nome,c.email,c.telefone,c.is_active,u.id AS user_id,u.username,"
            "u.must_change_password,count(t.id) AS terminal_count FROM customers c "
            "LEFT JOIN users u ON u.customer_id=c.id LEFT JOIN terminals t ON t.customer_id=c.id "
            "WHERE c.id ILIKE %s OR c.nome ILIKE %s OR COALESCE(c.email,'') ILIKE %s "
            "GROUP BY c.id,u.id ORDER BY c.nome LIMIT %s OFFSET %s",
            (term, term, term, page_size, (page - 1) * page_size),
        ).fetchall()
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def customer_detail(customer_id: str) -> dict:
    with connection() as conn:
        customer = conn.execute(
            "SELECT c.id,c.external_id,c.nome,c.email,c.telefone,c.is_active,u.id AS user_id,u.username,"
            "u.must_change_password FROM customers c LEFT JOIN users u ON u.customer_id=c.id WHERE c.id=%s",
            (customer_id,),
        ).fetchone()
        if not customer:
            raise LookupError("Cliente não localizado.")
        terminals = conn.execute(
            "SELECT t.id,t.serial_number,t.apelido,t.status,t.model_id,m.name AS model_name,t.installed_at "
            "FROM terminals t LEFT JOIN machine_models m ON m.id=t.model_id WHERE t.customer_id=%s ORDER BY t.id",
            (customer_id,),
        ).fetchall()
    return {**customer, "terminals": terminals}


def create_customer(actor_id: int, data: dict) -> dict:
    customer_id = data["username"]
    with connection() as conn:
        if conn.execute("SELECT 1 FROM users WHERE lower(username)=lower(%s)", (customer_id,)).fetchone():
            raise ValueError("Identificador de login já está em uso.")
        if conn.execute("SELECT 1 FROM customers WHERE id=%s", (customer_id,)).fetchone():
            raise ValueError("Cliente já cadastrado.")
        conn.execute(
            "INSERT INTO customers(id,external_id,nome,email,telefone,contato,display_name,plan,is_active) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,'Plano demonstração',true)",
            (
                customer_id,
                customer_id,
                data["nome"],
                data.get("email"),
                data.get("telefone"),
                data.get("telefone"),
                data["nome"],
            ),
        )
        conn.execute(
            "INSERT INTO users(username,password_hash,role,display_name,customer_id,must_change_password) "
            "VALUES (%s,%s,'cliente',%s,%s,true) RETURNING id",
            (
                customer_id,
                hash_password(settings().default_customer_password.get_secret_value()),
                data["nome"],
                customer_id,
            ),
        ).fetchone()
        audit(
            conn,
            actor_id,
            "customer.created",
            "customer",
            customer_id,
            {
                "username": customer_id,
                "nome": data["nome"],
                "email": data.get("email"),
                "telefone": data.get("telefone"),
            },
        )
    return customer_detail(customer_id)


def update_customer(actor_id: int, customer_id: str, data: dict) -> dict:
    values = {k: v for k, v in data.items() if v is not None}
    with connection() as conn:
        current = conn.execute("SELECT * FROM customers WHERE id=%s FOR UPDATE", (customer_id,)).fetchone()
        if not current:
            raise LookupError("Cliente não localizado.")
        allowed = {k: values[k] for k in ("nome", "email", "telefone", "is_active") if k in values}
        if allowed:
            extra = dict(allowed)
            if "nome" in allowed:
                extra["display_name"] = allowed["nome"]
            if "telefone" in allowed:
                extra["contato"] = allowed["telefone"]
            conn.execute(
                f"UPDATE customers SET {','.join(f'{k}=%s' for k in extra)} WHERE id=%s",
                [*extra.values(), customer_id],
            )
            conn.execute(
                "UPDATE users SET display_name=COALESCE(%s,display_name),is_active=COALESCE(%s,is_active),"
                "token_version=token_version+CASE WHEN %s=false THEN 1 ELSE 0 END,updated_at=now() WHERE customer_id=%s",
                (allowed.get("nome"), allowed.get("is_active"), allowed.get("is_active"), customer_id),
            )
            audit(conn, actor_id, "customer.updated", "customer", customer_id, allowed)
    return customer_detail(customer_id)


def reset_customer_password(actor_id: int, customer_id: str) -> dict:
    with connection() as conn:
        row = conn.execute(
            "UPDATE users SET password_hash=%s,must_change_password=true,token_version=token_version+1,"
            "password_changed_at=NULL,updated_at=now() WHERE customer_id=%s AND role='cliente' RETURNING id",
            (hash_password(settings().default_customer_password.get_secret_value()), customer_id),
        ).fetchone()
        if not row:
            raise LookupError("Usuário cliente não localizado.")
        audit(conn, actor_id, "customer.password_reset", "customer", customer_id, {"credentials": "reset"})
    return {"customer_id": customer_id, "must_change_password": True}


def link_terminal(actor_id: int, customer_id: str, data: dict) -> dict:
    with connection() as conn:
        if not conn.execute(
            "SELECT 1 FROM customers WHERE id=%s AND is_active=true", (customer_id,)
        ).fetchone():
            raise LookupError("Cliente ativo não localizado.")
        serial_number = data.get("serial_number")
        if serial_number:
            serial_number = serial_number.strip().upper()
        terminal = None
        if data.get("terminal_id"):
            terminal = conn.execute(
                "SELECT * FROM terminals WHERE id=%s FOR UPDATE", (data["terminal_id"],)
            ).fetchone()
        elif serial_number:
            terminal = conn.execute(
                "SELECT * FROM terminals WHERE serial_number=%s FOR UPDATE", (serial_number,)
            ).fetchone()
        if terminal:
            if (
                serial_number
                and serial_number != terminal["serial_number"]
                and conn.execute(
                    "SELECT 1 FROM terminals WHERE serial_number=%s AND id<>%s",
                    (serial_number, terminal["id"]),
                ).fetchone()
            ):
                raise ValueError("Número de série já cadastrado.")
            conn.execute(
                "UPDATE terminals SET customer_id=%s,model_id=COALESCE(%s,model_id),serial_number=COALESCE(%s,serial_number),"
                "apelido=COALESCE(%s,apelido),status=COALESCE(%s,status),installed_at=COALESCE(installed_at,now()) WHERE id=%s",
                (
                    customer_id,
                    data.get("model_id"),
                    serial_number,
                    data.get("apelido"),
                    data.get("status"),
                    terminal["id"],
                ),
            )
            action = "terminal.transferred"
        else:
            if not serial_number or not data.get("model_id"):
                raise ValueError("Informe um serial existente ou um novo serial com modelo.")
            model = conn.execute(
                "SELECT name FROM machine_models WHERE id=%s AND is_active=true", (data["model_id"],)
            ).fetchone()
            if not model:
                raise ValueError("Modelo ativo não localizado.")
            status = data.get("status") or "offline"
            terminal_id = str(uuid4())
            conn.execute(
                "INSERT INTO terminals(id,customer_id,model_id,model,status,connection_status,serial_number,apelido,installed_at,last_seen_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,now(),now())",
                (
                    terminal_id,
                    customer_id,
                    data["model_id"],
                    model["name"],
                    status,
                    status,
                    serial_number,
                    data.get("apelido"),
                ),
            )
            data["terminal_id"] = terminal_id
            action = "terminal.linked"
            terminal = {"id": terminal_id}
        audit(
            conn,
            actor_id,
            action,
            "terminal",
            terminal["id"],
            {"customer_id": customer_id, "serial_number": serial_number, "apelido": data.get("apelido")},
        )
    return customer_detail(customer_id)


def unlink_terminal(actor_id: int, customer_id: str, terminal_id: str) -> dict:
    with connection() as conn:
        row = conn.execute(
            "UPDATE terminals SET customer_id=NULL WHERE id=%s AND customer_id=%s RETURNING id",
            (terminal_id, customer_id),
        ).fetchone()
        if not row:
            raise LookupError("Terminal vinculado não localizado.")
        audit(conn, actor_id, "terminal.unlinked", "terminal", terminal_id, {"customer_id": customer_id})
    return customer_detail(customer_id)
