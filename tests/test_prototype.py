import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from psycopg.types.json import Jsonb
from test_ingestion import document
from test_reviews import ReviewedReportCase

from corvus.reporting.evidence import EvidenceCatalog
from corvus.server.database import connect


class PrototypeTests(ReviewedReportCase):
    def test_private_export_preserves_bindings_checksums_reviews_and_no_model_calls(self):
        self.assertEqual(self.post(decision="follow_up").status_code, 201)
        response = self.client.get(self.api_path + f"/{self.identifier}/export")
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment;", response.headers["content-disposition"])
        self.assertEqual(response.headers["cache-control"], "no-store")
        with ZipFile(io.BytesIO(response.content)) as archive:
            self.assertTrue(
                all("/" not in name and ".." not in name for name in archive.namelist())
            )
            manifest = json.loads(archive.read("manifest.json"))
            for name, binding in manifest["files"].items():
                data = archive.read(name)
                self.assertEqual(len(data), binding["bytes"])
                self.assertEqual(hashlib.sha256(data).hexdigest(), binding["sha256"])
            evidence = json.loads(archive.read("selected-evidence.json"))
            result = json.loads(archive.read("analysis.json"))
            self.assertEqual(EvidenceCatalog(evidence).digest, result["evidence_digest"])
            self.assertEqual(json.loads(archive.read("reviews.json"))[0]["decision"], "follow_up")
            self.assertNotIn(
                self.settings.admin_password.encode(),
                b"".join(archive.read(name) for name in archive.namelist()),
            )
            self.assertNotIn(
                b"private-reader-password",
                b"".join(archive.read(name) for name in archive.namelist()),
            )
        self.model.complete.assert_not_called()

    def test_summary_escapes_untrusted_markdown_and_rejected_output_is_not_an_assessment(self):
        original = self.read(self.identifier)["result"]
        original["report"]["summary"] = "<script>unsafe</script> ![image](https://example.invalid)"
        with connect(self.settings) as db:
            db.execute(
                "UPDATE triage_attempts SET result=%s WHERE id=%s",
                (Jsonb(original), self.identifier),
            )
        path = self.api_path + f"/{self.identifier}/export?format=markdown"
        text = self.client.get(path).text
        self.assertIn("&lt;script&gt;", text)
        self.assertNotIn("<script>", text)
        self.assertNotIn("![image](", text)
        with connect(self.settings) as db:
            db.execute(
                "UPDATE triage_attempts SET status='rejected' WHERE id=%s", (self.identifier,)
            )
        text = self.client.get(path).text
        self.assertIn("No accepted model assessment", text)
        self.assertNotIn("<script>", text)
        self.assertNotIn("## Advisory assessment", text)
        self.model.complete.assert_not_called()

    def test_export_authentication_scope_limits_and_no_automatic_processing(self):
        path = self.api_path + f"/{self.identifier}/export"
        with patch("corvus.server.investigations.exporting.MAX_EXPORT_BYTES", 100):
            self.assertEqual(self.client.get(path).status_code, 413)
        self.assertEqual(self.client.get(path + "?format=html").status_code, 422)
        self.client.post("/api/auth/logout", headers=self.headers)
        self.assertEqual(self.client.get(path).status_code, 401)
        self.model.complete.assert_not_called()

    def test_actionable_queue_filters_follow_latest_attempt_and_report_review(self):
        def count(view):
            return self.client.get("/api/alerts?view=" + view).json()["stats"]["total"]

        self.assertEqual(count("needs_review"), 1)
        self.assertEqual(count("uninvestigated"), 0)
        self.assertEqual(count("attention"), 0)
        self.post(decision="follow_up")
        self.assertEqual(count("follow_up"), 1)
        self.assertEqual(count("needs_review"), 0)
        self.post()
        self.assertEqual(count("reviewed"), 1)
        self.assertEqual(count("follow_up"), 0)
        other = self.request()
        self.assertEqual(count("active"), 1)
        self.assertEqual(count("reviewed"), 1)
        with connect(self.settings) as db:
            db.execute(
                "UPDATE triage_attempts SET status='failed',error_code='test_failure' WHERE id=%s",
                (other,),
            )
        self.assertEqual(count("attention"), 1)
        self.assertEqual(count("reviewed"), 1)
        self.assertEqual(self.client.get("/api/alerts?view=invalid").status_code, 422)
        self.model.complete.assert_not_called()

    def test_queue_filter_keyset_pagination_preserves_equal_timestamp_rows(self):
        timestamp = datetime.now(timezone.utc).isoformat()
        with connect(self.settings) as db:
            from corvus.server.ingestion import insert_alert

            for index in range(61):
                insert_alert(
                    db,
                    self.connection_row["id"],
                    document("workflow-" + str(index), timestamp=timestamp),
                )
        first = self.client.get("/api/alerts?view=uninvestigated").json()
        second = self.client.get(
            "/api/alerts?view=uninvestigated&before=" + first["next_cursor"]
        ).json()
        self.assertEqual(first["stats"]["total"], 61)
        self.assertEqual(len(first["alerts"]), 50)
        self.assertEqual(len(second["alerts"]), 11)
        self.assertEqual(len({row["id"] for row in first["alerts"] + second["alerts"]}), 61)

    def test_recovery_disarms_old_queues_without_altering_completed_reports(self):
        self.post()
        other = self.request()
        with connect(self.settings) as db:
            db.execute(
                "INSERT INTO analyst_policies(connection_id,enabled,activated_at,consent_by,consent_at) VALUES(%s,true,now(),%s,now())",
                (self.connection_row["id"], self.user_id),
            )
        with connect(self.settings) as db:
            db.autocommit = True
            db.execute(
                Path(__file__)
                .resolve()
                .parents[1]
                .joinpath("infra/recovery-disarm.sql")
                .read_text()
            )
        with connect(self.settings) as db:
            row = db.execute(
                "SELECT status,error_code,request_started_at FROM triage_attempts WHERE id=%s",
                (other,),
            ).fetchone()
            self.assertEqual(row["status"], "unknown")
            self.assertEqual(row["error_code"], "restored_backup_requires_reapproval")
            self.assertIsNone(row["request_started_at"])
            self.assertEqual(db.execute("SELECT count(*) AS n FROM sessions").fetchone()["n"], 0)
            self.assertFalse(
                db.execute("SELECT enabled FROM analyst_policies").fetchone()["enabled"]
            )
            self.assertEqual(
                db.execute("SELECT count(*) AS n FROM report_reviews").fetchone()["n"], 1
            )
        self.assertEqual(self.read(self.identifier)["status"], "validated")
        self.model.complete.assert_not_called()
