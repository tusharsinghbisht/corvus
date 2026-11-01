from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from test_ingestion import document
from test_server import ServerDatabaseCase

from corvus.agents.analyst.context import select_context
from corvus.providers import ModelError, ModelReply
from corvus.reporting.evidence import EvidenceCatalog
from corvus.server.database import connect
from corvus.server.ingestion import insert_alert
from corvus.server.investigations import policy
from corvus.server.investigations.worker import run_once
from corvus.storage import load_json

ROOT = Path(__file__).resolve().parents[1] / "evaluations"


class AnalystPolicyTests(ServerDatabaseCase):
    def setUp(self):
        super().setUp()
        self.connection_row = self.connection()
        self.connection_id = self.connection_row["id"]
        self.path = f"/api/settings/analyst/connections/{self.connection_id}"
        self.login()
        with connect(self.settings) as db:
            db.execute("UPDATE analyst_settings SET daily_limit=20")
        self.bundle = load_json(ROOT / "fixtures/001.json")
        report = load_json(ROOT / "reference-reports/001.json")
        report["evidence_digest"] = EvidenceCatalog(select_context(self.bundle)).digest
        import json

        self.model = Mock()
        self.model.complete.return_value = ModelReply(json.dumps(report), "test", {})
        self.factory = Mock(return_value=(self.model, {"provider": "test"}))
        self.collector = Mock(return_value=self.bundle)
        backend = patch("corvus.server.investigations.worker.adapter", return_value=Mock())
        backend.start()
        self.addCleanup(backend.stop)

    def body(self, **changes):
        current = self.client.get("/api/settings/analyst").json()["policies"][0]
        return (
            dict(
                enabled=True,
                allow_external=True,
                minimum_level=12,
                hourly_limit=2,
                daily_limit=10,
                version=current["version"],
            )
            | changes
        )

    def enable(self, **changes):
        response = self.client.put(self.path, json=self.body(**changes), headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        # Simulate activation ten minutes ago; never wait wall-clock minutes in tests.
        with connect(self.settings) as db:
            db.execute(
                "UPDATE analyst_policies SET activated_at=now()-interval '10 minutes' WHERE connection_id=%s",
                (self.connection_id,),
            )

    def alert(self, identifier="eligible", age=6, level=12, received_before_activation=False):
        with connect(self.settings) as db:
            insert_alert(
                db,
                self.connection_id,
                document(
                    identifier,
                    timestamp=(datetime.now(timezone.utc) - timedelta(minutes=age)).isoformat(),
                    level=level,
                ),
            )
            row = db.execute("SELECT id FROM alerts WHERE native_id=%s", (identifier,)).fetchone()[
                "id"
            ]
            if received_before_activation:
                db.execute(
                    "UPDATE alerts SET received_at=now()-interval '20 minutes' WHERE id=%s", (row,)
                )
            return row

    def reserve(self):
        with connect(self.settings) as db:
            return policy.schedule(db)

    def tick(self):
        return run_once(self.settings, collector=self.collector, model_factory=self.factory)

    def test_default_manual_and_strict_standing_consent(self):
        self.assertFalse(self.client.get("/api/settings/analyst").json()["policies"][0]["enabled"])
        self.alert()
        self.assertIsNone(self.reserve())
        self.assertEqual(
            self.client.put(
                self.path, json=self.body(allow_external=False), headers=self.headers
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.put(
                self.path, json=self.body(allow_external="true"), headers=self.headers
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.put(
                self.path, json=self.body(minimum_level=1), headers=self.headers
            ).status_code,
            422,
        )
        self.assertEqual(self.client.put(self.path, json=self.body()).status_code, 403)
        self.assertEqual(
            self.client.put(
                self.path, json=self.body(version=99), headers=self.headers
            ).status_code,
            409,
        )
        self.model.complete.assert_not_called()

    def test_no_backlog_recent_or_low_severity_and_no_previously_received_alerts(self):
        self.enable()
        self.alert("old", age=60)
        self.alert("before-activation", age=11)
        self.alert("too-new", age=1)
        self.alert("low", level=7)
        self.alert("already-received", received_before_activation=True)
        self.assertIsNone(self.reserve())
        eligible = self.alert("new-high")
        identifier = self.reserve()
        self.assertIsNotNone(identifier)
        with connect(self.settings) as db:
            row = db.execute(
                "SELECT a.*,j.alert_id FROM triage_attempts a JOIN triage_jobs j ON j.id=a.job_id"
            ).fetchone()
            self.assertEqual(row["alert_id"], eligible)
            self.assertEqual(row["mode"], "automatic")
            self.assertIsNotNone(row["policy_version"])
        self.assertIsNone(self.reserve())

    def test_automatic_collection_authorization_and_one_langgraph_request(self):
        self.enable()
        self.alert()
        self.tick()
        with connect(self.settings) as db:
            row = db.execute("SELECT * FROM triage_attempts").fetchone()
        self.assertEqual(row["status"], "queued")
        self.assertEqual(row["approved_digest"], row["evidence_digest"])
        self.factory.assert_not_called()
        self.tick()
        self.tick()
        with connect(self.settings) as db:
            row = db.execute("SELECT * FROM triage_attempts").fetchone()
        self.assertEqual(row["status"], "validated")
        self.assertIn("automatic_policy", row["provenance"])
        self.assertEqual(row["result"]["orchestration"]["framework"], "langgraph")
        self.model.complete.assert_called_once()

    def test_budget_reservations_are_durable_and_not_refunded_by_cancellation(self):
        self.enable(hourly_limit=1)
        self.alert("one")
        self.alert("two")
        identifier = self.reserve()
        self.assertIsNotNone(identifier)
        with connect(self.settings) as db:
            db.execute(
                "UPDATE triage_attempts SET status='cancelled',completed_at=now() WHERE id=%s",
                (identifier,),
            )
        self.assertIsNone(self.reserve())
        data = self.client.get("/api/settings/analyst").json()
        self.assertEqual(data["policies"][0]["used_hour"], 1)
        self.assertEqual(data["global_used_day"], 1)

    def test_global_daily_cap_is_enforced(self):
        self.enable(hourly_limit=20, daily_limit=100)
        self.assertEqual(
            self.client.put(
                "/api/settings/analyst/budget", json={"daily_limit": 1}, headers=self.headers
            ).status_code,
            200,
        )
        self.alert("one")
        self.alert("two")
        self.assertIsNotNone(self.reserve())
        self.assertIsNone(self.reserve())

    def test_disable_and_policy_edits_invalidate_unstarted_work(self):
        self.enable()
        self.alert()
        self.tick()
        response = self.client.put(
            self.path, json=self.body(enabled=False, allow_external=False), headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        self.tick()
        with connect(self.settings) as db:
            row = db.execute("SELECT status,error_code FROM triage_attempts").fetchone()
        self.assertEqual(row["status"], "cancelled")
        self.assertEqual(row["error_code"], "automation_policy_changed")
        self.model.complete.assert_not_called()

    def test_pause_or_expired_window_prevents_send(self):
        self.enable()
        self.alert()
        self.tick()
        with connect(self.settings) as db:
            db.execute("UPDATE connections SET enabled=false")
        self.tick()
        self.model.complete.assert_not_called()
        with connect(self.settings) as db:
            self.assertEqual(
                db.execute("SELECT status FROM triage_attempts").fetchone()["status"], "cancelled"
            )

    def test_ambiguous_automatic_call_is_never_retried(self):
        self.enable()
        self.alert()
        self.tick()
        self.model.complete.side_effect = ModelError("model_connection_failed", "Test timeout")
        self.tick()
        self.tick()
        self.model.complete.assert_called_once()
        with connect(self.settings) as db:
            self.assertEqual(
                db.execute("SELECT status FROM triage_attempts").fetchone()["status"], "unknown"
            )

    def test_data_endpoints_require_authentication(self):
        self.client.post("/api/auth/logout", headers=self.headers)
        for path in ("/api/settings/analyst", "/api/agents/analyst"):
            self.assertEqual(self.client.get(path).status_code, 401)
