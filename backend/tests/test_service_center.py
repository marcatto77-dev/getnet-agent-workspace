import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from app.config import settings


@pytest.fixture
def center_database(monkeypatch):
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Defina TEST_DATABASE_URL.")
    if not url.rstrip("/").endswith("getnet_test"):
        pytest.fail("O teste da Central exige getnet_test.")
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("HANDOFF_MODE", "manual")
    settings.cache_clear()
    from app.setup_db import setup

    setup()
    from app.db import connection

    with connection() as conn:
        conn.execute(
            "UPDATE handoffs SET status='closed',closed_at=COALESCE(closed_at,now()) WHERE status<>'closed'"
        )
        conn.execute(
            "UPDATE conversations SET status='closed',closed_at=COALESCE(closed_at,now()) WHERE status<>'closed'"
        )
    yield
    settings.cache_clear()


def _new_waiting():
    from app.db import connection
    from app.handoff.service import create_handoff

    cid = uuid4()
    with connection() as conn:
        conn.execute(
            "INSERT INTO conversations(id,customer_id,status) VALUES (%s,'cliente1988','ai')", (cid,)
        )
    return cid, create_handoff(cid, "cliente_pediu", "Resumo operacional sem PII")


def _technician(online=True):
    from app.db import connection

    with connection() as conn:
        row = conn.execute("SELECT id FROM users WHERE lower(username)='tecnico'").fetchone()
        conn.execute(
            "UPDATE technician_presence SET status=%s,last_seen_at=now() WHERE user_id=%s",
            ("online" if online else "offline", row["id"]),
        )
        return row["id"]


def _extra_technicians(total):
    from app.auth import hash_password
    from app.db import connection

    ids = []
    with connection() as conn:
        for index in range(total):
            username = f"central-{uuid4().hex[:10]}-{index}"
            tid = conn.execute(
                "INSERT INTO users(username,password_hash,role,display_name) VALUES (%s,%s,'tecnico',%s) RETURNING id",
                (username, hash_password("Senha-Forte-15"), f"Técnico {index}"),
            ).fetchone()["id"]
            conn.execute(
                "INSERT INTO technician_presence(user_id,status,last_seen_at) VALUES (%s,'online',now())",
                (tid,),
            )
            ids.append(tid)
    return ids


def test_new_visit_creates_new_history_but_pending_handoff_is_restored(center_database):
    from app.db import connection
    from app.handoff.service import create_handoff
    from app.persistence import get_or_create_conversation

    first = get_or_create_conversation("cliente1988", fresh=True)
    assert get_or_create_conversation("cliente1988", first["id"])["id"] == first["id"]
    second = get_or_create_conversation("cliente1988", fresh=True)
    assert second["id"] != first["id"]
    with connection() as conn:
        assert (
            conn.execute("SELECT status FROM conversations WHERE id=%s", (first["id"],)).fetchone()["status"]
            == "closed"
        )
    create_handoff(second["id"], "cliente_pediu", "Cliente pediu atendimento")
    assert get_or_create_conversation("cliente1988", fresh=True)["id"] == second["id"]


def test_customer_can_close_handoff_and_technician_cannot_reply(center_database):
    from app.db import connection
    from app.handoff.service import claim
    from app.main import app
    from fastapi.testclient import TestClient

    cid, handoff = _new_waiting()
    tid = _technician()
    claim(handoff["id"], tid)
    with TestClient(app) as customer, TestClient(app) as technician:
        assert (
            customer.post("/api/auth/login", json={"username": "cliente1988", "password": "123"}).status_code
            == 200
        )
        assert (
            technician.post(
                "/api/auth/login", json={"username": "Tecnico", "password": "Tecnico"}
            ).status_code
            == 200
        )
        assert customer.get("/api/chat/current").json()["conversation_id"] == str(cid)
        assert customer.post(f"/api/chat/conversations/{cid}/close").status_code == 200
        assert customer.get("/api/chat/current").json() is None
        assert (
            technician.post(
                f"/api/tech/conversations/{cid}/messages", json={"content": "Tarde demais"}
            ).status_code
            == 409
        )
        closed = technician.get("/api/tech/handoffs/closed").json()["items"]
        assert any(item["id"] == str(handoff["id"]) for item in closed)
    with connection() as conn:
        assert (
            conn.execute("SELECT status FROM handoffs WHERE id=%s", (handoff["id"],)).fetchone()["status"]
            == "closed"
        )
        assert (
            conn.execute("SELECT status FROM conversations WHERE id=%s", (cid,)).fetchone()["status"]
            == "closed"
        )


