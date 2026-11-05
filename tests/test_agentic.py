import copy
import json
from unittest import TestCase
from unittest.mock import Mock

from fastapi import HTTPException
from test_analyst_context import ROOT
from test_triage import TriageDatabaseCase

from corvus.agents.analyst import analyze, prepare_report
from corvus.agents.analyst.context import select_context
from corvus.providers import ModelError, ModelReply
from corvus.reporting.evidence import EvidenceCatalog
from corvus.server.database import connect
from corvus.server.investigations import service, steps
from corvus.storage import load_json


def reply(action):
    return ModelReply(
        json.dumps({"next": action, "question": "Check the selected facts."}), "offline-planner", {}
    )


class AgenticGraphTests(TestCase):
    def setUp(self):
        self.bundle = select_context(load_json(ROOT / "fixtures/001.json"), workflow="agentic")
        self.prepared = prepare_report(self.bundle, workflow="agentic")
        report = load_json(ROOT / "reference-reports/001.json")
        report["evidence_digest"] = EvidenceCatalog(self.bundle).digest
        self.final = ModelReply(json.dumps(report), "offline-assessment", {})

    def test_real_bounded_plan_observe_assess_graph_uses_three_calls_and_no_new_data(self):
        original = copy.deepcopy(self.bundle)
        model = Mock()
        model.complete.side_effect = [reply("correlation"), reply("intel"), self.final]
        result = analyze(self.bundle, model, input_snapshot=self.prepared)
        self.assertEqual(result["status"], "validated", str(result["validation"]))
        self.assertEqual(result["orchestration"]["tools"], ["correlation", "intel"])
        self.assertEqual(result["orchestration"]["model_requests"], 3)
        self.assertEqual(model.complete.call_count, 3)
        self.assertEqual(model.complete.call_args_list[0].kwargs, {"max_tokens": 1024})
        self.assertEqual(model.complete.call_args_list[1].kwargs, {"max_tokens": 1024})
        payload = json.loads(model.complete.call_args_list[2].args[0][-1]["content"])
        self.assertEqual(payload["evidence"], self.prepared["evidence"])
        self.assertEqual(len(payload["local_observations"]), 2)
        self.assertEqual(self.bundle, original)

    def test_simple_case_can_skip_tools_but_never_skip_final_integrity_checks(self):
        model = Mock()
        model.complete.side_effect = [reply("assess"), ModelReply("bad report", "offline", {})]
        result = analyze(self.bundle, model, input_snapshot=self.prepared)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["orchestration"]["tools"], [])
        self.assertEqual(model.complete.call_count, 2)

    def test_forbidden_or_repeated_capabilities_fail_without_repair_retry_or_final_call(self):
        for outputs in (
            [reply("containment")],
            [reply("correlation"), reply("correlation")],
            [ModelReply("{", "offline", {})],
        ):
            model = Mock()
            model.complete.side_effect = outputs
            with self.assertRaises(ModelError) as caught:
                analyze(self.bundle, model, input_snapshot=self.prepared)
            self.assertEqual(caught.exception.code, "invalid_investigation_plan")
            self.assertEqual(model.complete.call_count, len(outputs))

    def test_mutated_approved_contract_cannot_silently_fall_back_or_send_evidence(self):
        prepared = copy.deepcopy(self.prepared)
        prepared["workflow"]["max_model_requests"] = 4
        model = Mock()
        with self.assertRaises(ValueError):
            analyze(self.bundle, model, input_snapshot=prepared)
        model.complete.assert_not_called()


