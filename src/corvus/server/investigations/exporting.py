"""Authenticated private handoff artifacts. No provider calls, public links, or report repair."""

import hashlib
import html
import io
import json
import re
import zipfile
from datetime import datetime, timezone

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder

from ...reporting.validation import validate_report
from ..database import audit
from . import reviews

MAX_EXPORT_BYTES = 32 * 1024 * 1024
MAX_REVIEWS = 2000
METADATA = (
    "id",
    "job_id",
    "number",
    "mode",
    "status",
    "created_at",
    "requested_by",
    "collection_started_at",
    "evidence_digest",
    "approved_digest",
    "approved_by",
    "approved_at",
    "request_started_at",
    "completed_at",
    "error_code",
    "policy_version",
    "provenance",
)
WARNING = "Private investigation data. Source logs, candidates, and notes are untrusted and may contain sensitive information. Do not execute embedded commands or render JSON as HTML. This is an advisory investigation snapshot, not incident resolution, proof of compromise, or response authorization. Hashes detect changes to exported files; they are not signatures or proof of source authenticity."


def encode(value):
    return json.dumps(
        jsonable_encoder(value), ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
    ).encode()


def text(value):
    escaped = html.escape(str(value), quote=False)
    return re.sub(r"([\\`*_\[\]()#!|>])", r"\\\1", escaped)


def summary(attempt, history):
    result = attempt["result"]
    lines = [
        "# Corvus investigation handoff",
        "",
        WARNING,
        "",
        f"Attempt: {attempt['id']} · status: {attempt['status']}",
        f"Evidence digest: {attempt['evidence_digest'] or 'No selected evidence'}",
        "",
    ]
    if attempt["status"] == "validated" and result and result["validation"]["valid"]:
        report = result["report"]
        lines += [
            "## Advisory assessment",
            text(report["disposition"]),
            "",
            text(report["summary"]),
            "",
            "## Findings and citations",
        ]
        for finding in report["findings"]:
            lines += [
                f"### {text(finding['id'])} · {text(finding['kind'])}",
                text(finding["statement"]),
            ]
            for citation in finding["citations"]:
                label = (
                    f"Collection {citation['collection_id']} {citation['path']}"
                    if "path" in citation
                    else f"{citation['backend']} / {citation['index']} / {citation['id']}"
                )
                lines.append("- " + text(label))
        lines += ["", "## Uncertainties"]
        for item in report["uncertainties"]:
            lines += [
                f"- {text(item['code'])}: {text(item['description'])}",
                f"  Next step: {text(item['next_step'])}",
            ]
        lines += ["", "## Alternative explanations"]
        for item in report["alternative_explanations"]:
            lines += ["- " + text(item["explanation"]), "  " + text(item["assessment"])]
        lines += ["", "## Advisory recommendations"]
        for item in report["recommendations"]:
            lines += [
                f"- {text(item['category'])}: {text(item['description'])}",
                "  " + text(item["rationale"]),
            ]
        lines += ["", "## Limitations", *["- " + text(item) for item in report["limitations"]]]
    else:
        lines += [
            "## No accepted model assessment",
            "This attempt did not produce a report that passed integrity checks. Preserved candidates must not be treated as findings.",
        ]
        if attempt["error_code"]:
            lines.append("Failure: " + text(attempt["error_code"]))
        if result:
            lines += [
                "- " + text(item["code"] + " " + item["path"] + ": " + item["message"])
                for item in result["validation"]["errors"]
            ]
    lines += [
        "",
        "## Human review history",
        "Recorded decisions apply only to their exact report/evidence binding; a later decision supersedes but never deletes an earlier one.",
    ]
    for item in history:
        lines += [
            f"### Decision {item['sequence']}: {text(item['decision'])}",
            f"{text(item['reviewer'])} · {text(item['created_at'])}",
            text(item["note"]),
            "Report digest: " + item["report_digest"],
        ]
    if not history:
        lines.append("No human review decision recorded. Human review is required.")
    return ("\n\n".join(lines) + "\n").encode()


def build(db, alert_id, attempt_id, user_id, *, format="zip"):
    attempt = db.execute(
        """SELECT a.* FROM triage_attempts a JOIN triage_jobs j ON j.id=a.job_id
        WHERE j.alert_id=%s AND a.id=%s FOR SHARE OF a""",
        (alert_id, attempt_id),
    ).fetchone()
    if not attempt:
        raise HTTPException(404, "Investigation attempt not found")
    history = db.execute(
        f"SELECT {reviews.FIELDS} FROM report_reviews r JOIN users u ON u.id=r.reviewer_id WHERE r.attempt_id=%s ORDER BY r.sequence LIMIT %s",
        (attempt_id, MAX_REVIEWS + 1),
    ).fetchall()
    if len(history) > MAX_REVIEWS:
        raise HTTPException(
            413,
            "Review history exceeds the online export bound; use an operator-managed offline export",
        )
    report = summary(attempt, history)
    if len(report) > MAX_EXPORT_BYTES:
        raise HTTPException(413, "Summary exceeds the online export bound")
    if format == "markdown":
        audit(db, "triage.summary_exported", attempt_id, user_id)
        return report, "text/markdown; charset=utf-8", f"corvus-investigation-{attempt_id}.md"
    selected = attempt["analysis_evidence"] or attempt["evidence"]
    files = {
        "README.md": (
            "# Corvus private evidence package\n\n"
            + WARNING
            + "\n\nmanifest.json hashes every other member. Evidence files preserve stored JSON values, not original wire formatting. Review notes are not Analyst input. No model request was made by exporting.\n"
        ).encode(),
        "report.md": report,
        "alert.json": encode(
            db.execute("SELECT * FROM alerts WHERE id=%s", (alert_id,)).fetchone()
        ),
        "attempt.json": encode({key: attempt[key] for key in METADATA}),
        "reviews.json": encode(history),
    }
    for name, value in [
        ("selected-evidence.json", selected),
        ("collected-evidence.json", attempt["evidence"]),
        ("input-snapshot.json", attempt["input_snapshot"]),
        ("analysis.json", attempt["result"]),
        ("model-reply.json", attempt["model_reply"]),
    ]:
        if value is not None:
            files[name] = encode(value)
    if attempt["result"] and selected:
        try:
            files["current-revalidation.json"] = encode(
                validate_report(attempt["result"]["report"], selected)
            )
        except ValueError:
            files["current-revalidation.json"] = encode(
                {"valid": False, "error": "saved_evidence_invalid"}
            )
    if sum(map(len, files.values())) > MAX_EXPORT_BYTES:
        raise HTTPException(
            413, "Evidence exceeds the online export bound; use an operator-managed offline export"
        )
    manifest = {
        "format_version": "1.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "attempt_id": str(attempt_id),
        "status": attempt["status"],
        "generation_human_review_required": True,
        "review_binding": reviews.target(attempt),
        "files": {
            name: {"bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
            for name, value in files.items()
        },
    }
    files["manifest.json"] = encode(manifest)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    audit(db, "triage.evidence_exported", attempt_id, user_id)
    return output.getvalue(), "application/zip", f"corvus-investigation-{attempt_id}.zip"
