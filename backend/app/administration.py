from uuid import uuid4

from psycopg.types.json import Jsonb

from .auth import ensure_not_last_active_admin, hash_password
from .db import connection


def audit(conn, actor_id: int, action: str, entity: str, entity_id: object, diff: dict):
    safe = {key: value for key, value in diff.items() if "password" not in key.lower()}
    conn.execute(
        "INSERT INTO audit_logs(actor_id,action,entity,entity_id,diff) VALUES (%s,%s,%s,%s,%s)",
        (actor_id, action, entity, str(entity_id), Jsonb(safe)),
    )


def list_users() -> list[dict]:
    with connection() as conn:
        return conn.execute(
            "SELECT u.id,u.username,u.role,u.display_name,u.customer_id,u.is_active,u.created_at,u.updated_at,"
            "p.status AS presence FROM users u LEFT JOIN technician_presence p ON p.user_id=u.id "
            "WHERE u.role IN ('admin','tecnico') ORDER BY u.id"
        ).fetchall()


def create_user(actor_id: int, data: dict) -> dict:
    with connection() as conn:
        exists = conn.execute(
            "SELECT 1 FROM users WHERE lower(username)=lower(%s)", (data["username"],)
        ).fetchone()
        if exists:
            raise ValueError("Nome de usuário já está em uso.")
        row = conn.execute(
            "INSERT INTO users(username,password_hash,role,display_name,customer_id,must_change_password) VALUES (%s,%s,%s,%s,%s,%s) "
            "RETURNING id,username,role,display_name,customer_id,is_active,created_at,updated_at",
            (
                data["username"],
                hash_password(data["password"]),
                data["role"],
                data["display_name"],
                None,
                False,
            ),
        ).fetchone()
        if data["role"] == "tecnico":
            conn.execute(
                "INSERT INTO technician_presence(user_id,status,last_seen_at) VALUES (%s,'offline',now())",
                (row["id"],),
            )
        audit(
            conn,
            actor_id,
            "user.created",
            "user",
            row["id"],
            {"username": row["username"], "role": row["role"], "display_name": row["display_name"]},
        )
        return row


def update_user(actor_id: int, target_id: int, data: dict) -> dict:
    values = {key: value for key, value in data.items() if value is not None}
    with connection() as conn:
        current = conn.execute(
            "SELECT id,username,role,display_name,customer_id,is_active FROM users WHERE id=%s FOR UPDATE",
            (target_id,),
        ).fetchone()
        if not current:
            raise LookupError("Usuário não localizado.")
        if values.get("is_active") is False and actor_id == target_id:
            raise PermissionError("O administrador não pode desativar a própria conta.")
        removes_admin = current["role"] == "admin" and (
            values.get("is_active") is False or values.get("role") == "tecnico"
        )
        if removes_admin:
            ensure_not_last_active_admin(conn, target_id)
        if "username" in values:
            duplicate = conn.execute(
                "SELECT 1 FROM users WHERE lower(username)=lower(%s) AND id<>%s",
                (values["username"], target_id),
            ).fetchone()
            if duplicate:
                raise ValueError("Nome de usuário já está em uso.")
        if current["role"] == "cliente":
            raise PermissionError("Contas de Cliente são gerenciadas na área Clientes.")
        assignments, params, diff = [], [], {}
        for field in ("username", "role", "display_name", "is_active"):
            if field in values:
                assignments.append(f"{field}=%s")
                params.append(values[field])
                diff[field] = {"from": current[field], "to": values[field]}
        if "password" in values:
            assignments.append("password_hash=%s")
            params.append(hash_password(values["password"]))
            diff["credentials"] = "password_updated"
        if values.get("is_active") is False and current["role"] == "cliente":
            assignments.append("token_version=token_version+1")
        if not assignments:
            return current
        assignments.append("updated_at=now()")
        params.append(target_id)
        row = conn.execute(
            f"UPDATE users SET {','.join(assignments)} WHERE id=%s "
            "RETURNING id,username,role,display_name,customer_id,is_active,created_at,updated_at",
            params,
        ).fetchone()
        if row["role"] == "tecnico":
            conn.execute(
                "INSERT INTO technician_presence(user_id,status,last_seen_at) VALUES (%s,'offline',now()) "
                "ON CONFLICT(user_id) DO NOTHING",
                (target_id,),
            )
        audit(conn, actor_id, "user.updated", "user", target_id, diff)
        return row


def deactivate_user(actor_id: int, target_id: int) -> dict:
    return update_user(actor_id, target_id, {"is_active": False})


