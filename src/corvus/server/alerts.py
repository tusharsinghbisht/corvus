import base64
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

from ..timeutil import utc
from .investigations.overview import enrich_alerts

COLUMNS = "a.id,a.connection_id,a.timestamp,a.received_at,a.agent_id,a.agent_name,a.rule_id,a.rule_level,a.title,a.native_index,a.native_id"


def cursor(row):
    value = json.dumps([row["timestamp"].isoformat(), str(row["id"])]).encode()
    return base64.urlsafe_b64encode(value).decode()


def decode_cursor(value):
    try:
        parts = json.loads(base64.b64decode(value, altchars=b"-_", validate=True))
        if (
            not isinstance(parts, list)
            or len(parts) != 2
            or not all(isinstance(part, str) for part in parts)
        ):
            raise ValueError("Cursor must contain a timestamp and ID")
        timestamp, identifier = parts
        return utc(timestamp), UUID(identifier)
    except (ValueError, TypeError, UnicodeDecodeError) as exc:
        raise ValueError("Invalid alert cursor") from exc


WORKFLOW_JOIN = """LEFT JOIN triage_jobs j ON j.alert_id=a.id
    LEFT JOIN LATERAL (SELECT status FROM triage_attempts WHERE job_id=j.id ORDER BY number DESC LIMIT 1) latest ON true
    LEFT JOIN LATERAL (SELECT id FROM triage_attempts WHERE job_id=j.id AND status='validated' ORDER BY number DESC LIMIT 1) report ON true
    LEFT JOIN LATERAL (SELECT decision FROM report_reviews WHERE attempt_id=report.id ORDER BY sequence DESC LIMIT 1) review ON true"""
WORKFLOW_FILTERS = {
    'all': 'true',
    'uninvestigated': 'latest.status IS NULL',
    'active': "latest.status IN ('pending_collection','collecting','awaiting_approval','queued','requesting')",
    'needs_review': 'report.id IS NOT NULL AND review.decision IS NULL',
    'follow_up': "review.decision='follow_up'",
    'reviewed': "review.decision IN ('accepted','rejected')",
    'attention': "latest.status IN ('failed','unknown','rejected')",
}


def listing(db, *, hours=24, minimum=0, search="", connection=None, before=None, view='all'):
    where = ["a.timestamp>=%s", "a.rule_level>=%s"]
    params = [datetime.now(timezone.utc) - timedelta(hours=hours), minimum]
    if connection:
        where.append("a.connection_id=%s")
        params.append(connection)
    if search:
        where.append(
            "(a.title ILIKE %s OR a.agent_name ILIKE %s OR a.agent_id ILIKE %s OR a.rule_id ILIKE %s)"
        )
        params.extend(["%" + search + "%"] * 4)
    join = WORKFLOW_JOIN if view != 'all' else ''
    where.append(WORKFLOW_FILTERS[view])
    clause = " AND ".join(where)
    stats = db.execute(
        f"""
        SELECT count(*) AS total,count(*) FILTER(WHERE rule_level>=12) AS high,
               count(DISTINCT agent_id) AS agents FROM alerts a {join} WHERE {clause}
    """,
        params,
    ).fetchone()
    if before:
        clause += " AND (a.timestamp,a.id)<(%s,%s)"
        params.extend(decode_cursor(before))
    rows = db.execute(
        f"SELECT {COLUMNS} FROM alerts a {join} WHERE {clause} ORDER BY a.timestamp DESC,a.id DESC LIMIT 51",
        params,
    ).fetchall()
    page = rows[:50]
    enrich_alerts(db, page)
    return {
        "alerts": page,
        "next_cursor": cursor(rows[49]) if len(rows) > 50 else None,
        "stats": stats,
    }
