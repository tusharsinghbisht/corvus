import copy
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from test_triage import TriageDatabaseCase

from corvus.server.api import ReportReviewInput
from corvus.server.database import connect
from corvus.server.investigations import reviews


class ReviewTests(TriageDatabaseCase):
    def setUp(self):
        super().setUp()
        self.identifier = self.request()
        self.tick()
        self.approve(self.identifier)
        self.tick()
        self.model.reset_mock()
        self.login()
        self.path = self.api_path + f"/{self.identifier}/reviews"

    def body(self, **changes):
        page = self.client.get(self.path).json()
        binding = page["target"]
        return {
            "decision": "accepted",
            "note": "I checked the cited process identity and collection gaps.",
            "evidence_checked": True,
            "analysis_id": binding["analysis_id"],
            "evidence_digest": binding["evidence_digest"],
            "report_digest": binding["report_digest"],
            "expected_sequence": page["current_sequence"],
        } | changes

    def post(self, **changes):
        return self.client.post(self.path, json=self.body(**changes), headers=self.headers)

    def test_review_preserves_model_output_and_records_human_identity_and_exact_binding(self):
        original = copy.deepcopy(self.read(self.identifier))
        response = self.post()
        self.assertEqual(response.status_code, 201, response.text)
        page = response.json()
        self.assertTrue(page["latest_matches_report"])
        self.assertEqual(page["latest"]["reviewer"], self.settings.admin_username)
        self.assertEqual(page["latest"]["analysis_id"], original["result"]["analysis_id"])
        self.assertEqual(page["latest"]["evidence_digest"], original["evidence_digest"])
        self.assertEqual(page["latest"]["generation_validator_version"], "0.2")
        self.assertTrue(page["latest"]["revalidation"]["valid"])
        current = self.read(self.identifier)
        for field in (
            "result",
            "model_reply",
            "evidence",
            "analysis_evidence",
            "input_snapshot",
            "status",
        ):
            self.assertEqual(current[field], original[field])
        self.assertTrue(current["result"]["human_review_required"])
        self.assertFalse(current["result"]["report"]["response_executed"])
        self.model.complete.assert_not_called()
        with connect(self.settings) as db:
            event = db.execute(
                "SELECT user_id FROM audit_events WHERE action='triage.assessment_accepted'"
            ).fetchone()
        self.assertEqual(event["user_id"], self.user_id)

    def test_authentication_origin_and_strict_fields(self):
        body = self.body()
        self.assertEqual(self.client.post(self.path, json=body).status_code, 403)
        self.assertEqual(
            self.client.post(
                self.path, json=body | {"evidence_checked": "true"}, headers=self.headers
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.post(
                self.path, json=body | {"response_executed": True}, headers=self.headers
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.post(
                self.path, json=body | {"decision": "resolve"}, headers=self.headers
            ).status_code,
            422,
        )
        self.client.post("/api/auth/logout", headers=self.headers)
        self.assertEqual(self.client.get(self.path).status_code, 401)
        self.assertEqual(
            self.client.post(self.path, json=body, headers=self.headers).status_code, 401
        )
        self.model.complete.assert_not_called()

    def test_accept_requires_evidence_attestation_and_meaningful_notes(self):
        self.assertEqual(self.post(evidence_checked=False).status_code, 400)
        self.assertEqual(self.post(note=" " * 15).status_code, 422)
        self.assertEqual(self.post(note="short").status_code, 422)
        self.assertEqual(self.post(note="x" * 2001).status_code, 422)
        self.assertEqual(self.post(decision="follow_up", evidence_checked=False).status_code, 201)
        self.model.complete.assert_not_called()

    def test_stale_target_digest_analysis_id_or_sequence_is_refused(self):
        body = self.body()
        for changes in (
            {"report_digest": "0" * 64},
            {"evidence_digest": "0" * 64},
            {"analysis_id": str(uuid4())},
            {"expected_sequence": 1},
        ):
            self.assertEqual(
                self.client.post(self.path, json=body | changes, headers=self.headers).status_code,
                409,
            )
        self.assertEqual(
            self.client.post(self.path, json=body, headers=self.headers).status_code, 201
        )
        self.assertEqual(
            self.client.post(self.path, json=body, headers=self.headers).status_code, 409
        )
        self.assertEqual(self.client.get(self.path).json()["total"], 1)

    def test_concurrent_reviews_require_explicit_refresh_and_do_not_overwrite(self):
        body = ReportReviewInput(**self.body())

        def submit(_):
            try:
                with connect(self.settings) as db:
                    reviews.create(db, self.alert_id, self.identifier, body, self.user_id)
                return 201
            except HTTPException as exc:
                return exc.status_code

        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(submit, range(3)))
        self.assertEqual(results.count(201), 1)
        self.assertEqual(results.count(409), 2)
        self.assertEqual(self.client.get(self.path).json()["total"], 1)

    def test_history_is_append_only_and_paginates_without_losing_prior_decisions(self):
        for index in range(23):
            self.assertEqual(
                self.post(
                    decision="follow_up", note=f"Follow-up rationale for revision {index}"
                ).status_code,
                201,
            )
        first = self.client.get(self.path).json()
        self.assertEqual(first["total"], 23)
        self.assertEqual(len(first["reviews"]), 20)
        second = self.client.get(self.path + "?before=" + str(first["next_before"])).json()
        self.assertEqual(
            [row["sequence"] for row in first["reviews"] + second["reviews"]],
            list(range(23, 0, -1)),
        )
        self.assertIsNone(second["next_before"])
        self.assertEqual(second["latest"]["sequence"], 23)
        self.assertEqual(self.client.delete(self.path, headers=self.headers).status_code, 405)
        self.model.complete.assert_not_called()

    def test_accept_revalidates_with_current_validator_but_rejection_can_record_problems(self):
        invalid = {
            "valid": False,
            "validation_version": "test-next",
            "errors": [{"code": "test_integrity_failure"}],
        }
        with patch("corvus.server.investigations.reviews.validate_report", return_value=invalid):
            self.assertEqual(self.post().status_code, 409)
            response = self.post(decision="rejected", evidence_checked=False)
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.json()["latest"]["revalidation"]["valid"])
        self.assertEqual(
            response.json()["latest"]["revalidation"]["validation_version"], "test-next"
        )

    def test_changed_report_or_evidence_cannot_reuse_acceptance(self):
        self.assertEqual(self.post().status_code, 201)
        with connect(self.settings) as db:
            db.execute(
                "UPDATE triage_attempts SET result=jsonb_set(result,'{report,summary}',to_jsonb('Changed assessment'::text)) WHERE id=%s",
                (self.identifier,),
            )
        page = self.client.get(self.path).json()
        self.assertFalse(page["latest_matches_report"])
        self.assertNotEqual(page["target"]["report_digest"], page["latest"]["report_digest"])
        alert = self.client.get("/api/alerts").json()["alerts"][0]
        self.assertTrue(alert["investigation"]["review_stale"])
        self.assertEqual(alert["investigation"]["review_status"], "pending")
        with connect(self.settings) as db:
            db.execute(
                "UPDATE triage_attempts SET analysis_evidence=jsonb_set(analysis_evidence,'{status}','\"partial\"') WHERE id=%s",
                (self.identifier,),
            )
        self.assertEqual(self.post().status_code, 409)
        self.model.complete.assert_not_called()

    def test_nonfinal_and_rejected_candidates_cannot_be_accepted_as_assessments(self):
        other = self.request()
        path = self.api_path + f"/{other}/reviews"
        self.assertIsNone(self.client.get(path).json()["target"])
        self.assertEqual(
            self.client.post(path, json=self.body(), headers=self.headers).status_code, 409
        )
        self.tick()
        self.approve(other)
        from corvus.providers import ModelReply

        self.model.complete.return_value = ModelReply("invalid report", "test", {})
        self.tick()
        self.assertEqual(
            self.client.post(path, json=self.body(), headers=self.headers).status_code, 409
        )
        self.assertEqual(self.client.get(path).json()["total"], 0)

    def test_review_does_not_carry_to_a_new_attempt_and_queue_and_agent_stats_are_consistent(self):
        self.assertEqual(self.post().status_code, 201)
        agent = self.client.get("/api/agents/analyst?review=accepted").json()
        self.assertEqual(agent["stats"]["pending_review"], 0)
        self.assertEqual(agent["stats"]["accepted_assessments"], 1)
        self.assertEqual(len(agent["attempts"]), 1)
        alert = self.client.get("/api/alerts").json()["alerts"][0]
        self.assertEqual(alert["investigation"]["review_status"], "accepted")
        self.assertEqual(self.post(decision="follow_up").status_code, 201)
        self.assertEqual(
            len(self.client.get("/api/agents/analyst?review=follow_up").json()["attempts"]), 1
        )
        self.assertEqual(
            len(self.client.get("/api/agents/analyst?review=accepted").json()["attempts"]), 0
        )
        other = self.request()
        self.tick()
        self.approve(other)
        self.tick()
        self.assertIsNone(self.read(other)["human_review"]["latest"])
        alert = self.client.get("/api/alerts").json()["alerts"][0]
        self.assertEqual(alert["investigation"]["review_status"], "pending")
        self.assertEqual(alert["investigation"]["report_attempt_id"], str(other))
        self.assertEqual(self.client.get(self.path).json()["latest"]["decision"], "follow_up")

    def test_cross_alert_target_is_not_accessible(self):
        wrong_path = f"/api/alerts/{uuid4()}/investigations/{self.identifier}/reviews"
        self.assertEqual(self.client.get(wrong_path).status_code, 404)
        self.assertEqual(
            self.client.post(wrong_path, json=self.body(), headers=self.headers).status_code, 404
        )