def list_machines(kind: str, search: str, page: int, page_size: int) -> dict:
    offset = (page - 1) * page_size
    term = f"%{search}%"
    with connection() as conn:
        if kind == "model":
            total = conn.execute(
                "SELECT count(*) AS n FROM machine_models WHERE name ILIKE %s", (term,)
            ).fetchone()["n"]
            items = conn.execute(
                "SELECT m.id,m.name,m.is_active,m.created_at,count(t.id) AS terminal_count "
                "FROM machine_models m LEFT JOIN terminals t ON t.model_id=m.id "
                "WHERE m.name ILIKE %s GROUP BY m.id ORDER BY m.name LIMIT %s OFFSET %s",
                (term, page_size, offset),
            ).fetchall()
        else:
            total = conn.execute(
                "SELECT count(*) AS n FROM terminals t JOIN customers c ON c.id=t.customer_id "
                "LEFT JOIN machine_models m ON m.id=t.model_id "
                "WHERE t.id ILIKE %s OR t.serial_number ILIKE %s OR COALESCE(t.apelido,'') ILIKE %s "
                "OR c.nome ILIKE %s OR COALESCE(m.name,'') ILIKE %s",
                (term, term, term, term, term),
            ).fetchone()["n"]
            items = conn.execute(
                "SELECT t.id,t.serial_number,t.apelido,t.customer_id,c.nome AS customer_name,t.model_id,m.name AS model_name,"
                "t.status,t.last_error,t.last_seen_at,t.installed_at FROM terminals t JOIN customers c ON c.id=t.customer_id "
                "LEFT JOIN machine_models m ON m.id=t.model_id "
                "WHERE t.id ILIKE %s OR t.serial_number ILIKE %s OR COALESCE(t.apelido,'') ILIKE %s "
                "OR c.nome ILIKE %s OR COALESCE(m.name,'') ILIKE %s "
                "ORDER BY t.serial_number LIMIT %s OFFSET %s",
                (term, term, term, term, term, page_size, offset),
            ).fetchall()
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def create_machine(actor_id: int, data: dict) -> dict:
    with connection() as conn:
        if data["kind"] == "model":
            if not data.get("name"):
                raise ValueError("Informe o nome do modelo.")
            if conn.execute(
                "SELECT 1 FROM machine_models WHERE lower(name)=lower(%s)", (data["name"],)
            ).fetchone():
                raise ValueError("Modelo já cadastrado.")
            row = conn.execute(
                "INSERT INTO machine_models(name) VALUES (%s) RETURNING id,name,is_active,created_at",
                (data["name"],),
            ).fetchone()
            audit(conn, actor_id, "machine_model.created", "machine_model", row["id"], {"name": row["name"]})
            return row
        required = ("customer_id", "model_id", "status", "serial_number")
        if any(not data.get(field) for field in required):
            raise ValueError("Informe o serial, cliente, modelo e status do terminal.")
        model = conn.execute(
            "SELECT name FROM machine_models WHERE id=%s AND is_active=true", (data["model_id"],)
        ).fetchone()
        customer = conn.execute("SELECT id FROM customers WHERE id=%s", (data["customer_id"],)).fetchone()
        if not model or not customer:
            raise ValueError("Cliente ou modelo ativo não localizado.")
        serial_number = data["serial_number"].strip().upper()
        if conn.execute("SELECT 1 FROM terminals WHERE serial_number=%s", (serial_number,)).fetchone():
            raise ValueError("Número de série já cadastrado.")
        terminal_id = data.get("id") or str(uuid4())
        row = conn.execute(
            "INSERT INTO terminals(id,customer_id,model_id,status,model,connection_status,last_error,last_seen_at,serial_number,apelido,installed_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,now(),%s,%s,now()) RETURNING id,serial_number,apelido,customer_id,model_id,status,last_error,last_seen_at,installed_at",
            (
                terminal_id,
                data["customer_id"],
                data["model_id"],
                data["status"],
                model["name"],
                data["status"],
                data.get("last_error"),
                serial_number,
                data.get("apelido"),
            ),
        ).fetchone()
        audit(
            conn,
            actor_id,
            "terminal.created",
            "terminal",
            row["id"],
            {key: row.get(key) for key in ("customer_id", "model_id", "status")},
        )
        return row


