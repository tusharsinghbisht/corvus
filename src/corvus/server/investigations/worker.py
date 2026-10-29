"""One bounded collection or one approved model request per cycle; never retry a call.

A session advisory lock elects a single triage consumer. Only its successor can mark
interrupted work terminal. There is no expiring lease that could duplicate a slow request.
Ingestion runs independently in the worker's main thread.
"""

import json
import logging
import os
from threading import Event

from psycopg.types.json import Jsonb

from ... import __version__
from ...analyst import PROMPT_VERSION, analyze, prepare_report
from ...errors import BackendError
from ...evidence import collect
from ...providers import ModelError
from ...providers.azure_foundry import AzureFoundryClient, load_foundry_config
from ...reporting.evidence import EvidenceCatalog
from ..connections import adapter
from ..database import audit, connect

logger = logging.getLogger("corvus.triage")
COLLECTION_SCOPE = {"window_minutes": 5, "ancestry_hours": 6, "limit": 100}
MAX_BUNDLE_BYTES = 16 * 1024 * 1024


def configured_model():
    # Wiring stays here, not in API/frontend settings. No fallback or implicit request.
    config = load_foundry_config()
    return AzureFoundryClient(config), {
        "provider": "azure_foundry",
        "endpoint": config.endpoint,
        "requested_model": config.model,
        "max_tokens": config.max_tokens,
        "timeout_seconds": config.timeout_seconds,
    }


def recover(db):
    rows = db.execute(
        """UPDATE triage_attempts SET
        status=CASE WHEN status='requesting' THEN 'unknown' ELSE 'failed' END,
        error_code=CASE WHEN status='requesting' THEN 'request_interrupted' ELSE 'collection_interrupted' END,
        completed_at=now() WHERE status IN ('collecting','requesting') RETURNING id"""
    ).fetchall()
    for row in rows:
        audit(db, "triage.interrupted", row["id"])


def fail(settings, identifier, status, code):
    with connect(settings) as db:
        db.execute(
            "UPDATE triage_attempts SET status=%s,error_code=%s,completed_at=now() WHERE id=%s",
            (status, code, identifier),
        )
        audit(db, "triage." + status, identifier)


def collect_attempt(settings, attempt, collector):
    identifier = attempt["id"]
    with connect(settings) as db:
        alert = db.execute(
            "SELECT alerts.* FROM alerts JOIN triage_jobs j ON j.alert_id=alerts.id WHERE j.id=%s",
            (attempt["job_id"],),
        ).fetchone()
        connection = db.execute(
            "SELECT * FROM connections WHERE id=%s", (alert["connection_id"],)
        ).fetchone()
    try:
        bundle = collector(
            adapter(settings, connection),
            index=alert["native_index"],
            alert_id=alert["native_id"],
            **COLLECTION_SCOPE,
        )
        if len(json.dumps(bundle, ensure_ascii=False).encode()) > MAX_BUNDLE_BYTES:
            raise ValueError("Collection exceeds the saved bundle bound")
        digest = EvidenceCatalog(bundle).digest
        with connect(settings) as db:
            db.execute(
                """UPDATE triage_attempts SET status='awaiting_approval',evidence=%s,
                evidence_digest=%s WHERE id=%s AND status='collecting'""",
                (Jsonb(bundle), digest, identifier),
            )
            audit(db, "triage.evidence_saved", identifier)
    except Exception as exc:
        code = exc.code if isinstance(exc, BackendError) else "collection_failed"
        fail(settings, identifier, "failed", code)


def analyze_attempt(settings, attempt, model_factory):
    identifier = attempt["id"]
    try:
        prepared = prepare_report(attempt["evidence"])
        if prepared["evidence_digest"] != attempt["approved_digest"]:
            fail(settings, identifier, "failed", "evidence_binding_changed")
            return
        model, provider = model_factory()
        provenance = {
            **provider,
            "prompt_version": PROMPT_VERSION,
            "corvus_version": __version__,
            "revision": os.environ.get("CORVUS_REVISION", "unknown"),
            "collection_scope": COLLECTION_SCOPE,
            "evidence_digest": prepared["evidence_digest"],
        }
    except Exception:
        fail(settings, identifier, "failed", "analysis_configuration_failed")
        return

    # This commit is the no-auto-retry boundary, BEFORE any possibly billable call.
    with connect(settings) as db:
        row = db.execute(
            """UPDATE triage_attempts SET status='requesting',request_started_at=now(),
            provenance=%s WHERE id=%s AND status='queued' RETURNING id""",
            (Jsonb(provenance), identifier),
        ).fetchone()
        if not row:  # A cancellation won the race.
            return
        audit(db, "triage.model_request_started", identifier)

    def save_reply(reply):
        with connect(settings) as db:
            db.execute(
                "UPDATE triage_attempts SET model_reply=%s WHERE id=%s",
                (
                    Jsonb({"content": reply.content, "model": reply.model, "usage": reply.usage}),
                    identifier,
                ),
            )

    try:
        result = analyze(attempt["evidence"], model, on_reply=save_reply)
        with connect(settings) as db:
            db.execute(
                """UPDATE triage_attempts SET status=%s,result=%s,completed_at=now(),
                error_code=NULL WHERE id=%s""",
                (result["status"], Jsonb(result), identifier),
            )
            audit(db, "triage." + result["status"], identifier)
    except Exception as exc:
        if isinstance(exc, ModelError) and exc.reply is not None:
            save_reply(exc.reply)
        # Even a timeout may have completed remotely. Neither failures nor unknowns are retried.
        code = exc.code if isinstance(exc, ModelError) else "analysis_interrupted"
        unknown = code in ("model_connection_failed", "analysis_interrupted")
        fail(settings, identifier, "unknown" if unknown else "failed", code)


def run_once(settings, *, collector=collect, model_factory=configured_model):
    with connect(settings) as lock:
        lock.autocommit = True
        acquired = lock.execute(
            "SELECT pg_try_advisory_lock(hashtext(current_schema() || '.corvus.triage')) AS acquired"
        ).fetchone()["acquired"]
        if not acquired:
            return False
        try:
            with connect(settings) as db:
                recover(db)
                attempt = db.execute(
                    """SELECT * FROM triage_attempts WHERE status IN ('pending_collection','queued')
                    ORDER BY created_at,id LIMIT 1 FOR UPDATE SKIP LOCKED"""
                ).fetchone()
                if attempt and attempt["status"] == "pending_collection":
                    db.execute(
                        """UPDATE triage_attempts SET status='collecting',collection_started_at=now()
                        WHERE id=%s""",
                        (attempt["id"],),
                    )
            if not attempt:
                return False
            if attempt["status"] == "pending_collection":
                collect_attempt(settings, attempt, collector)
            else:
                analyze_attempt(settings, attempt, model_factory)
            return True
        finally:
            lock.execute(
                "SELECT pg_advisory_unlock(hashtext(current_schema() || '.corvus.triage'))"
            )


def run(settings, stop: Event):
    while not stop.is_set():
        try:
            worked = run_once(settings)
        except Exception:
            logger.error("Triage cycle interrupted; no automatic model retry")
            worked = False
        if not worked:
            stop.wait(2)
