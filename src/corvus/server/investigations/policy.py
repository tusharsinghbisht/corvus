"""Explicit connection consent, fresh-alert eligibility and conservative request reservations."""

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from ..database import audit
from . import service


def lock(db):
    db.execute("SELECT pg_advisory_xact_lock(hashtext(current_schema() || '.analyst.policy'))")


def listing(db):
    rows = db.execute("""SELECT c.id AS connection_id,c.name,c.enabled AS ingestion_enabled,
        coalesce(p.enabled,false) AS enabled,coalesce(p.minimum_level,12) AS minimum_level,
        coalesce(p.hourly_limit,2) AS hourly_limit,coalesce(p.daily_limit,10) AS daily_limit,
        coalesce(p.version,0) AS version,p.activated_at,p.consent_at,
        (SELECT count(*) FROM triage_attempts a JOIN triage_jobs j ON j.id=a.job_id
         JOIN alerts e ON e.id=j.alert_id WHERE a.mode='automatic' AND e.connection_id=c.id
         AND a.created_at>now()-interval '1 hour') AS used_hour,
        (SELECT count(*) FROM triage_attempts a JOIN triage_jobs j ON j.id=a.job_id
         JOIN alerts e ON e.id=j.alert_id WHERE a.mode='automatic' AND e.connection_id=c.id
         AND a.created_at>now()-interval '24 hours') AS used_day
        FROM connections c LEFT JOIN analyst_policies p ON p.connection_id=c.id ORDER BY c.created_at""").fetchall()
    settings = db.execute("SELECT daily_limit FROM analyst_settings WHERE singleton").fetchone()
    used = db.execute(
        "SELECT count(*) AS n FROM triage_attempts WHERE mode='automatic' AND created_at>now()-interval '24 hours'"
    ).fetchone()["n"]
    return {
        "policies": rows,
        "global_daily_limit": settings["daily_limit"],
        "global_used_day": used,
    }


def update(db, connection_id, body, user_id):
    lock(db)
    if not db.execute(
        "SELECT id FROM connections WHERE id=%s FOR UPDATE", (connection_id,)
    ).fetchone():
        raise HTTPException(404, "Connection not found")
    db.execute(
        "INSERT INTO analyst_policies(connection_id) VALUES(%s) ON CONFLICT DO NOTHING",
        (connection_id,),
    )
    row = db.execute(
        "SELECT * FROM analyst_policies WHERE connection_id=%s FOR UPDATE", (connection_id,)
    ).fetchone()
    # Optimistic version checks prevent a stale tab from re-enabling/replacing policy.
    actual = row["version"] if row["consent_at"] or row["version"] > 1 else 0
    if body.version != actual:
        raise HTTPException(409, "Policy changed; reload and inspect the current settings")
    if body.enabled and not body.allow_external:
        raise HTTPException(
            400, "Separate connection-level external-processing consent is required"
        )
    db.execute(
        """UPDATE analyst_policies SET enabled=%s,minimum_level=%s,hourly_limit=%s,
        daily_limit=%s,version=version+1,activated_at=CASE WHEN %s THEN now() ELSE activated_at END,
        consent_by=CASE WHEN %s THEN %s ELSE consent_by END,
        consent_at=CASE WHEN %s THEN now() ELSE consent_at END,updated_at=now() WHERE connection_id=%s""",
        (
            body.enabled,
            body.minimum_level,
            body.hourly_limit,
            body.daily_limit,
            body.enabled,
            body.enabled,
            user_id,
            body.enabled,
            connection_id,
        ),
    )
    db.execute(
        """UPDATE triage_attempts a SET status='cancelled',error_code='automation_policy_changed',completed_at=now()
        FROM triage_jobs j,alerts e WHERE a.job_id=j.id AND e.id=j.alert_id AND e.connection_id=%s
        AND a.mode='automatic' AND a.status IN ('pending_collection','awaiting_approval','queued')""",
        (connection_id,),
    )
    audit(
        db,
        "analyst.automation_enabled" if body.enabled else "analyst.automation_disabled",
        connection_id,
        user_id,
    )


