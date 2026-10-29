"""Durable triage against disposable PostgreSQL; model/collection are local fakes only."""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Event, Thread
from unittest.mock import Mock, patch
from uuid import uuid4

import psycopg
from fastapi import HTTPException
from psycopg import sql
from psycopg.conninfo import make_conninfo
from test_ingestion import document
from test_server import ServerDatabaseCase

from corvus.analyst import analyze
from corvus.errors import BackendError
from corvus.providers import ModelError, ModelReply
from corvus.reporting.evidence import EvidenceCatalog
from corvus.server.database import connect, initialize
from corvus.server.ingestion import insert_alert
from corvus.server.investigations import service as triage
from corvus.server.investigations.worker import run_once
from corvus.storage import load_json

ROOT = Path(__file__).resolve().parents[1] / "evaluations"


class TriageTests(ServerDatabaseCase):
    def setUp(self):
        super().setUp()
        self.connection_row = self.connection()
        with connect(self.settings) as db:
            insert_alert(db, self.connection_row["id"], document())
            self.alert_id = db.execute("SELECT id FROM alerts").fetchone()["id"]
            self.user_id = db.execute("SELECT id FROM users").fetchone()["id"]
        self.api_path = f"/api/alerts/{self.alert_id}/investigations"
        self.bundle = load_json(ROOT / "fixtures/001.json")
        self.report = load_json(ROOT / "reference-reports/001.json")
        self.model = Mock()
        self.model.complete.return_value = ModelReply(
            json.dumps(self.report), "test-served", {"total_tokens": 30}
        )
        self.factory = Mock(
            return_value=(self.model, {"provider": "test", "requested_model": "test-requested"})
        )
        self.collector = Mock(return_value=self.bundle)
        backend = patch("corvus.server.investigations.worker.adapter", return_value=Mock())
        backend.start()
        self.addCleanup(backend.stop)

    def request(self):
        with connect(self.settings) as db:
            return triage.request_collection(db, self.alert_id, self.user_id)

    def read(self, identifier):
        with connect(self.settings) as db:
            return triage.detail(db, self.alert_id, identifier)

    def tick(self):
        return run_once(self.settings, collector=self.collector, model_factory=self.factory)

    def approve(self, identifier):
        with connect(self.settings) as db:
            triage.approve(
                db,
                self.alert_id,
                identifier,
                self.read(identifier)["evidence_digest"],
                self.user_id,
            )

    def test_full_manual_flow_preserves_exact_evidence_candidate_and_provenance(self):
        identifier = self.request()
        self.assertEqual(self.read(identifier)["status"], "pending_collection")
        self.tick()
        attempt = self.read(identifier)
        self.assertEqual(attempt["status"], "awaiting_approval")
        self.assertEqual(attempt["evidence"], self.bundle)
        self.assertEqual(attempt["evidence_digest"], EvidenceCatalog(self.bundle).digest)
        self.factory.assert_not_called()
        self.tick()
        self.model.complete.assert_not_called()
        self.approve(identifier)
        self.tick()
        attempt = self.read(identifier)
        self.assertEqual(attempt["status"], "validated")
        self.assertEqual(attempt["approved_digest"], attempt["evidence_digest"])
        self.assertEqual(attempt["approved_by"], self.user_id)
        self.assertEqual(attempt["result"]["report"], self.report)
        self.assertEqual(attempt["model_reply"]["content"], json.dumps(self.report))
        self.assertEqual(attempt["result"]["model"]["served_model"], "test-served")
        self.assertEqual(attempt["provenance"]["requested_model"], "test-requested")
        self.assertEqual(attempt["provenance"]["prompt_version"], "0.3")
        self.assertTrue(attempt["result"]["human_review_required"])
        self.model.complete.assert_called_once()
        self.collector.assert_called_once()
        self.assertEqual(self.collector.call_args.kwargs["limit"], 100)
        self.assertEqual(self.collector.call_args.kwargs["alert_id"], "test-event")
        self.assertEqual(attempt["result"]["report"]["response_executed"], False)
        self.tick()
        self.model.complete.assert_called_once()
        retry = self.request()
        self.assertEqual(self.read(retry)["number"], 2)
        self.assertEqual(self.read(identifier)["result"]["report"], self.report)

    def test_authenticated_api_requires_exact_explicit_consent_and_prevents_replays(self):
        self.assertEqual(self.client.get(self.api_path).status_code, 401)
        self.assertEqual(self.client.post(self.api_path, headers=self.headers).status_code, 401)
        self.login()
        response = self.client.post(self.api_path, headers=self.headers)
        self.assertEqual(response.status_code, 201)
        identifier = response.json()["id"]
        path = self.api_path + "/" + identifier
        self.assertEqual(self.client.post(self.api_path, headers=self.headers).status_code, 409)
        self.tick()
        evidence = self.client.get(path).json()
        digest = evidence["evidence_digest"]
        self.assertNotIn("encrypted_password", json.dumps(evidence))
        self.assertIn("instructions", evidence["prepared_input"])
        for body, expected in [
            ({}, 422),
            ({"allow_external": False, "evidence_digest": digest}, 400),
            ({"allow_external": "true", "evidence_digest": digest}, 422),
            ({"allow_external": True, "evidence_digest": "0" * 64}, 409),
        ]:
            self.assertEqual(
                self.client.post(path + "/approve", json=body, headers=self.headers).status_code,
                expected,
            )
        body = {"allow_external": True, "evidence_digest": digest}
        self.assertEqual(self.client.post(path + "/approve", json=body).status_code, 403)
        self.assertEqual(
            self.client.post(path + "/approve", json=body, headers=self.headers).status_code, 200
        )
        self.assertEqual(
            self.client.post(path + "/approve", json=body, headers=self.headers).status_code, 409
        )
        self.assertEqual(
            self.client.get(f"/api/alerts/{uuid4()}/investigations/{identifier}").status_code, 404
        )
        self.assertEqual(self.client.get(self.api_path).json()["attempts"][0]["status"], "queued")
        self.assertNotIn("evidence", self.client.get(self.api_path).json()["attempts"][0])

    def test_simultaneous_requests_allow_one_active_attempt(self):
        def request():
            try:
                return self.request()
            except HTTPException as exc:
                return exc.status_code

        with ThreadPoolExecutor(max_workers=4) as pool:
            outcomes = list(pool.map(lambda _: request(), range(4)))
        self.assertEqual(outcomes.count(409), 3)
        with connect(self.settings) as db:
            self.assertEqual(
                db.execute("SELECT count(*) AS n FROM triage_attempts").fetchone()["n"], 1
            )

    def test_partial_evidence_and_rejected_candidate_survive(self):
        self.bundle["status"] = "partial"
        self.bundle["gaps"].append({"code": "collection_unavailable", "message": "test gap"})
        identifier = self.request()
        self.tick()
        self.approve(identifier)
        self.model.complete.return_value = ModelReply(
            "not valid JSON <script>untrusted</script>", "test", {}
        )
        self.tick()
        attempt = self.read(identifier)
        self.assertEqual(attempt["status"], "rejected")
        self.assertEqual(attempt["evidence"]["status"], "partial")
        self.assertIn("not valid JSON", attempt["result"]["unparseable_output"])
        self.assertFalse(attempt["result"]["validation"]["valid"])

    def test_candidate_saved_before_validation_failure_and_not_retried(self):
        identifier = self.request()
        self.tick()
        self.approve(identifier)

        def fail_after_reply(bundle, model, **kwargs):
            with patch(
                "corvus.analyst.validate_report", side_effect=RuntimeError("private details")
            ):
                return analyze(bundle, model, **kwargs)

        with patch("corvus.server.investigations.worker.analyze", side_effect=fail_after_reply):
            self.tick()
        attempt = self.read(identifier)
        self.assertEqual(attempt["status"], "unknown")
        self.assertIsNotNone(attempt["model_reply"])
        self.assertEqual(attempt["error_code"], "analysis_interrupted")
        self.tick()
        self.model.complete.assert_called_once()

    def test_crash_recovery_preserves_ambiguous_attempt_without_calling_again(self):
        identifier = self.request()
        self.tick()
        self.approve(identifier)
        with connect(self.settings) as db:
            db.execute(
                "UPDATE triage_attempts SET status='requesting',request_started_at=now() WHERE id=%s",
                (identifier,),
            )
        self.tick()
        attempt = self.read(identifier)
        self.assertEqual(attempt["status"], "unknown")
        self.assertEqual(attempt["error_code"], "request_interrupted")
        self.assertEqual(attempt["evidence"], self.bundle)
        self.factory.assert_not_called()
        self.model.complete.assert_not_called()
        retry = self.request()
        self.tick()
        self.assertEqual(self.read(retry)["status"], "awaiting_approval")
        self.model.complete.assert_not_called()

    def test_live_consumer_is_not_recovered_or_duplicated_by_another_worker(self):
        identifier = self.request()
        self.tick()
        self.approve(identifier)
        entered, release = Event(), Event()

        def complete(messages):
            entered.set()
            self.assertTrue(release.wait(15))
            return ModelReply(json.dumps(self.report), "test", {})

        self.model.complete.side_effect = complete
        thread = Thread(target=self.tick)
        thread.start()
        try:
            self.assertTrue(entered.wait(15))
            self.assertFalse(self.tick())
            self.assertEqual(self.read(identifier)["status"], "requesting")
            with connect(self.settings) as db, self.assertRaises(HTTPException):
                triage.cancel(db, self.alert_id, identifier, self.user_id)
        finally:
            release.set()
            thread.join(20)
        self.assertEqual(self.read(identifier)["status"], "validated")
        self.model.complete.assert_called_once()

    def test_collection_crash_failure_and_configuration_failure_are_terminal(self):
        identifier = self.request()
        with connect(self.settings) as db:
            db.execute("UPDATE triage_attempts SET status='collecting' WHERE id=%s", (identifier,))
        self.tick()
        self.assertEqual(self.read(identifier)["error_code"], "collection_interrupted")
        identifier = self.request()
        self.collector.side_effect = BackendError("read_denied", "private error must not leak")
        self.tick()
        self.assertEqual(self.read(identifier)["error_code"], "read_denied")
        self.assertNotIn("private error", json.dumps(self.read(identifier), default=str))
        identifier = self.request()
        self.collector.side_effect = None
        self.tick()
        self.approve(identifier)
        self.factory.side_effect = ValueError("secret configuration")
        self.tick()
        self.assertEqual(self.read(identifier)["error_code"], "analysis_configuration_failed")
        self.assertIsNone(self.read(identifier)["request_started_at"])
        self.tick()
        self.model.complete.assert_not_called()

    def test_transport_timeout_has_unknown_outcome_without_auto_retry(self):
        identifier = self.request()
        self.tick()
        self.approve(identifier)
        self.model.complete.side_effect = ModelError(
            "model_connection_failed", "private transport details"
        )
        self.tick()
        self.assertEqual(self.read(identifier)["status"], "unknown")
        self.assertEqual(self.read(identifier)["error_code"], "model_connection_failed")
        self.tick()
        self.model.complete.assert_called_once()

    def test_cancellation_and_digest_tampering_cannot_send_evidence(self):
        identifier = self.request()
        self.tick()
        self.approve(identifier)
        with connect(self.settings) as db:
            triage.cancel(db, self.alert_id, identifier, self.user_id)
        self.tick()
        self.model.complete.assert_not_called()
        identifier = self.request()
        self.tick()
        self.approve(identifier)
        with connect(self.settings) as db:
            db.execute(
                "UPDATE triage_attempts SET evidence=jsonb_set(evidence,'{status}','\"partial\"') WHERE id=%s",
                (identifier,),
            )
        self.tick()
        self.assertEqual(self.read(identifier)["error_code"], "evidence_binding_changed")
        self.factory.assert_not_called()

    def test_incomplete_provider_candidate_is_preserved_as_failed(self):
        identifier = self.request()
        self.tick()
        self.approve(identifier)
        self.model.complete.side_effect = ModelError(
            "incomplete_model_response",
            "Incomplete",
            reply=ModelReply('{"partial":', "test-served", {"total_tokens": 99}),
        )
        self.tick()
        attempt = self.read(identifier)
        self.assertEqual(attempt["status"], "failed")
        self.assertEqual(attempt["model_reply"]["content"], '{"partial":')
        self.assertEqual(attempt["model_reply"]["usage"]["total_tokens"], 99)
        self.assertIsNone(attempt["result"])
        self.tick()
        self.model.complete.assert_called_once()

    def test_upgrade_from_version_one_preserves_existing_alerts(self):
        schema = "corvus_upgrade_" + uuid4().hex
        with psycopg.connect(self.base) as db:
            db.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        config = replace(
            self.settings, database_url=make_conninfo(self.base, options="-csearch_path=" + schema)
        )
        try:
            with connect(config) as db:
                db.execute("CREATE TABLE schema_versions(version integer PRIMARY KEY)")
                db.execute(
                    Path(__file__)
                    .resolve()
                    .parents[1]
                    .joinpath("src/corvus/server/schema.sql")
                    .read_text()
                )
            # Seed version 1 with an existing operator, connection and alert.
            with connect(self.settings) as db:
                user = db.execute("SELECT * FROM users").fetchone()
                connection = db.execute("SELECT * FROM connections").fetchone()
            with connect(config) as db:
                db.execute(
                    "INSERT INTO users(id,username,password_hash) VALUES(%s,%s,%s)",
                    (user["id"], user["username"], user["password_hash"]),
                )
                db.execute(
                    "INSERT INTO connections(id,name,indexer_url,username,encrypted_password,backfill_start,checkpoint) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                    tuple(
                        connection[key]
                        for key in (
                            "id",
                            "name",
                            "indexer_url",
                            "username",
                            "encrypted_password",
                            "backfill_start",
                            "checkpoint",
                        )
                    ),
                )
                insert_alert(db, connection["id"], document())
            initialize(config)
            initialize(config)
            with connect(config) as db:
                self.assertEqual(
                    db.execute("SELECT max(version) AS v FROM schema_versions").fetchone()["v"], 2
                )
                self.assertEqual(db.execute("SELECT count(*) AS n FROM alerts").fetchone()["n"], 1)
                self.assertEqual(
                    db.execute("SELECT count(*) AS n FROM triage_attempts").fetchone()["n"], 0
                )
        finally:
            with psycopg.connect(self.base) as db:
                db.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))

    def test_schema_initialization_is_repeatable_and_integrity_is_enforced(self):
        initialize(self.settings)
        initialize(self.settings)
        identifier = self.request()
        with self.assertRaises(psycopg.errors.CheckViolation), connect(self.settings) as db:
            db.execute("UPDATE triage_attempts SET status='queued' WHERE id=%s", (identifier,))
