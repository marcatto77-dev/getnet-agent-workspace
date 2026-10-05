from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .auth import hash_password
from .config import settings
from .db import connection


def setup():
    cfg = settings()
    with connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(20260920)")
        users = [
            (
                cfg.seed_admin_username,
                cfg.seed_admin_password.get_secret_value(),
                "admin",
                cfg.seed_admin_display_name,
            ),
            (
                cfg.seed_technician_username,
                cfg.seed_technician_password.get_secret_value(),
                "tecnico",
                cfg.seed_technician_display_name,
            ),
        ]
        for username, password, role, display_name in users:
            row = conn.execute("SELECT id FROM users WHERE lower(username)=lower(%s)", (username,)).fetchone()
            if row:
                conn.execute(
                    "UPDATE users SET role=%s,display_name=%s,is_active=true,updated_at=now() WHERE id=%s",
                    (role, display_name, row["id"]),
                )
                user_id = row["id"]
            else:
                user_id = conn.execute(
                    "INSERT INTO users(username,password_hash,role,display_name) VALUES (%s,%s,%s,%s) RETURNING id",
                    (username, hash_password(password), role, display_name),
                ).fetchone()["id"]
            if role == "tecnico":
                conn.execute(
                    "INSERT INTO technician_presence(user_id,status) VALUES (%s,'offline') ON CONFLICT DO NOTHING",
                    (user_id,),
                )
        for cid, name in [("cliente1988", "Café Aurora"), ("cliente2026", "Mercado Horizonte")]:
            conn.execute(
                "INSERT INTO customers(id,external_id,nome,contato,display_name,plan,is_active) "
                "VALUES (%s,%s,%s,%s,%s,%s,true) ON CONFLICT(id) DO UPDATE SET "
                "external_id=EXCLUDED.external_id,nome=EXCLUDED.nome,display_name=EXCLUDED.display_name,is_active=true",
                (cid, cid, name, "Contato fictício", name, "Plano demonstração"),
            )
            if cfg.demo_mode:
                existing = conn.execute(
                    "SELECT id FROM users WHERE lower(username)=lower(%s)", (cid,)
                ).fetchone()
                if existing:
                    conn.execute(
                        "UPDATE users SET role='cliente',display_name=%s,customer_id=%s,is_active=true,"
                        "must_change_password=false,updated_at=now() WHERE id=%s",
                        (name, cid, existing["id"]),
                    )
                else:
                    conn.execute(
                        "INSERT INTO users(username,password_hash,role,display_name,customer_id,must_change_password) "
                        "VALUES (%s,%s,'cliente',%s,%s,false)",
                        (cid, hash_password(cfg.default_customer_password.get_secret_value()), name, cid),
                    )
        model_ids = {}
        for model in ("Get Smart", "Get Clássica"):
            model_ids[model] = conn.execute(
                "INSERT INTO machine_models(name) VALUES (%s) ON CONFLICT(name) "
                "DO UPDATE SET is_active=true RETURNING id",
                (model,),
            ).fetchone()["id"]
        terminals = [
            ("terminal-demo-01", "cliente1988", "Get Smart", "offline", "Falha de conexão", "A1B2C3"),
            ("terminal-demo-02", "cliente2026", "Get Clássica", "online", None, "D4E5F6"),
        ]
        for terminal_id, customer_id, model, status, error, serial_number in terminals:
            conn.execute(
                "INSERT INTO terminals(id,customer_id,model_id,status,model,connection_status,last_error,last_seen_at,serial_number,apelido,installed_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,now(),%s,%s,now()) ON CONFLICT(id) DO UPDATE SET "
                "customer_id=EXCLUDED.customer_id,model_id=EXCLUDED.model_id,status=EXCLUDED.status,"
                "model=EXCLUDED.model,connection_status=EXCLUDED.connection_status,last_error=EXCLUDED.last_error,"
                "serial_number=EXCLUDED.serial_number,apelido=EXCLUDED.apelido",
                (
                    terminal_id,
                    customer_id,
                    model_ids[model],
                    status,
                    model,
                    status,
                    error,
                    serial_number,
                    model,
                ),
            )
        today = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
        for cid, amount in [("cliente1988", "1250.80"), ("cliente2026", "380.00")]:
            conn.execute(
                "INSERT INTO receivables(id,customer_id,sale_date,expected_date,amount,status) "
                "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET "
                "sale_date=EXCLUDED.sale_date,expected_date=EXCLUDED.expected_date,amount=EXCLUDED.amount,"
                "currency=EXCLUDED.currency,status=EXCLUDED.status",
                (
                    f"{cid}-seed",
                    cid,
                    today - timedelta(days=1),
                    today + timedelta(days=1),
                    amount,
                    "previsto_demo",
                ),
            )
    print("Seed idempotente de demonstração concluído.")


if __name__ == "__main__":
    setup()
