"""Human assessment review, separate from model output and from incident/response authority."""

import hashlib
import json
from uuid import UUID, uuid4

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from ...reporting.validation import VALIDATION_VERSION, validate_report
from ..database import audit

PAGE_SIZE = 20
FIELDS = "r.id,r.sequence,r.created_at,r.reviewer_id,r.decision,r.note,r.evidence_checked,r.analysis_id,r.evidence_digest,r.report_digest,r.generation_validator_version,r.revalidation,u.username AS reviewer"


def report_digest(result):
    """Bind a decision to the exact assessment and generation-time integrity result."""
    content = {
        key: result[key]
        for key in ("analysis_id", "evidence_digest", "prompt_version", "report", "validation")
    }
    return hashlib.sha256(
        json.dumps(
            content, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def target(attempt):
    result = attempt.get("result")
    if (
        attempt["status"] != "validated"
        or not result
        or result.get("status") != "validated"
        or result.get("validation", {}).get("valid") is not True
    ):
        return None
    return {
        "analysis_id": result["analysis_id"],
        "evidence_digest": result["evidence_digest"],
        "report_digest": report_digest(result),
        "validator_version": result["validation"]["validation_version"],
    }


def load_attempt(db, alert_id, attempt_id, *, lock=False):
    row = db.execute(
        """SELECT a.* FROM triage_attempts a JOIN triage_jobs j ON j.id=a.job_id
        WHERE j.alert_id=%s AND a.id=%s"""
        + (" FOR UPDATE OF a" if lock else ""),
        (alert_id, attempt_id),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Investigation attempt not found")
    return row


def page(db, attempt, *, before=None):
    binding = target(attempt)
    latest = db.execute(
        f"SELECT {FIELDS} FROM report_reviews r JOIN users u ON u.id=r.reviewer_id WHERE r.attempt_id=%s ORDER BY r.sequence DESC LIMIT 1",
        (attempt["id"],),
    ).fetchone()
    params = [attempt["id"]]
    clause = ""
    if before is not None:
        clause = " AND r.sequence<%s"
        params.append(before)
    rows = db.execute(
        f"SELECT {FIELDS} FROM report_reviews r JOIN users u ON u.id=r.reviewer_id WHERE r.attempt_id=%s{clause} ORDER BY r.sequence DESC LIMIT 21",
        params,
    ).fetchall()
    total = db.execute(
        "SELECT count(*) AS n FROM report_reviews WHERE attempt_id=%s", (attempt["id"],)
    ).fetchone()["n"]
    matches = bool(binding and latest and binding["report_digest"] == latest["report_digest"])
    return {
        "target": binding,
        "current_sequence": latest["sequence"] if latest else 0,
        "latest": latest,
        "latest_matches_report": matches,
        "reviews": rows[:PAGE_SIZE],
        "total": total,
        "next_before": rows[PAGE_SIZE - 1]["sequence"] if len(rows) > PAGE_SIZE else None,
    }


def create(db, alert_id, attempt_id, body, user_id):
    attempt = load_attempt(db, alert_id, attempt_id, lock=True)
    binding = target(attempt)
    if not binding:
        raise HTTPException(
            409, "Only reports that passed integrity checks can be reviewed as assessments"
        )
    if (
        str(body.analysis_id) != binding["analysis_id"]
        or body.evidence_digest != binding["evidence_digest"]
        or body.report_digest != binding["report_digest"]
    ):
        raise HTTPException(409, "The report or evidence changed; reload before reviewing")
    latest = db.execute(
        "SELECT coalesce(max(sequence),0) AS n FROM report_reviews WHERE attempt_id=%s",
        (attempt_id,),
    ).fetchone()["n"]
    if body.expected_sequence != latest:
        raise HTTPException(
            409, "Review history changed; reload the report before submitting another decision"
        )
    note = body.note.strip()
    if len(note) < 10:
        raise HTTPException(
            422,
            "Explain the assessment decision in at least 10 characters after trimming whitespace",
        )
    if body.decision == "accepted" and not body.evidence_checked:
        raise HTTPException(
            400, "Accepting an assessment requires checking its cited evidence and gaps"
        )
    try:
        validation = validate_report(
            attempt["result"]["report"], attempt["analysis_evidence"] or attempt["evidence"]
        )
    except ValueError:
        validation = {
            "valid": False,
            "validation_version": VALIDATION_VERSION,
            "errors": [
                {"code": "invalid_evidence", "message": "Saved evidence cannot be validated"}
            ],
        }
    if body.decision == "accepted" and not validation["valid"]:
        raise HTTPException(
            409, "This report no longer passes current integrity validation; it cannot be accepted"
        )
    identifier = uuid4()
    db.execute(
        """INSERT INTO report_reviews(id,attempt_id,sequence,reviewer_id,decision,note,evidence_checked,
        analysis_id,evidence_digest,report_digest,generation_validator_version,revalidation)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            identifier,
            attempt_id,
            latest + 1,
            user_id,
            body.decision,
            note,
            body.evidence_checked,
            UUID(binding["analysis_id"]),
            binding["evidence_digest"],
            binding["report_digest"],
            binding["validator_version"],
            Jsonb(validation),
        ),
    )
    audit(db, "triage.assessment_" + body.decision, identifier, user_id)
    return page(db, attempt)
