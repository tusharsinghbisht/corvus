"""Manual investigation state. Evidence collection never implies external consent."""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from ...agents.analyst import prepare_report
from ...agents.analyst.context import ContextBudgetError, select_context
from ...agents.intel import inspect as inspect_indicators
from ...reporting.evidence import EvidenceCatalog
from ...timeutil import utc
from ..database import audit
from . import reviews, steps

ACTIVE = ("pending_collection", "collecting", "awaiting_approval", "queued", "requesting")
TERMINAL = ("validated", "rejected", "failed", "unknown", "cancelled")
SUMMARY = """id,job_id,number,requested_by,created_at,status,collection_started_at,
    evidence_digest,approved_by,approved_at,approved_digest,request_started_at,
    completed_at,provenance,error_code,mode,policy_version,workflow"""


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


def saved_collection_binding(attempt):
    if (
        attempt["status"] not in TERMINAL
        or not isinstance(attempt["evidence"], dict)
        or not isinstance(attempt["evidence"].get("scope"), dict)
    ):
        return None
    try:
        catalog = EvidenceCatalog(attempt["evidence"])
    except ValueError:
        return None
    collected_at = attempt["evidence"].get("completed_at") or attempt["evidence"].get(
        "scope", {}
    ).get("as_of")
    try:
        collected_at = utc(collected_at).isoformat() if collected_at else None
    except ValueError:
        collected_at = None
    return {
        "collection_id": catalog.collection_id,
        "evidence_digest": catalog.digest,
        "collected_at": collected_at,
        "supporting_events": len(attempt["evidence"]["events"]),
    }


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
    row["steps"] = steps.listing(db, attempt_id)
    row["saved_collection"] = saved_collection_binding(row)
    row["local_intel"] = inspect_indicators(selected) if selected else None
    row["prepared_input"] = row["input_snapshot"] or (
        prepare_report(selected) if selected else None
    )
    row["prepared_input_reconstructed"] = bool(selected and not row["input_snapshot"])
    row["human_review"] = reviews.page(db, row) if row["status"] == "validated" else None
    return row


def next_number(db, job_id):
    # Caller holds the job row lock, shared with every other attempt-creation path.
    if db.execute(
        "SELECT id FROM triage_attempts WHERE job_id=%s AND status=ANY(%s)", (job_id, list(ACTIVE))
    ).fetchone():
        raise HTTPException(409, "An investigation is already active for this alert")
    return db.execute(
        "SELECT coalesce(max(number),0)+1 AS n FROM triage_attempts WHERE job_id=%s", (job_id,)
    ).fetchone()["n"]


def request_collection(db, alert_id, user_id, *, automatic=False, workflow="direct"):
    if workflow not in ("direct", "agentic") or (automatic and workflow != "direct"):
        raise HTTPException(400, "Workflow not permitted")
    require_alert(db, alert_id)
    # The job row serializes new attempts, including simultaneous first requests.
    db.execute(
        "INSERT INTO triage_jobs(id,alert_id) VALUES(%s,%s) ON CONFLICT(alert_id) DO NOTHING",
        (uuid4(), alert_id),
    )
    job = db.execute(
        "SELECT id FROM triage_jobs WHERE alert_id=%s FOR UPDATE", (alert_id,)
    ).fetchone()
    number = next_number(db, job["id"])
    if (
        automatic
        and db.execute("SELECT 1 FROM triage_attempts WHERE job_id=%s", (job["id"],)).fetchone()
    ):
        raise HTTPException(409, "This alert already has an investigation attempt")
    identifier = uuid4()
    db.execute(
        """INSERT INTO triage_attempts(id,job_id,number,requested_by,status,workflow)
        VALUES(%s,%s,%s,%s,'pending_collection',%s)""",
        (identifier, job["id"], number, user_id, workflow),
    )
    audit(db, "triage.collection_requested", identifier, user_id)
    return identifier