def within_budget(db, connection_id, policy, exclude=None):
    global_limit = db.execute(
        "SELECT daily_limit FROM analyst_settings WHERE singleton FOR UPDATE"
    ).fetchone()["daily_limit"]
    counts = db.execute(
        """SELECT count(*) FILTER(WHERE a.created_at>now()-interval '24 hours') AS global_day,
        count(*) FILTER(WHERE e.connection_id=%s AND a.created_at>now()-interval '1 hour') AS hour,
        count(*) FILTER(WHERE e.connection_id=%s AND a.created_at>now()-interval '24 hours') AS day
        FROM triage_attempts a JOIN triage_jobs j ON j.id=a.job_id JOIN alerts e ON e.id=j.alert_id
        WHERE a.mode='automatic' AND (%s::uuid IS NULL OR a.id<>%s)""",
        (connection_id, connection_id, exclude, exclude),
    ).fetchone()
    return (
        counts["global_day"] < global_limit
        and counts["hour"] < policy["hourly_limit"]
        and counts["day"] < policy["daily_limit"]
    )


def authorize(db, attempt):
    """Called inside the transaction that crosses the no-retry request boundary."""
    lock(db)
    row = db.execute(
        """SELECT p.*,c.enabled AS ingestion_enabled,e.timestamp,e.received_at
        FROM triage_jobs j JOIN alerts e ON e.id=j.alert_id JOIN connections c ON c.id=e.connection_id
        JOIN analyst_policies p ON p.connection_id=c.id WHERE j.id=%s FOR UPDATE OF p,c""",
        (attempt["job_id"],),
    ).fetchone()
    fresh = (
        row
        and db.execute(
            "SELECT %s::timestamptz >= now()-interval '15 minutes' AS fresh", (row["timestamp"],)
        ).fetchone()["fresh"]
    )
    if (
        not row
        or not row["enabled"]
        or not row["ingestion_enabled"]
        or row["version"] != attempt["policy_version"]
        or not fresh
    ):
        return False
    return within_budget(db, row["connection_id"], row, attempt["id"])


def schedule(db):
    """Reserve at most one fresh alert per cycle. Old/backfilled detections never qualify."""
    # Serialize global budget reservations and policy changes with a consistent lock order.
    lock(db)
    policies = db.execute("""SELECT p.* FROM analyst_policies p JOIN connections c ON c.id=p.connection_id
        WHERE p.enabled AND c.enabled ORDER BY p.connection_id FOR UPDATE OF p,c""").fetchall()
    for policy in policies:
        if not within_budget(db, policy["connection_id"], policy):
            continue
        alert = db.execute(
            """SELECT e.id FROM alerts e WHERE e.connection_id=%s AND e.rule_level>=%s
            AND e.timestamp>=%s AND e.received_at>=%s
            AND e.timestamp BETWEEN now()-interval '15 minutes' AND now()-interval '5 minutes'
            AND NOT EXISTS(SELECT 1 FROM triage_jobs j WHERE j.alert_id=e.id)
            ORDER BY e.rule_level DESC,e.timestamp,e.id LIMIT 1""",
            (
                policy["connection_id"],
                policy["minimum_level"],
                policy["activated_at"],
                policy["activated_at"],
            ),
        ).fetchone()
        if not alert:
            continue
        identifier = service.request_collection(
            db, alert["id"], policy["consent_by"], automatic=True
        )
        snapshot = {
            key: policy[key] for key in ("minimum_level", "hourly_limit", "daily_limit", "version")
        }
        snapshot.update(
            {
                "connection_id": str(policy["connection_id"]),
                "consent_at": policy["consent_at"].isoformat(),
            }
        )
        db.execute(
            """UPDATE triage_attempts SET mode='automatic',policy_version=%s,provenance=%s WHERE id=%s""",
            (policy["version"], Jsonb({"automatic_policy": snapshot}), identifier),
        )
        audit(db, "triage.automatic_reserved", identifier, policy["consent_by"])
        return identifier
    return None