def test_closed_technician_history_excludes_later_legacy_messages(center_database):
    from app.db import connection
    from app.handoff.service import claim, close_handoff
    from app.technician import conversation_detail

    cid, handoff = _new_waiting()
    tid = _technician()
    claim(handoff["id"], tid)
    with connection() as conn:
        conn.execute(
            "INSERT INTO messages(id,conversation_id,sender_type,content) VALUES (%s,%s,'customer','Antes do encerramento')",
            (uuid4(), cid),
        )
    close_handoff(handoff["id"], "Resolvido", tid)
    with connection() as conn:
        conn.execute(
            "INSERT INTO messages(id,conversation_id,sender_type,content,created_at) VALUES (%s,%s,'customer','Conversa posterior',now()+interval '1 minute')",
            (uuid4(), cid),
        )
    detail = conversation_detail(cid, tid, handoff["id"])
    assert "Antes do encerramento" in [message["content"] for message in detail["messages"]]
    assert any("Atendimento técnico encerrado" in message["content"] for message in detail["messages"])
    assert "Conversa posterior" not in [message["content"] for message in detail["messages"]]


def test_customer_cancels_queue_and_it_moves_to_closed(center_database):
    from app.main import app
    from fastapi.testclient import TestClient

    cid, handoff = _new_waiting()
    with TestClient(app) as customer, TestClient(app) as technician:
        assert (
            customer.post("/api/auth/login", json={"username": "cliente1988", "password": "123"}).status_code
            == 200
        )
        assert (
            technician.post(
                "/api/auth/login", json={"username": "Tecnico", "password": "Tecnico"}
            ).status_code
            == 200
        )
        assert customer.post(f"/api/chat/conversations/{cid}/close").status_code == 200
        assert not any(item["id"] == str(handoff["id"]) for item in technician.get("/api/tech/queue").json())
        assert any(
            item["id"] == str(handoff["id"])
            for item in technician.get("/api/tech/handoffs/closed").json()["items"]
        )
        detail = technician.get(f"/api/tech/conversations/{cid}?handoff_id={handoff['id']}")
        assert detail.status_code == 200


def test_manual_claim_note_return_and_close(center_database):
    from app.db import connection
    from app.handoff.service import add_internal_note, claim, close_handoff, transfer

    tid = _technician()
    cid, waiting = _new_waiting()
    assert waiting["status"] == "waiting"
    assigned = claim(waiting["id"], tid)
    assert assigned["status"] == "assigned" and assigned["technician_id"] == tid
    add_internal_note(waiting["id"], tid, "Nota privada 111.444.777-35")
    queued = transfer(waiting["id"], tid, None, "Retornar mantendo prioridade")
    assert queued["status"] == "waiting" and queued["waiting_since"] == waiting["waiting_since"]
    claim(waiting["id"], tid)
    closed = close_handoff(waiting["id"], "Resolvido", tid, "resolvido")
    assert closed["status"] == "closed" and closed["closed_by_id"] == tid
    with connection() as conn:
        assert (
            conn.execute("SELECT status FROM conversations WHERE id=%s", (cid,)).fetchone()["status"]
            == "closed"
        )
        note = conn.execute(
            "SELECT content,visibility FROM messages WHERE conversation_id=%s AND visibility='internal'",
            (cid,),
        ).fetchone()
        event = conn.execute(
            "SELECT note FROM handoff_events WHERE handoff_id=%s AND type='note_added'", (waiting["id"],)
        ).fetchone()
        assert note["visibility"] == "internal" and "111.444" in note["content"]
        assert "111.444" not in (event["note"] or "")
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM handoff_events WHERE handoff_id=%s", (waiting["id"],)
            ).fetchone()["n"]
            >= 5
        )


def test_ten_concurrent_claims_have_one_winner(center_database):
    from app.handoff.service import HandoffConflict, claim

    technicians = _extra_technicians(10)
    _, waiting = _new_waiting()

    def attempt(_):
        try:
            claim(waiting["id"], technicians[_])
            return "won"
        except HandoffConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(attempt, range(10)))
    assert results.count("won") == 1 and results.count("conflict") == 9


def test_pull_and_transfer_race_stays_consistent(center_database):
    from app.db import connection
    from app.handoff.service import claim, pull, transfer

    owner, puller, target = _extra_technicians(3)
    _, waiting = _new_waiting()
    claim(waiting["id"], owner)

    def pull_action():
        try:
            pull(waiting["id"], puller, "Cobertura de troca concorrente")
            return "pull"
        except (ValueError, PermissionError):
            return "lost"

    def transfer_action():
        try:
            transfer(waiting["id"], owner, target, "Encaminhamento concorrente")
            return "transfer"
        except (ValueError, PermissionError):
            return "lost"

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(pull_action), pool.submit(transfer_action)]
        results = [future.result() for future in futures]
    assert results.count("lost") == 1
    with connection() as conn:
        row = conn.execute(
            "SELECT status,technician_id FROM handoffs WHERE id=%s", (waiting["id"],)
        ).fetchone()
        assert row["status"] == "assigned" and row["technician_id"] in {puller, target}