def update_machine(actor_id: int, kind: str, entity_id: str, data: dict) -> dict:
    values = {key: value for key, value in data.items() if value is not None}
    with connection() as conn:
        if kind == "model":
            current = conn.execute(
                "SELECT id,name,is_active FROM machine_models WHERE id=%s FOR UPDATE", (entity_id,)
            ).fetchone()
            if not current:
                raise LookupError("Modelo não localizado.")
            allowed = {key: values[key] for key in ("name", "is_active") if key in values}
            if (
                "name" in allowed
                and conn.execute(
                    "SELECT 1 FROM machine_models WHERE lower(name)=lower(%s) AND id<>%s",
                    (allowed["name"], entity_id),
                ).fetchone()
            ):
                raise ValueError("Modelo já cadastrado.")
            if not allowed:
                return current
            row = conn.execute(
                f"UPDATE machine_models SET {','.join(f'{key}=%s' for key in allowed)} WHERE id=%s RETURNING id,name,is_active,created_at",
                [*allowed.values(), entity_id],
            ).fetchone()
            audit(conn, actor_id, "machine_model.updated", "machine_model", entity_id, allowed)
            return row
        current = conn.execute(
            "SELECT id,customer_id,model_id,status,last_error FROM terminals WHERE id=%s FOR UPDATE",
            (entity_id,),
        ).fetchone()
        if not current:
            raise LookupError("Terminal não localizado.")
        allowed = {
            key: values[key]
            for key in ("customer_id", "model_id", "status", "last_error", "serial_number", "apelido")
            if key in values
        }
        if "serial_number" in allowed:
            allowed["serial_number"] = allowed["serial_number"].strip().upper()
            if conn.execute(
                "SELECT 1 FROM terminals WHERE serial_number=%s AND id<>%s",
                (allowed["serial_number"], entity_id),
            ).fetchone():
                raise ValueError("Número de série já cadastrado.")
        if "model_id" in allowed:
            model = conn.execute(
                "SELECT name FROM machine_models WHERE id=%s AND is_active=true", (allowed["model_id"],)
            ).fetchone()
            if not model:
                raise ValueError("Modelo ativo não localizado.")
            allowed["model"] = model["name"]
        if (
            "customer_id" in allowed
            and not conn.execute("SELECT 1 FROM customers WHERE id=%s", (allowed["customer_id"],)).fetchone()
        ):
            raise ValueError("Cliente não localizado.")
        if "status" in allowed:
            allowed["connection_status"] = allowed["status"]
        if not allowed:
            return current
        row = conn.execute(
            f"UPDATE terminals SET {','.join(f'{key}=%s' for key in allowed)},last_seen_at=now() WHERE id=%s "
            "RETURNING id,serial_number,apelido,customer_id,model_id,status,last_error,last_seen_at,installed_at",
            [*allowed.values(), entity_id],
        ).fetchone()
        audit(conn, actor_id, "terminal.updated", "terminal", entity_id, allowed)
        return row


def delete_machine(actor_id: int, kind: str, entity_id: str) -> dict:
    with connection() as conn:
        if kind == "model":
            linked = conn.execute(
                "SELECT count(*) AS n FROM terminals WHERE model_id=%s", (entity_id,)
            ).fetchone()["n"]
            if linked:
                raise ValueError("Não é possível remover o modelo porque existem terminais vinculados.")
            row = conn.execute(
                "DELETE FROM machine_models WHERE id=%s RETURNING id,name", (entity_id,)
            ).fetchone()
            entity = "machine_model"
        else:
            row = conn.execute("DELETE FROM terminals WHERE id=%s RETURNING id", (entity_id,)).fetchone()
            entity = "terminal"
        if not row:
            raise LookupError("Máquina não localizada.")
        audit(conn, actor_id, f"{entity}.deleted", entity, entity_id, {"deleted": True})
        return row


def list_audit(entity: str, action: str, actor_id: int | None, page: int, page_size: int) -> dict:
    clauses, params = (
        ["(%s='' OR entity=%s)", "(%s='' OR action ILIKE %s)"],
        [entity, entity, action, f"%{action}%"],
    )
    if actor_id is not None:
        clauses.append("actor_id=%s")
        params.append(actor_id)
    where = " AND ".join(clauses)
    with connection() as conn:
        total = conn.execute(f"SELECT count(*) AS n FROM audit_logs WHERE {where}", params).fetchone()["n"]
        items = conn.execute(
            f"SELECT a.id,a.actor_id,u.display_name AS actor_name,a.action,a.entity,a.entity_id,a.diff,a.created_at "
            f"FROM audit_logs a LEFT JOIN users u ON u.id=a.actor_id WHERE {where} "
            "ORDER BY a.created_at DESC,a.id DESC LIMIT %s OFFSET %s",
            [*params, page_size, (page - 1) * page_size],
        ).fetchall()
    return {"items": items, "total": total, "page": page, "page_size": page_size}
