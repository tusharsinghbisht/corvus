"""Read-only investigation/review summaries; never return model output in queue rows."""

from .reviews import report_digest

REVIEW_JOIN = """LEFT JOIN LATERAL (
    SELECT id,decision,report_digest FROM report_reviews WHERE attempt_id=a.id
    ORDER BY sequence DESC LIMIT 1
) r ON true"""


def review_summary(row):
    result = row.pop("reviewed_result", None)
    digest = row.pop("review_report_digest", None)
    stale = bool(digest and (not result or digest != report_digest(result)))
    decision = row.pop("review_decision", None)
    row["review_stale"] = stale
    row["review_status"] = "pending" if stale or not decision else decision
    return row


def enrich_alerts(db, alerts):
    if not alerts:
        return
    # Enrich only the displayed page, not every alert scanned for time/severity statistics.
    summaries = db.execute(
        """SELECT j.alert_id,latest.status AS attempt_status,report.id AS report_attempt_id,
        r.decision AS review_decision,r.report_digest AS review_report_digest,
        CASE WHEN r.id IS NOT NULL THEN report.result END AS reviewed_result
        FROM triage_jobs j
        LEFT JOIN LATERAL (SELECT status FROM triage_attempts WHERE job_id=j.id ORDER BY number DESC LIMIT 1) latest ON true
        LEFT JOIN LATERAL (SELECT id,result FROM triage_attempts WHERE job_id=j.id AND status='validated' ORDER BY number DESC LIMIT 1) report ON true
        LEFT JOIN LATERAL (SELECT id,decision,report_digest FROM report_reviews WHERE attempt_id=report.id ORDER BY sequence DESC LIMIT 1) r ON true
        WHERE j.alert_id=ANY(%s)""",
        ([row["id"] for row in alerts],),
    ).fetchall()
    by_alert = {}
    for summary in summaries:
        alert_id = summary.pop("alert_id")
        by_alert[alert_id] = review_summary(summary)
        if not summary["report_attempt_id"]:
            summary["review_status"] = None
    for alert in alerts:
        alert["investigation"] = by_alert.get(alert["id"])


def analyst(db, review_filter="all"):
    filters = {
        "all": "true",
        "pending": "a.status='validated' AND r.id IS NULL",
        "accepted": "a.status='validated' AND r.decision='accepted'",
        "rejected": "a.status='validated' AND r.decision='rejected'",
        "follow_up": "a.status='validated' AND r.decision='follow_up'",
    }
    stats = db.execute(f"""SELECT count(*) AS total,
        count(*) FILTER(WHERE a.status IN ('pending_collection','collecting','awaiting_approval','queued','requesting')) AS active,
        count(*) FILTER(WHERE a.status='validated') AS reports,
        count(*) FILTER(WHERE a.status IN ('failed','unknown','rejected')) AS attention,
        count(*) FILTER(WHERE a.status='validated' AND r.id IS NULL) AS pending_review,
        count(*) FILTER(WHERE a.status='validated' AND r.decision='accepted') AS accepted_assessments,
        count(*) FILTER(WHERE a.status='validated' AND r.decision='rejected') AS rejected_assessments,
        count(*) FILTER(WHERE a.status='validated' AND r.decision='follow_up') AS follow_up
        FROM triage_attempts a {REVIEW_JOIN}""").fetchone()
    attempts = db.execute(f"""SELECT a.id,a.number,a.status,a.mode,a.workflow,a.created_at,a.completed_at,a.error_code,
        (SELECT phase FROM investigation_steps WHERE attempt_id=a.id ORDER BY position DESC LIMIT 1) AS current_step,
        j.alert_id,e.title,e.rule_level,e.agent_name,a.result->'report'->>'disposition' AS disposition,
        r.decision AS review_decision,r.report_digest AS review_report_digest,
        CASE WHEN r.id IS NOT NULL THEN a.result END AS reviewed_result
        FROM triage_attempts a JOIN triage_jobs j ON j.id=a.job_id JOIN alerts e ON e.id=j.alert_id
        {REVIEW_JOIN} WHERE {filters[review_filter]}
        ORDER BY a.created_at DESC,a.id DESC LIMIT 50""").fetchall()
    for attempt in attempts:
        review_summary(attempt)
        if attempt["status"] != "validated":
            attempt["review_status"] = None
    return {"stats": stats, "attempts": attempts}
