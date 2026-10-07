from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from app.analytics import period_bounds
from app.config import settings
from app.db import connection
from app.main import app
from fastapi.testclient import TestClient


def test_selected_day_uses_brasilia_midnight():
    start, end = period_bounds("today", day=date(2026, 10, 4))
    assert start == datetime(2026, 10, 4, 3, tzinfo=timezone.utc)
    assert end == start + timedelta(days=1)


@pytest.fixture
def database(monkeypatch):
    import os

    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Requires dedicated getnet_test database.")
    if not url.rstrip("/").endswith("getnet_test"):
        pytest.fail("Only getnet_test is allowed.")
    monkeypatch.setenv("DATABASE_URL", url)
    settings.cache_clear()
    yield
    settings.cache_clear()


@pytest.mark.integration
def test_dashboard_details_dates_pagination_rbac_and_presence(database):
    with TestClient(app) as admin, TestClient(app) as customer, TestClient(app) as tech:
        assert (
            admin.post("/api/auth/login", json={"username": "Admin", "password": "Admin"}).status_code == 200
        )
        assert (
            customer.post("/api/auth/login", json={"username": "cliente1988", "password": "123"}).status_code
            == 200
        )
        assert (
            tech.post("/api/auth/login", json={"username": "Tecnico", "password": "Tecnico"}).status_code
            == 200
        )
        assert customer.get("/api/admin/dashboard/details?kind=blocked").status_code == 403
        assert tech.get("/api/admin/dashboard/details?kind=conversations").status_code == 403
        assert admin.get("/api/admin/dashboard/details?kind=invalid").status_code == 422
        assert admin.get("/api/admin/dashboard?date=invalid").status_code == 422
        customer_session, other_tab, tech_session = str(uuid4()), str(uuid4()), str(uuid4())
        for client, session in [(customer, customer_session), (customer, other_tab), (tech, tech_session)]:
            assert client.post("/api/auth/presence", json={"session_id": session}).status_code == 204
        snapshot = admin.get("/api/admin/dashboard").json()
        assert any(row["display_name"] == "Café Aurora" for row in snapshot["connected_customers"])
        technician = next(row for row in snapshot["technicians"] if row["display_name"] == "Técnico")
        assert technician["connected"] and technician["status"] == "online"
        customer.post("/api/auth/presence", json={"session_id": customer_session, "active": False})
        assert any(
            row["display_name"] == "Café Aurora"
            for row in admin.get("/api/admin/dashboard").json()["connected_customers"]
        )
        tech.post("/api/auth/presence", json={"session_id": tech_session, "active": False})
        technician = next(
            row
            for row in admin.get("/api/admin/dashboard").json()["technicians"]
            if row["display_name"] == "Técnico"
        )
        assert not technician["connected"] and technician["status"] == "offline"
        with connection() as conn:
            conn.execute(
                "UPDATE user_presence_sessions SET last_seen_at=now()-interval '100 seconds' WHERE session_id=%s",
                (other_tab,),
            )
            ids = [uuid4(), uuid4()]
            conn.execute(
                "INSERT INTO conversations(id,customer_id,status,started_at,closed_at) VALUES "
                "(%s,'cliente1988','closed','2020-01-02T03:00:00Z','2020-01-02T04:00:00Z'),"
                "(%s,'cliente1988','closed','2020-01-03T03:00:00Z','2020-01-03T04:00:00Z')",
                ids,
            )
            for _ in range(11):
                conn.execute(
                    "INSERT INTO guardrail_events(request_id,conversation_id,layer,rule,action,severity,sample,created_at) "
                    "VALUES (%s,%s,'input','command_execution_request','block','high','email pessoa@example.com','2020-01-02T15:00:00Z')",
                    (uuid4(), ids[0]),
                )
        snapshot = admin.get("/api/admin/dashboard?date=2020-01-02").json()
        assert snapshot["cards"]["attendances"] == 1  # Excludes next midnight.
        assert snapshot["cards"]["blocked"] == 11
        assert len(snapshot["recent_conversations_by_day"]) == 7
        assert not any(row["display_name"] == "Café Aurora" for row in snapshot["connected_customers"])
        first = admin.get("/api/admin/dashboard/details?kind=blocked&date=2020-01-02").json()
        second = admin.get("/api/admin/dashboard/details?kind=blocked&date=2020-01-02&page=2").json()
        assert first["total"] == 11 and len(first["items"]) == 10 and len(second["items"]) == 1
        assert first["items"][0]["rule"] == "command_execution_request"
        assert "pessoa@example.com" not in first["items"][0]["sample"]
        conversations = admin.get("/api/admin/dashboard/details?kind=conversations&date=2020-01-02").json()
        assert conversations["total"] == 1
        assert conversations["items"][0]["customer_name"] == "Café Aurora"
        assert admin.get("/api/admin/dashboard/details?kind=handoffs&date=2020-01-02").json()["total"] == 0
        with connection() as conn:
            conn.execute(
                "INSERT INTO handoffs(id,conversation_id,reason,summary,status,technician_id,created_at,closed_at) "
                "VALUES (%s,%s,'cliente_pediu','Atendimento de teste','closed',%s,'2020-01-02T03:10:00Z','2020-01-02T04:00:00Z')",
                (uuid4(), ids[0], technician["id"]),
            )
        humans = admin.get("/api/admin/dashboard/details?kind=handoffs&date=2020-01-02").json()
        assert humans["total"] == 1 and humans["items"][0]["technician_name"] == "Técnico"
        assert humans["items"][0]["handoff_status"] == "closed"
        with connection() as conn:
            conn.execute(
                "INSERT INTO guardrail_events(request_id,conversation_id,layer,rule,action,severity,sample,created_at) "
                "VALUES (%s,%s,'output','output_canary','block','high','INTERNAL_PRIVATE_MARKER','2020-01-04T15:00:00Z')",
                (uuid4(), ids[0]),
            )
        output_events = admin.get("/api/admin/dashboard/details?kind=blocked&date=2020-01-04").json()
        assert "INTERNAL_PRIVATE_MARKER" not in str(output_events)
        assert output_events["items"][0]["rule"] == "output_canary"
        customer.post("/api/auth/presence", json={"session_id": other_tab})
        customer.post("/api/auth/logout")
        assert not any(
            row["display_name"] == "Café Aurora"
            for row in admin.get("/api/admin/dashboard").json()["connected_customers"]
        )