def test_offline_and_pull_rules(center_database):
    from app.handoff.service import claim, pull

    tid = _technician(False)
    _, waiting = _new_waiting()
    with pytest.raises(PermissionError):
        claim(waiting["id"], tid)
    _technician(True)
    claim(waiting["id"], tid)
    with pytest.raises(ValueError):
        pull(waiting["id"], tid, "motivo longo o bastante")


def test_service_center_rbac_and_internal_note_privacy(center_database):
    from app.main import app
    from fastapi.testclient import TestClient

    cid, waiting = _new_waiting()
    with TestClient(app) as technician, TestClient(app) as customer, TestClient(app) as admin:
        assert (
            technician.post(
                "/api/auth/login", json={"username": "Tecnico", "password": "Tecnico"}
            ).status_code
            == 200
        )
        claimed = technician.post(f"/api/tech/handoffs/{waiting['id']}/claim")
        assert claimed.status_code == 200
        assert (
            technician.post(
                f"/api/tech/handoffs/{waiting['id']}/notes", json={"text": "Somente equipe"}
            ).status_code
            == 200
        )
        assert (
            customer.post("/api/auth/login", json={"username": "cliente1988", "password": "123"}).status_code
            == 200
        )
        from app.auth import create_customer_token

        customer.cookies.set(settings().customer_cookie_name, create_customer_token("cliente1988"))
        history = customer.get(f"/api/chat/conversations/{cid}/messages")
        assert history.status_code == 200
        assert all(item["content"] != "Somente equipe" for item in history.json()["messages"])
        assert customer.get("/api/tech/queue").status_code == 403
        assert (
            admin.post("/api/auth/login", json={"username": "Admin", "password": "Admin"}).status_code == 200
        )
        assert admin.get("/api/tech/queue").status_code == 403


def test_claim_emits_public_and_technician_websocket_events(center_database):
    from app.auth import create_customer_token
    from app.main import app
    from fastapi.testclient import TestClient

    cid, waiting = _new_waiting()
    with TestClient(app) as customer, TestClient(app) as technician:
        customer.cookies.set(settings().customer_cookie_name, create_customer_token("cliente1988"))
        assert (
            technician.post(
                "/api/auth/login", json={"username": "Tecnico", "password": "Tecnico"}
            ).status_code
            == 200
        )
        with (
            customer.websocket_connect(f"/ws/chat/{cid}") as customer_ws,
            technician.websocket_connect("/ws/tech") as technician_ws,
        ):
            assert customer_ws.receive_json()["status"] == "waiting"
            assert technician_ws.receive_json()["type"] == "connection.ready"
            assert technician.post(f"/api/tech/handoffs/{waiting['id']}/claim").status_code == 200
            assert customer_ws.receive_json()["type"] == "handoff.claimed"
            assert technician_ws.receive_json()["type"] == "queue.updated"


def test_offline_timeout_requeues_with_original_priority(center_database):
    from datetime import datetime, timedelta, timezone

    from app.db import connection
    from app.handoff.service import claim, reassign_stale_offline

    tid = _technician()
    _, waiting = _new_waiting()
    claim(waiting["id"], tid)
    with connection() as conn:
        conn.execute(
            "UPDATE technician_presence SET status='offline',last_seen_at=%s WHERE user_id=%s",
            (datetime.now(timezone.utc) - timedelta(hours=1), tid),
        )
    reassign_stale_offline(datetime.now(timezone.utc))
    with connection() as conn:
        row = conn.execute(
            "SELECT status,waiting_since FROM handoffs WHERE id=%s", (waiting["id"],)
        ).fetchone()
        assert row["status"] == "waiting" and row["waiting_since"] == waiting["waiting_since"]
        assert conn.execute(
            "SELECT 1 FROM handoff_events WHERE handoff_id=%s AND type='timeout_requeued'", (waiting["id"],)
        ).fetchone()


def test_assignment_fifo_legacy_and_manual_default():
    from datetime import datetime, timezone

    from app.config import Settings
    from app.handoff.assignment import next_waiting_handoff

    now = datetime.now(timezone.utc)
    assert Settings(_env_file=None, handoff_mode="manual").effective_handoff_mode == "manual"
    assert next_waiting_handoff([{"id": 2, "created_at": now}, {"id": 1, "created_at": now}])["id"] == 1
