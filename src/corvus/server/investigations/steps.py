"""Durable, bounded activity ledger. A started remote step is never replayed."""

import json
from uuid import uuid4

from psycopg.types.json import Jsonb

from ..database import audit, connect


def listing(db, attempt_id):
    return db.execute(
        "SELECT id,position,phase,state,model_request,started_at,completed_at,error_code,output FROM investigation_steps WHERE attempt_id=%s ORDER BY position",
        (attempt_id,),
    ).fetchall()


def tasks(db, phase):
    rows = db.execute(
        """SELECT s.id,s.phase,s.state,s.error_code,s.started_at,s.attempt_id,t.number,t.status AS attempt_status,
        j.alert_id,e.title,e.agent_name,s.input_snapshot->>'question' AS question,
        CASE WHEN s.phase='correlation' THEN jsonb_array_length(coalesce(s.output->'matches','[]'::jsonb)) ELSE jsonb_array_length(coalesce(s.output->'indicators','[]'::jsonb)) END AS items
        FROM investigation_steps s JOIN triage_attempts t ON t.id=s.attempt_id JOIN triage_jobs j ON j.id=t.job_id JOIN alerts e ON e.id=j.alert_id
        WHERE s.phase=%s ORDER BY s.started_at DESC,s.id DESC LIMIT 30""",
        (phase,),
    ).fetchall()
    return {"kind": phase, "tasks": rows}


def recorder(settings, attempt_id):
    def record(event, token, payload):
        with connect(settings) as db:
            if event == "start":
                phase = token
                attempt = db.execute(
                    "SELECT status,workflow FROM triage_attempts WHERE id=%s FOR UPDATE",
                    (attempt_id,),
                ).fetchone()
                rows = db.execute(
                    "SELECT phase,model_request FROM investigation_steps WHERE attempt_id=%s ORDER BY position",
                    (attempt_id,),
                ).fetchall()
                model = phase in ("plan", "assessment")
                if (
                    not attempt
                    or attempt["status"] != "requesting"
                    or attempt["workflow"] != "agentic"
                    or phase not in ("plan", "assessment", "correlation", "intel")
                    or len(rows) >= 5
                ):
                    raise ValueError("Unauthorized workflow step")
                if model and (
                    sum(row["model_request"] for row in rows) >= 3
                    or sum(row["phase"] == phase for row in rows) >= (2 if phase == "plan" else 1)
                ):
                    raise ValueError("Approved model request budget exhausted")
                if not model and any(row["phase"] == phase for row in rows):
                    raise ValueError("Capability already used")
                if len(json.dumps(payload, ensure_ascii=False).encode()) > 128 * 1024:
                    raise ValueError("Step input bound exceeded")
                identifier = uuid4()
                db.execute(
                    "INSERT INTO investigation_steps(id,attempt_id,position,phase,state,model_request,input_snapshot) VALUES(%s,%s,%s,%s,'running',%s,%s)",
                    (identifier, attempt_id, len(rows) + 1, phase, model, Jsonb(payload)),
                )
                audit(db, "triage.step_started", identifier)
                return identifier
            if event == "invalid_plan":
                db.execute(
                    "UPDATE investigation_steps SET state='failed',error_code='invalid_investigation_plan' WHERE id=(SELECT id FROM investigation_steps WHERE attempt_id=%s AND phase='plan' ORDER BY position DESC LIMIT 1)",
                    (attempt_id,),
                )
                return
            state = (
                "completed"
                if event == "complete"
                else (
                    "unknown"
                    if payload.get("code") in ("model_connection_failed", "analysis_interrupted")
                    else "failed"
                )
            )
            db.execute(
                "UPDATE investigation_steps SET state=%s,completed_at=now(),output=%s,error_code=%s WHERE id=%s AND attempt_id=%s AND state='running'",
                (
                    state,
                    Jsonb(payload),
                    payload.get("code") if event != "complete" else None,
                    token,
                    attempt_id,
                ),
            )

    return record