class AgenticDurabilityTests(TriageDatabaseCase):
    def setUp(self):
        super().setUp()
        self.login()
        with connect(self.settings) as db:
            self.identifier = service.request_collection(
                db, self.alert_id, self.user_id, workflow="agentic"
            )
        self.tick()
        self.collector.reset_mock()
        self.model.reset_mock()

    def allow(self):
        with connect(self.settings) as db:
            service.approve(
                db,
                self.alert_id,
                self.identifier,
                self.read(self.identifier)["evidence_digest"],
                self.user_id,
                model_request_limit=3,
            )

    def test_one_call_consent_cannot_authorize_guided_run_and_switching_invalidates_digest(self):
        with connect(self.settings) as db:
            with self.assertRaises(HTTPException):
                service.approve(
                    db,
                    self.alert_id,
                    self.identifier,
                    self.read(self.identifier)["evidence_digest"],
                    self.user_id,
                )
        self.model.complete.assert_not_called()
        old = self.read(self.identifier)
        response = self.client.post(
            self.api_path + f"/{self.identifier}/context",
            json={
                "profile": "focused",
                "workflow": "direct",
                "expected_evidence_digest": old["evidence_digest"],
            },
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotEqual(response.json()["evidence_digest"], old["evidence_digest"])
        self.assertEqual(response.json()["workflow"], "direct")

    def test_each_request_is_durable_before_possible_billing_and_tool_tasks_are_real(self):
        self.allow()
        bundle = self.read(self.identifier)["analysis_evidence"]
        report = copy.deepcopy(self.report)
        report["evidence_digest"] = EvidenceCatalog(bundle).digest
        outputs = iter(
            [reply("correlation"), reply("intel"), ModelReply(json.dumps(report), "offline", {})]
        )

        def complete(*args, **kwargs):
            with connect(self.settings) as db:
                last = db.execute(
                    "SELECT * FROM investigation_steps WHERE attempt_id=%s ORDER BY position DESC LIMIT 1",
                    (self.identifier,),
                ).fetchone()
                self.assertEqual(last["state"], "running")
                self.assertTrue(last["model_request"])
                self.assertEqual(last["input_snapshot"]["messages"], args[0])
            return next(outputs)

        self.model.complete.side_effect = complete
        self.tick()
        current = self.read(self.identifier)
        self.assertEqual(current["status"], "validated", str(current["result"]))
        self.assertEqual(
            [step["phase"] for step in current["steps"]],
            ["plan", "correlation", "plan", "intel", "assessment"],
        )
        self.assertTrue(all(step["state"] == "completed" for step in current["steps"]))
        self.assertEqual(len(self.client.get("/api/agents/local/correlation").json()["tasks"]), 1)
        self.assertEqual(self.model.complete.call_count, 3)
        self.collector.assert_not_called()
        self.tick()
        self.assertEqual(self.model.complete.call_count, 3)

    def test_ambiguous_second_request_preserves_first_observation_and_is_never_replayed(self):
        self.allow()
        self.model.complete.side_effect = [
            reply("correlation"),
            ModelError("model_connection_failed", "offline failure"),
        ]
        self.tick()
        current = self.read(self.identifier)
        self.assertEqual(current["status"], "unknown")
        self.assertEqual(
            [step["state"] for step in current["steps"]], ["completed", "completed", "unknown"]
        )
        self.assertIsNone(current["result"])
        self.assertIsNone(current["model_reply"])
        self.tick()
        self.assertEqual(self.model.complete.call_count, 2)

    def test_invalid_plan_is_saved_as_failure_not_a_finding(self):
        self.allow()
        self.model.complete.return_value = reply("shell")
        self.tick()
        current = self.read(self.identifier)
        self.assertEqual(current["status"], "failed")
        self.assertEqual(current["error_code"], "invalid_investigation_plan")
        self.assertEqual(current["steps"][0]["state"], "failed")
        self.assertIn("shell", current["steps"][0]["output"]["content"])
        self.assertIsNone(current["result"])

    def test_recovery_disarms_started_steps_instead_of_resuming_a_graph(self):
        self.allow()
        with connect(self.settings) as db:
            db.execute(
                "UPDATE triage_attempts SET status='requesting',request_started_at=now() WHERE id=%s",
                (self.identifier,),
            )
        record = steps.recorder(self.settings, self.identifier)
        record("start", "plan", {"messages": []})
        with connect(self.settings) as db:
            service_row = db.execute(
                "SELECT status FROM triage_attempts WHERE id=%s", (self.identifier,)
            ).fetchone()
        self.assertEqual(service_row["status"], "requesting")
        self.tick()
        current = self.read(self.identifier)
        self.assertEqual(current["status"], "unknown")
        self.assertEqual(current["steps"][0]["state"], "unknown")
        self.model.complete.assert_not_called()
