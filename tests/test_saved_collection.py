import copy
import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from psycopg.types.json import Jsonb
from test_reviews import ReviewedReportCase

from corvus.agents.analyst.context import ContextBudgetError, encoded
from corvus.providers import ModelReply
from corvus.reporting.evidence import EvidenceCatalog
from corvus.server.api import SavedCollectionInput
from corvus.server.database import connect
from corvus.server.investigations import service


class SavedCollectionTests(ReviewedReportCase):
    def setUp(self):
        super().setUp()
        self.path_reuse = self.api_path + f"/{self.identifier}/reuse"
        self.collector.reset_mock()
        self.factory.reset_mock()

    def reuse_body(self, **changes):
        binding = self.read(self.identifier)["saved_collection"]
        return {
            "source_evidence_digest": binding["evidence_digest"],
            "acknowledge_historical": True,
            "profile": "focused",
        } | changes

    def reuse(self, **changes):
        return self.client.post(
            self.path_reuse, json=self.reuse_body(**changes), headers=self.headers
        )

    def test_prepare_is_local_preserves_originals_and_never_inherits_consent_reviews_or_reply(self):
        self.post()
        original = copy.deepcopy(self.read(self.identifier))
        response = self.reuse()
        self.assertEqual(response.status_code, 201, response.text)
        current = self.read(response.json()["id"])
        self.assertEqual(current["status"], "awaiting_approval")
        self.assertEqual(current["mode"], "manual")
        self.assertEqual(current["number"], original["number"] + 1)
        self.assertEqual(current["requested_by"], self.user_id)
        self.assertEqual(current["evidence"], original["evidence"])
        self.assertEqual(
            current["evidence"]["collection_id"], original["evidence"]["collection_id"]
        )
        self.assertEqual(self.read(self.identifier), original)
        for field in (
            "result",
            "model_reply",
            "approved_digest",
            "approved_at",
            "approved_by",
            "request_started_at",
            "collection_started_at",
            "policy_version",
        ):
            self.assertIsNone(current[field], field)
        self.assertIsNone(current["human_review"])
        reuse = current["provenance"]["saved_collection"]
        self.assertEqual(reuse["source_attempt_id"], str(self.identifier))
        self.assertEqual(
            reuse["original_collected_at"], original["saved_collection"]["collected_at"]
        )
        self.assertEqual(current["analysis_evidence"]["scope"]["saved_collection_reuse"], reuse)
        self.assertEqual(current["analysis_evidence"]["status"], "partial")
        self.assertIn(
            "saved_collection_reused", [gap["code"] for gap in current["analysis_evidence"]["gaps"]]
        )
        self.assertLessEqual(
            len(encoded(EvidenceCatalog(current["analysis_evidence"]).view)), 16 * 1024
        )
        self.assertEqual(
            current["analysis_evidence"]["scope"]["context_selection"]["original_evidence_digest"],
            original["saved_collection"]["evidence_digest"],
        )
        self.assertEqual(current["prepared_input"]["evidence_digest"], current["evidence_digest"])
        self.tick()
        self.factory.assert_not_called()
        self.model.complete.assert_not_called()
        self.collector.assert_not_called()

    def test_reprofile_keeps_historical_warning_and_fresh_approval_alone_authorizes_one_request(
        self,
    ):
        identifier = self.reuse().json()["id"]
        old = self.read(identifier)
        switched = self.client.post(
            self.api_path + f"/{identifier}/context",
            json={"profile": "expanded", "expected_evidence_digest": old["evidence_digest"]},
            headers=self.headers,
        )
        self.assertEqual(switched.status_code, 200, switched.text)
        current = self.read(identifier)
        self.assertEqual(
            current["analysis_evidence"]["scope"]["saved_collection_reuse"],
            old["analysis_evidence"]["scope"]["saved_collection_reuse"],
        )
        self.assertIn(
            "saved_collection_reused", [gap["code"] for gap in current["analysis_evidence"]["gaps"]]
        )
        stale = self.client.post(
            self.api_path + f"/{identifier}/approve",
            json={"allow_external": True, "evidence_digest": old["evidence_digest"]},
            headers=self.headers,
        )
        self.assertEqual(stale.status_code, 409)
        report = copy.deepcopy(self.report)
        report.update(
            evidence_digest=current["evidence_digest"],
            disposition="inconclusive",
            summary="The preserved observations do not establish current endpoint state.",
        )
        report["findings"][1]["statement"] = (
            "Historical process observations are insufficient to establish the present endpoint state."
        )
        report["uncertainties"] = [
            {
                "code": gap["code"],
                "description": gap["message"],
                "next_step": "Obtain separately authorized current evidence if needed.",
            }
            for gap in current["analysis_evidence"]["gaps"]
        ]
        self.model.complete.return_value = ModelReply(json.dumps(report), "offline-reuse-test", {})
        self.approve(identifier)
        self.tick()
        result = self.read(identifier)
        self.assertEqual(result["status"], "validated", str(result["result"]))
        self.assertEqual(
            result["provenance"]["saved_collection"], old["provenance"]["saved_collection"]
        )
        self.assertEqual(result["provenance"]["collection_scope"], old["evidence"]["scope"])
        self.model.complete.assert_called_once()
        self.collector.assert_not_called()
        self.tick()
        self.model.complete.assert_called_once()

    def test_concurrent_reuse_and_fresh_collection_share_single_active_attempt_guard(self):
        body = SavedCollectionInput(**self.reuse_body())

        def create(kind):
            try:
                with connect(self.settings) as db:
                    return str(
                        service.reuse_collection(
                            db, self.alert_id, self.identifier, body, self.user_id
                        )
                        if kind == "reuse"
                        else service.request_collection(db, self.alert_id, self.user_id)
                    )
            except HTTPException as exc:
                return exc.status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            values = list(pool.map(create, ["reuse", "fresh"]))
        self.assertEqual(values.count(409), 1)
        with connect(self.settings) as db:
            self.assertEqual(
                db.execute(
                    "SELECT count(*) AS n FROM triage_attempts WHERE status=ANY(%s)",
                    (list(service.ACTIVE),),
                ).fetchone()["n"],
                1,
            )
        self.model.complete.assert_not_called()
        self.collector.assert_not_called()

    def test_strict_acknowledgement_origin_authentication_scope_and_source_binding(self):
        body = self.reuse_body()
        self.assertEqual(self.client.post(self.path_reuse, json=body).status_code, 403)
        self.assertEqual(self.reuse(acknowledge_historical=False).status_code, 400)
        self.assertEqual(self.reuse(acknowledge_historical="true").status_code, 422)
        self.assertEqual(self.reuse(allow_external=True).status_code, 422)
        self.assertEqual(self.reuse(profile="unbounded").status_code, 422)
        self.assertEqual(self.reuse(source_evidence_digest="0" * 64).status_code, 409)
        self.assertEqual(
            self.client.post(
                f"/api/alerts/{uuid4()}/investigations/{self.identifier}/reuse",
                json=body,
                headers=self.headers,
            ).status_code,
            404,
        )
        self.client.post("/api/auth/logout", headers=self.headers)
        self.assertEqual(
            self.client.post(self.path_reuse, json=body, headers=self.headers).status_code, 401
        )
        self.model.complete.assert_not_called()
        self.collector.assert_not_called()

    def test_missing_invalid_source_and_over_budget_input_do_not_create_attempts(self):
        body = self.reuse_body()
        with patch(
            "corvus.server.investigations.service.select_context",
            side_effect=ContextBudgetError("test"),
        ):
            self.assertEqual(
                self.client.post(self.path_reuse, json=body, headers=self.headers).status_code, 413
            )
        with connect(self.settings) as db:
            self.assertEqual(
                db.execute("SELECT count(*) AS n FROM triage_attempts").fetchone()["n"], 1
            )
            db.execute(
                "UPDATE triage_attempts SET evidence=%s WHERE id=%s",
                (Jsonb({"schema_version": "invalid"}), self.identifier),
            )
        self.assertIsNone(self.read(self.identifier)["saved_collection"])
        self.assertEqual(
            self.client.post(self.path_reuse, json=body, headers=self.headers).status_code, 409
        )
        self.model.complete.assert_not_called()

    def test_unknown_or_restored_attempt_can_only_prepare_an_explicit_new_manual_attempt(self):
        with connect(self.settings) as db:
            db.execute(
                "UPDATE triage_attempts SET status='unknown',error_code='restored_backup_requires_reapproval',request_started_at=NULL WHERE id=%s",
                (self.identifier,),
            )
        response = self.reuse()
        self.assertEqual(response.status_code, 201, response.text)
        current = self.read(response.json()["id"])
        self.assertEqual(current["status"], "awaiting_approval")
        self.assertEqual(self.read(self.identifier)["status"], "unknown")
        self.model.complete.assert_not_called()
        self.collector.assert_not_called()

    def test_automatic_source_never_carries_policy_authorization_into_reuse(self):
        with connect(self.settings) as db:
            db.execute(
                "UPDATE triage_attempts SET mode='automatic',policy_version=99 WHERE id=%s",
                (self.identifier,),
            )
        response = self.reuse()
        self.assertEqual(response.status_code, 201, response.text)
        current = self.read(response.json()["id"])
        self.assertEqual(current["mode"], "manual")
        self.assertIsNone(current["policy_version"])
        self.assertIsNone(current["approved_at"])
        self.tick()
        self.factory.assert_not_called()
        self.model.complete.assert_not_called()

    def test_unknown_collection_age_is_not_replaced_with_preparation_time(self):
        original = copy.deepcopy(self.read(self.identifier)["evidence"])
        original.pop("completed_at", None)
        original["scope"].pop("as_of", None)
        with connect(self.settings) as db:
            db.execute(
                "UPDATE triage_attempts SET evidence=%s WHERE id=%s",
                (Jsonb(original), self.identifier),
            )
        self.assertIsNone(self.read(self.identifier)["saved_collection"]["collected_at"])
        response = self.reuse()
        self.assertEqual(response.status_code, 201, response.text)
        current = self.read(response.json()["id"])
        self.assertIsNone(current["provenance"]["saved_collection"]["original_collected_at"])
        self.assertIsNone(
            current["analysis_evidence"]["scope"]["saved_collection_reuse"]["original_collected_at"]
        )
        self.assertIsNone(current["collection_started_at"])
        self.assertEqual(current["evidence"], original)
        self.model.complete.assert_not_called()

    def test_export_marks_historical_origin_without_promoting_the_source_review_or_report(self):
        self.post()
        identifier = self.reuse().json()["id"]
        text = self.client.get(self.api_path + f"/{identifier}/export?format=markdown").text
        self.assertIn("## Historical saved collection", text)
        self.assertIn("No new backend query", text)
        self.assertIn(str(self.identifier), text)
        self.assertIn("No accepted model assessment", text)
        self.assertIn("No human review decision recorded", text)
        self.model.complete.assert_not_called()
