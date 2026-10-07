from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .db import connection
from .handoff.service import service_center_counts
from .persistence import mask_sensitive
from .presence import PRESENCE_TTL_SECONDS, presence_snapshot

LOCAL_ZONE = ZoneInfo("America/Sao_Paulo")


def period_bounds(
    period: str, now: datetime | None = None, day: date | None = None
) -> tuple[datetime, datetime]:
    now = now or datetime.now(timezone.utc)
    local_now = now.astimezone(LOCAL_ZONE)
    if day:
        start = datetime.combine(day, datetime.min.time(), tzinfo=LOCAL_ZONE)
        return start.astimezone(timezone.utc), (start + timedelta(days=1)).astimezone(timezone.utc)
    days = {"today": 1, "7d": 7, "30d": 30}[period]
    local_start = datetime.combine(
        local_now.date() - timedelta(days=days - 1), datetime.min.time(), tzinfo=LOCAL_ZONE
    )
    return local_start.astimezone(timezone.utc), now


def dashboard(period: str, now: datetime | None = None, day: date | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    start, end = period_bounds(period, now, day)
    week_start, week_end = period_bounds("7d", now)
    with connection() as conn:
        live_handoffs = service_center_counts(conn=conn)
        connected = presence_snapshot(conn, now)
        connected_ids = {person["id"] for person in connected}
        cards = conn.execute(
            "SELECT count(*) AS conversations,"
            "count(*) FILTER (WHERE status='waiting') AS waiting,"
            "count(*) FILTER (WHERE status='with_technician') AS in_progress "
            "FROM conversations WHERE started_at >= %s AND started_at < %s",
            (start, end),
        ).fetchone()
        contacted_customers = conn.execute(
            "SELECT count(DISTINCT c.customer_id) AS total FROM messages m "
            "JOIN conversations c ON c.id=m.conversation_id "
            "WHERE m.sender_type='customer' AND m.created_at >= %s AND m.created_at < %s",
            (start, end),
        ).fetchone()["total"]
        escalated = conn.execute(
            "SELECT count(DISTINCT h.conversation_id) AS total FROM handoffs h "
            "JOIN conversations c ON c.id=h.conversation_id "
            "WHERE c.started_at >= %s AND c.started_at < %s",
            (start, end),
        ).fetchone()["total"]
        runs = conn.execute(
            "SELECT COALESCE(avg(latency_ms),0) AS average_latency_ms,"
            "COALESCE(sum(COALESCE((tokens->>'input_tokens')::bigint,0)),0) AS input_tokens,"
            "COALESCE(sum(COALESCE((tokens->>'output_tokens')::bigint,0)),0) AS output_tokens,"
            "COALESCE(sum(cost),0) AS cost FROM agent_runs WHERE created_at >= %s AND created_at < %s",
            (start, end),
        ).fetchone()
        blocked = conn.execute(
            "SELECT count(*) AS total FROM guardrail_events WHERE action='block' AND created_at >= %s AND created_at < %s",
            (start, end),
        ).fetchone()["total"]
        by_day = conn.execute(
            "SELECT (started_at AT TIME ZONE 'America/Sao_Paulo')::date AS day,count(*) AS total "
            "FROM conversations WHERE started_at >= %s AND started_at < %s "
            "GROUP BY day ORDER BY day",
            (start, end),
        ).fetchall()
        recent_days = conn.execute(
            "SELECT (started_at AT TIME ZONE 'America/Sao_Paulo')::date AS day,count(*) AS total "
            "FROM conversations WHERE started_at >= %s AND started_at < %s GROUP BY day ORDER BY day",
            (week_start, week_end),
        ).fetchall()
        routes = conn.execute(
            "SELECT route,count(*) AS total FROM agent_runs WHERE created_at >= %s AND created_at < %s "
            "GROUP BY route ORDER BY route",
            (start, end),
        ).fetchall()
        technicians = conn.execute(
            "SELECT u.id,u.display_name,p.status AS availability,"
            "count(DISTINCT h.id) FILTER (WHERE h.status='assigned') AS active_chats,"
            "count(DISTINCT h.id) FILTER (WHERE h.created_at >= %s AND h.created_at < %s) AS attended "
            "FROM users u JOIN technician_presence p ON p.user_id=u.id "
            "LEFT JOIN handoffs h ON h.technician_id=u.id "
            "WHERE u.role='tecnico' AND u.is_active=true GROUP BY u.id,p.status ORDER BY u.id",
            (start, end),
        ).fetchall()
        for technician in technicians:
            technician["connected"] = technician["id"] in connected_ids
            technician["status"] = technician["availability"] if technician["connected"] else "offline"
    week_totals = {row["day"]: row["total"] for row in recent_days}
    week_days = [
        {
            "day": week_start.astimezone(LOCAL_ZONE).date() + timedelta(days=offset),
            "total": week_totals.get(week_start.astimezone(LOCAL_ZONE).date() + timedelta(days=offset), 0),
        }
        for offset in range(7)
    ]
    total = cards["conversations"]
    return {
        "period": period,
        "selected_date": day,
        "start": start,
        "end": end,
        "cards": {
            "attendances": total,
            "distinct_customers": contacted_customers,
            "resolved_by_ai": max(total - escalated, 0),
            "escalated": escalated,
            "waiting": live_handoffs["queue"],
            "in_progress": live_handoffs["in_progress"],
            "average_response_ms": round(float(runs["average_latency_ms"] or 0), 2),
            "input_tokens": runs["input_tokens"],
            "output_tokens": runs["output_tokens"],
            "cost": float(runs["cost"] or 0),
            "blocked": blocked,
        },
        "attendances_by_day": by_day,
        "recent_conversations_by_day": week_days,
        "routes": routes,
        "escalation_rate": round((escalated / total * 100) if total else 0, 2),
        "technicians": technicians,
        "connected_customers": [person for person in connected if person["role"] == "cliente"],
        "presence_ttl_seconds": PRESENCE_TTL_SECONDS,
    }


def dashboard_details(kind: str, period: str, day: date | None, page: int, page_size: int) -> dict:
    start, end = period_bounds(period, day=day)
    with connection() as conn:
        if kind == "blocked":
            total = conn.execute(
                "SELECT count(*) AS n FROM guardrail_events WHERE action='block' AND created_at >= %s AND created_at < %s",
                (start, end),
            ).fetchone()["n"]
            rows = conn.execute(
                "SELECT id,rule,layer,severity,sample,created_at FROM guardrail_events "
                "WHERE action='block' AND created_at >= %s AND created_at < %s "
                "ORDER BY created_at DESC,id DESC LIMIT %s OFFSET %s",
                (start, end, page_size, (page - 1) * page_size),
            ).fetchall()
            for row in rows:
                row["sample"] = (
                    "[Conteúdo de saída omitido por segurança]"
                    if row["layer"] == "output"
                    else mask_sensitive(row["sample"])[:500]
                )
        else:
            handoff_filter = (
                "AND EXISTS (SELECT 1 FROM handoffs h WHERE h.conversation_id=c.id)"
                if kind == "handoffs"
                else ""
            )
            total = conn.execute(
                f"SELECT count(*) AS n FROM conversations c WHERE c.started_at >= %s AND c.started_at < %s {handoff_filter}",
                (start, end),
            ).fetchone()["n"]
            rows = conn.execute(
                "SELECT c.id,c.started_at,c.closed_at,c.status,cu.nome AS customer_name,"
                "(SELECT count(*) FROM messages m WHERE m.conversation_id=c.id AND m.visibility='public') AS message_count,"
                "latest.reason,latest.status AS handoff_status,u.display_name AS technician_name "
                "FROM conversations c JOIN customers cu ON cu.id=c.customer_id "
                "LEFT JOIN LATERAL (SELECT h.reason,h.status,h.technician_id FROM handoffs h "
                "WHERE h.conversation_id=c.id ORDER BY h.created_at DESC,h.id DESC LIMIT 1) latest ON true "
                "LEFT JOIN users u ON u.id=latest.technician_id "
                f"WHERE c.started_at >= %s AND c.started_at < %s {handoff_filter} "
                "ORDER BY c.started_at DESC,c.id DESC LIMIT %s OFFSET %s",
                (start, end, page_size, (page - 1) * page_size),
            ).fetchall()
    return {"items": rows, "total": total, "page": page, "page_size": page_size, "start": start, "end": end}


def operational_logs(
    start: datetime | None,
    end: datetime | None,
    route: str,
    tool: str,
    status: str,
    customer: str,
    page: int,
    page_size: int,
) -> dict:
    clauses, params = ["1=1"], []
    for value, sql in (
        (start, "ar.created_at >= %s"),
        (end, "ar.created_at <= %s"),
        (route, "ar.route = %s"),
        (status, "ar.status = %s"),
        (customer, "ar.user_id = %s"),
    ):
        if value:
            clauses.append(sql)
            params.append(value)
    if tool:
        clauses.append(
            "EXISTS (SELECT 1 FROM tool_calls filter_tc WHERE filter_tc.agent_run_id=ar.id "
            "AND filter_tc.tool_name=%s)"
        )
        params.append(tool)
    where = " AND ".join(clauses)
    with connection() as conn:
        total = conn.execute(f"SELECT count(*) AS n FROM agent_runs ar WHERE {where}", params).fetchone()["n"]
        runs = conn.execute(
            f"SELECT ar.id,ar.request_id,ar.conversation_id,ar.user_id,ar.route,ar.agents_used,"
            f"ar.status,ar.latency_ms,ar.tokens,ar.cost,ar.error,ar.created_at "
            f"FROM agent_runs ar WHERE {where} ORDER BY ar.created_at DESC,ar.id "
            "LIMIT %s OFFSET %s",
            [*params, page_size, (page - 1) * page_size],
        ).fetchall()
        run_ids = [row["id"] for row in runs]
        calls = (
            conn.execute(
                "SELECT id,agent_run_id,tool_name,input_summary,output_summary,success,latency_ms,created_at "
                "FROM tool_calls WHERE agent_run_id=ANY(%s) ORDER BY created_at,id",
                (run_ids,),
            ).fetchall()
            if run_ids
            else []
        )
    grouped: dict = {run_id: [] for run_id in run_ids}
    for call in calls:
        call["input_summary"] = mask_sensitive(call["input_summary"])
        call["output_summary"] = mask_sensitive(call["output_summary"])
        grouped[call["agent_run_id"]].append(call)
    for run in runs:
        run["error"] = mask_sensitive(run["error"]) if run["error"] else None
        run["tool_calls"] = grouped[run["id"]]
    return {"items": runs, "total": total, "page": page, "page_size": page_size}