def reuse_collection(db, alert_id, source_id, body, user_id):
    if not body.acknowledge_historical:
        raise HTTPException(
            400,
            "Explicit acknowledgement of historical evidence is required; this is not model-processing consent",
        )
    source = reviews.load_attempt(db, alert_id, source_id)
    db.execute("SELECT id FROM triage_jobs WHERE id=%s FOR UPDATE", (source["job_id"],)).fetchone()
    number = next_number(db, source["job_id"])
    source = db.execute(
        "SELECT * FROM triage_attempts WHERE id=%s FOR SHARE", (source_id,)
    ).fetchone()
    binding = saved_collection_binding(source)
    if not binding:
        raise HTTPException(
            409, "Only a finished attempt with a valid saved original collection can be reused"
        )
    if binding["evidence_digest"] != body.source_evidence_digest:
        raise HTTPException(
            409, "The saved collection changed; reload before preparing a new attempt"
        )
    reuse = {
        "source_attempt_id": str(source_id),
        "source_attempt_number": source["number"],
        "source_collection_id": binding["collection_id"],
        "source_evidence_digest": binding["evidence_digest"],
        "original_collected_at": binding["collected_at"],
        "reused_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        selected = select_context(
            source["evidence"], profile=body.profile, saved_collection=reuse, workflow=body.workflow
        )
    except ContextBudgetError:
        raise HTTPException(
            413,
            "Saved evidence cannot fit this input budget; choose the broader profile or inspect the original",
        ) from None
    identifier = uuid4()
    db.execute(
        """INSERT INTO triage_attempts(id,job_id,number,requested_by,status,mode,evidence,analysis_evidence,input_snapshot,evidence_digest,provenance,workflow)
        VALUES(%s,%s,%s,%s,'awaiting_approval','manual',%s,%s,%s,%s,%s,%s)""",
        (
            identifier,
            source["job_id"],
            number,
            user_id,
            Jsonb(source["evidence"]),
            Jsonb(selected),
            Jsonb(prepare_report(selected, workflow=body.workflow)),
            EvidenceCatalog(selected).digest,
            Jsonb({"saved_collection": reuse, "evidence_source": "saved_collection"}),
            body.workflow,
        ),
    )
    audit(db, "triage.saved_collection_prepared", identifier, user_id)
    return identifier


def choose_context(db, alert_id, attempt_id, profile, expected_digest, user_id, *, workflow=None):
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
    workflow = workflow or row["workflow"]
    if workflow not in ("direct", "agentic"):
        raise HTTPException(400, "Workflow not permitted")
    try:
        selected = select_context(
            row["evidence"],
            workflow=workflow,
            profile=profile,
            saved_collection=(row["provenance"] or {}).get("saved_collection"),
        )
    except ContextBudgetError:
        raise HTTPException(
            413,
            "This context cannot fit the selected budget; use the broader profile or inspect the local evidence",
        ) from None
    digest = EvidenceCatalog(selected).digest
    db.execute(
        """UPDATE triage_attempts SET status='awaiting_approval',analysis_evidence=%s,input_snapshot=%s,evidence_digest=%s,
        approved_digest=NULL,approved_at=NULL,approved_by=NULL,error_code=NULL,completed_at=NULL,workflow=%s WHERE id=%s""",
        (
            Jsonb(selected),
            Jsonb(prepare_report(selected, workflow=workflow)),
            digest,
            workflow,
            attempt_id,
        ),
    )
    audit(db, "triage.context_selected", attempt_id, user_id)
    return detail(db, alert_id, attempt_id)


def approve(db, alert_id, attempt_id, digest, user_id, *, model_request_limit=1):
    row = db.execute(
        """SELECT a.* FROM triage_attempts a JOIN triage_jobs j ON j.id=a.job_id
        WHERE j.alert_id=%s AND a.id=%s FOR UPDATE OF a""",
        (alert_id, attempt_id),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Investigation attempt not found")
    if row["status"] != "awaiting_approval":
        raise HTTPException(409, "This attempt is not awaiting approval; refresh its state")
    if model_request_limit != (3 if row["workflow"] == "agentic" else 1):
        raise HTTPException(400, "Explicit approval must match this workflow request limit")
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
