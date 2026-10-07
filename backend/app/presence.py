from datetime import datetime, timedelta, timezone
from uuid import UUID

from .db import connection

PRESENCE_TTL_SECONDS = 90


def update_presence(user: dict, session_id: UUID, active: bool) -> None:
    with connection() as conn:
        if active:
            conn.execute(
                "INSERT INTO user_presence_sessions(user_id,session_id,token_version,last_seen_at) "
                "VALUES (%s,%s,%s,now()) ON CONFLICT (user_id,session_id) "
                "DO UPDATE SET token_version=EXCLUDED.token_version,last_seen_at=EXCLUDED.last_seen_at",
                (user["id"], session_id, user["token_version"]),
            )
        else:
            conn.execute(
                "DELETE FROM user_presence_sessions WHERE user_id=%s AND session_id=%s",
                (user["id"], session_id),
            )
        conn.execute("DELETE FROM user_presence_sessions WHERE last_seen_at < now() - interval '1 day'")


def presence_snapshot(conn, now: datetime | None = None) -> list[dict]:
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(seconds=PRESENCE_TTL_SECONDS)
    return conn.execute(
        "SELECT u.id,u.display_name,u.role,max(s.last_seen_at) AS last_seen_at "
        "FROM user_presence_sessions s JOIN users u ON u.id=s.user_id "
        "WHERE u.is_active=true AND u.must_change_password=false AND s.token_version=u.token_version "
        "AND s.last_seen_at>%s GROUP BY u.id ORDER BY u.display_name,u.id",
        (cutoff,),
    ).fetchall()
