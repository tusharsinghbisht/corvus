"""Manual investigation state. Evidence collection never implies external consent."""

from uuid import uuid4

from fastapi import HTTPException

from ...analyst import prepare_report
from ...reporting.evidence import EvidenceCatalog
from ..database import audit

ACTIVE = ("pending_collection", "collecting", "awaiting_approval", "queued", "requesting")
SUMMARY = """id,job_id,number,requested_by,created_at,status,collection_started_at,
    evidence_digest,approved_by,approved_at,approved_digest,request_started_at,
    completed_at,provenance,error_code"""


def require_alert(db, alert_id):
    row = db.execute("SELECT id FROM alerts WHERE id=%s", (alert_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Alert not found")


def history(db, alert_id):
    require_alert(db, alert_id)
    return db.execute(
        f"""SELECT {",".join("a." + field.strip() for field in SUMMARY.split(","))}
        FROM triage_attempts a JOIN triage_jobs j ON j.id=a.job_id
        WHERE j.alert_id=%s ORDER BY a.number DESC""",
        (alert_id,),
    ).fetchall()


def detail(db, alert_id, attempt_id):
    row = db.execute(
        """SELECT a.* FROM triage_attempts a JOIN triage_jobs j ON j.id=a.job_id
        WHERE j.alert_id=%s AND a.id=%s""",
        (alert_id, attempt_id),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Investigation attempt not found")
    row["prepared_input"] = prepare_report(row["evidence"]) if row["evidence"] else None
    return row


def request_collection(db, alert_id, user_id):
    require_alert(db, alert_id)
    # The job row serializes new attempts, including simultaneous first requests.
    db.execute(
        "INSERT INTO triage_jobs(id,alert_id) VALUES(%s,%s) ON CONFLICT(alert_id) DO NOTHING",
        (uuid4(), alert_id),
    )
    job = db.execute(
        "SELECT id FROM triage_jobs WHERE alert_id=%s FOR UPDATE", (alert_id,)
    ).fetchone()
    if db.execute(
        "SELECT id FROM triage_attempts WHERE job_id=%s AND status=ANY(%s)",
        (job["id"], list(ACTIVE)),
    ).fetchone():
        raise HTTPException(409, "An investigation is already active for this alert")
    number = db.execute(
        "SELECT coalesce(max(number),0)+1 AS n FROM triage_attempts WHERE job_id=%s",
        (job["id"],),
    ).fetchone()["n"]
    identifier = uuid4()
    db.execute(
        """INSERT INTO triage_attempts(id,job_id,number,requested_by,status)
        VALUES(%s,%s,%s,%s,'pending_collection')""",
        (identifier, job["id"], number, user_id),
    )
    audit(db, "triage.collection_requested", identifier, user_id)
    return identifier


def approve(db, alert_id, attempt_id, digest, user_id):
    row = db.execute(
        """SELECT a.* FROM triage_attempts a JOIN triage_jobs j ON j.id=a.job_id
        WHERE j.alert_id=%s AND a.id=%s FOR UPDATE OF a""",
        (alert_id, attempt_id),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Investigation attempt not found")
    if row["status"] != "awaiting_approval":
        raise HTTPException(409, "This attempt is not awaiting approval; refresh its state")
    if digest != row["evidence_digest"] or digest != EvidenceCatalog(row["evidence"]).digest:
        raise HTTPException(409, "Evidence changed; inspect the exact saved bundle before approval")
    db.execute(
        """UPDATE triage_attempts SET status='queued',approved_by=%s,approved_at=now(),
        approved_digest=%s WHERE id=%s""",
        (user_id, digest, attempt_id),
    )
    audit(db, "triage.external_processing_approved", attempt_id, user_id)


def cancel(db, alert_id, attempt_id, user_id):
    row = db.execute(
        """UPDATE triage_attempts a SET status='cancelled',completed_at=now()
        FROM triage_jobs j WHERE a.job_id=j.id AND j.alert_id=%s AND a.id=%s
        AND a.status IN ('pending_collection','awaiting_approval','queued') RETURNING a.id""",
        (alert_id, attempt_id),
    ).fetchone()
    if not row:
        raise HTTPException(409, "Only an unstarted collection or model request can be cancelled")
    audit(db, "triage.cancelled", attempt_id, user_id)
