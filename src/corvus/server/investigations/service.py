"""Manual investigation state. Evidence collection never implies external consent."""

from uuid import uuid4

from fastapi import HTTPException

from ...agents.analyst import prepare_report
from ...agents.analyst.context import select_context, ContextBudgetError
from ...agents.intel import inspect as inspect_indicators
from psycopg.types.json import Jsonb
from ...reporting.evidence import EvidenceCatalog
from ..database import audit
from . import reviews

ACTIVE = ("pending_collection", "collecting", "awaiting_approval", "queued", "requesting")
SUMMARY = """id,job_id,number,requested_by,created_at,status,collection_started_at,
    evidence_digest,approved_by,approved_at,approved_digest,request_started_at,
    completed_at,provenance,error_code,mode,policy_version"""


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
    selected = (
        None
        if row["error_code"] == "context_budget_exceeded"
        else (row["analysis_evidence"] or row["evidence"])
    )
    row["local_intel"] = inspect_indicators(selected) if selected else None
    row["prepared_input"] = row["input_snapshot"] or (
        prepare_report(selected) if selected else None
    )
    row["prepared_input_reconstructed"] = bool(selected and not row["input_snapshot"])
    row["human_review"] = reviews.page(db, row) if row["status"] == "validated" else None
    return row


def request_collection(db, alert_id, user_id, *, automatic=False):
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
    if (
        automatic
        and db.execute("SELECT 1 FROM triage_attempts WHERE job_id=%s", (job["id"],)).fetchone()
    ):
        raise HTTPException(409, "This alert already has an investigation attempt")
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


def choose_context(db, alert_id, attempt_id, profile, expected_digest, user_id):
    row = reviews.load_attempt(db, alert_id, attempt_id, lock=True)
    recoverable = row["status"] == "failed" and row["error_code"] == "context_budget_exceeded"
    if (
        row["mode"] != "manual"
        or (row["status"] != "awaiting_approval" and not recoverable)
        or row["request_started_at"]
        or row["approved_at"]
        or not row["evidence"]
    ):
        raise HTTPException(
            409,
            "Only unapproved manual input can be changed; completed or started attempts are immutable",
        )
    if expected_digest != row["evidence_digest"]:
        raise HTTPException(409, "Selected input changed; reload before choosing context")
    try:
        selected = select_context(row["evidence"], profile=profile)
    except ContextBudgetError:
        raise HTTPException(
            413,
            "This context cannot fit the selected budget; use the broader profile or inspect the local evidence",
        ) from None
    digest = EvidenceCatalog(selected).digest
    db.execute(
        """UPDATE triage_attempts SET status='awaiting_approval',analysis_evidence=%s,input_snapshot=%s,evidence_digest=%s,
        approved_digest=NULL,approved_at=NULL,approved_by=NULL,error_code=NULL,completed_at=NULL WHERE id=%s""",
        (Jsonb(selected), Jsonb(prepare_report(selected)), digest, attempt_id),
    )
    audit(db, "triage.context_selected", attempt_id, user_id)
    return detail(db, alert_id, attempt_id)


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
    if (
        digest != row["evidence_digest"]
        or digest != EvidenceCatalog(row["analysis_evidence"] or row["evidence"]).digest
    ):
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
