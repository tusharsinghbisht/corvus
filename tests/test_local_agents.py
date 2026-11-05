import copy
import unittest
from unittest.mock import patch
from uuid import uuid4

from test_triage import TriageDatabaseCase

from corvus.agents.analyst.context import ContextBudgetError, encoded, select_context
from corvus.agents.correlation import correlate
from corvus.agents.intel import inspect
from corvus.reporting.evidence import EvidenceCatalog


class LocalAgentTests(unittest.TestCase):
    def setUp(self):
        from test_analyst_context import ROOT

        from corvus.storage import load_json

        self.bundle = load_json(ROOT / "fixtures/001.json")

    def event(self, number, *, process=None, parent=None, event_id="3", agent="001"):
        event = copy.deepcopy(self.bundle["alert"])
        event["reference"]["id"] = "local-" + str(number)
        event["context"].update(
            process_guid=process, parent_process_guid=parent, event_id=event_id, agent_id=agent
        )
        event["source"] = {}
        return event

    def test_focused_selection_does_not_fill_with_nearby_or_sibling_events(self):
        trigger = self.bundle["alert"]["context"]
        self.bundle["events"] = [
            self.event(i, parent=trigger["parent_process_guid"]) for i in range(40)
        ]
        self.bundle["events"] += [
            self.event(50, process=trigger["process_guid"]),
            self.event(51, process=trigger["parent_process_guid"], event_id="1"),
        ]
        original = copy.deepcopy(self.bundle)
        focused = select_context(self.bundle)
        self.assertEqual(len(focused["events"]), 2)
        self.assertLessEqual(len(encoded(EvidenceCatalog(focused).view)), 16 * 1024)
        self.assertEqual(self.bundle, original)
        broader = select_context(self.bundle, profile="expanded")
        self.assertGreater(len(broader["events"]), len(focused["events"]))
        self.assertLessEqual(len(broader["events"]), 12)
        self.assertLessEqual(len(encoded(EvidenceCatalog(broader).view)), 48 * 1024)
        self.assertEqual(focused["status"], "partial")

    def test_no_guid_or_command_anchor_means_trigger_only_not_arbitrary_context(self):
        self.bundle["alert"]["context"]["process_guid"] = None
        self.bundle["alert"]["context"]["parent_process_guid"] = None
        self.bundle["alert"]["source"] = {}
        self.bundle["events"] = [self.event(i) for i in range(20)]
        focused = select_context(self.bundle)
        self.assertEqual(focused["events"], [])
        self.assertIn("analyst_context_reduced", [gap["code"] for gap in focused["gaps"]])

    def test_correlation_normalizes_guids_but_never_crosses_agent_boundary(self):
        process = self.bundle["alert"]["context"]["process_guid"]
        self.bundle["events"] = [
            self.event(1, process=process.upper()),
            self.event(2, process=process, agent="002"),
        ]
        matches = correlate(self.bundle)["candidates"]
        self.assertEqual([match["document"]["reference"]["id"] for match in matches], ["local-1"])
        self.bundle["alert"]["context"]["process_guid"] = "{00000000-0000-0000-0000-000000000000}"
        self.bundle["alert"]["context"]["parent_process_guid"] = None
        self.assertEqual(correlate(self.bundle)["candidates"], [])

    def test_repeated_activity_and_mirrored_trigger_are_not_sent_as_many_documents(self):
        process = self.bundle["alert"]["context"]["process_guid"]
        system = {
            "channel": "Microsoft-Windows-Sysmon/Operational",
            "eventRecordID": 123,
            "systemTime": "2020-01-01T12:00:00Z",
        }
        self.bundle["alert"]["source"] = {
            "data": {"win": {"system": system, "eventdata": {"image": "example.exe"}}}
        }
        self.bundle["events"] = [self.event(i, process=process) for i in range(30)]
        duplicate = self.event(40, process=process)
        duplicate["source"] = copy.deepcopy(self.bundle["alert"]["source"])
        self.bundle["events"].append(duplicate)
        selected = select_context(self.bundle)
        self.assertEqual(len(selected["events"]), 1)
        self.assertNotIn("local-40", [event["reference"]["id"] for event in selected["events"]])
        self.assertNotIn("message", selected["alert"]["source"]["data"]["win"]["system"])

    def test_query_counts_survive_compaction_and_source_renderings_are_explicit_omissions(self):
        process = self.bundle["alert"]["context"]["process_guid"]
        self.bundle["events"] = [self.event(i, process=process) for i in range(100)]
        self.bundle["queries"][0].update(
            returned=100, event_references=[event["reference"] for event in self.bundle["events"]]
        )
        self.bundle["alert"]["source"] = {
            "full_log": "verbose rendering",
            "data": {
                "win": {
                    "system": {"message": "another rendering"},
                    "eventdata": {"commandLine": "safe observed command"},
                }
            },
        }
        selected = select_context(self.bundle)
        self.assertEqual(selected["queries"][0]["returned"], 100)
        self.assertGreater(selected["queries"][0]["omitted_event_references"], 0)
        self.assertEqual(
            selected["alert"]["source"]["data"]["win"]["eventdata"]["commandLine"],
            "safe observed command",
        )
        self.assertEqual(len(selected["alert"]["source"]["_corvus_omitted_renderings"]), 2)
        self.assertEqual(selected["status"], "partial")

    def test_intel_is_bounded_local_syntax_inspection_with_exact_source_paths(self):
        self.bundle["alert"]["source"] = {
            "data": {
                "win": {
                    "eventdata": {
                        "destinationIp": "8.8.8.8",
                        "sourceIp": "127.0.0.1",
                        "queryName": "EXAMPLE.INVALID.",
                        "hashes": "SHA256=" + "a" * 64,
                        "commandLine": "do not extract arbitrary https://secrets.invalid/token",
                    }
                }
            }
        }
        original = copy.deepcopy(self.bundle)
        result = inspect(self.bundle)
        self.assertEqual(
            {item["kind"] for item in result["observations"]}, {"ip", "domain", "hash"}
        )
        self.assertTrue(any(item["value"] == "example.invalid" for item in result["observations"]))
        self.assertTrue(
            all(
                item["sources"][0]["reference"] == self.bundle["alert"]["reference"]
                for item in result["observations"]
            )
        )
        self.assertTrue(
            all(
                item["sources"][0]["path"].startswith("/data/win/eventdata/")
                for item in result["observations"]
            )
        )
        self.assertNotIn("secrets.invalid", str(result))
        self.assertEqual(self.bundle, original)
        self.bundle["alert"]["source"] = {
            str(i): {"destinationIp": f"10.0.0.{i}"} for i in range(1, 70)
        }
        result = inspect(self.bundle)
        self.assertLessEqual(len(result["observations"]), 32)
        self.assertTrue(result["truncated"])


class ContextChoiceTests(TriageDatabaseCase):
    def setUp(self):
        super().setUp()
        self.login()
        self.identifier = self.request()
        self.tick()
        self.path = self.api_path + f"/{self.identifier}/context"

    def choose(self, profile="expanded", digest=None):
        return self.client.post(
            self.path,
            json={
                "profile": profile,
                "expected_evidence_digest": digest or self.read(self.identifier)["evidence_digest"],
            },
            headers=self.headers,
        )

    def test_local_profile_switch_preserves_originals_and_invalidates_stale_approval(self):
        original = copy.deepcopy(self.read(self.identifier))
        response = self.choose()
        self.assertEqual(response.status_code, 200, response.text)
        current = response.json()
        self.assertEqual(current["evidence"], original["evidence"])
        self.assertNotEqual(current["evidence_digest"], original["evidence_digest"])
        self.assertEqual(
            current["analysis_evidence"]["scope"]["context_selection"]["profile"], "expanded"
        )
        self.assertEqual(current["prepared_input"]["evidence_digest"], current["evidence_digest"])
        self.assertEqual(self.choose("focused", original["evidence_digest"]).status_code, 409)
        approved = self.client.post(
            self.api_path + f"/{self.identifier}/approve",
            json={"allow_external": True, "evidence_digest": original["evidence_digest"]},
            headers=self.headers,
        )
        self.assertEqual(approved.status_code, 409)
        self.approve(self.identifier)
        self.assertEqual(self.choose().status_code, 409)
        self.assertIsNone(self.read(self.identifier)["request_started_at"])
        self.model.complete.assert_not_called()

    def test_context_routes_auth_origin_scope_and_strict_profiles(self):
        body = {
            "profile": "expanded",
            "expected_evidence_digest": self.read(self.identifier)["evidence_digest"],
        }
        self.assertEqual(self.client.post(self.path, json=body).status_code, 403)
        self.assertEqual(
            self.client.post(
                self.path, json=body | {"profile": "unlimited"}, headers=self.headers
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.post(
                self.path, json=body | {"allow_external": True}, headers=self.headers
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.post(
                f"/api/alerts/{uuid4()}/investigations/{self.identifier}/context",
                json=body,
                headers=self.headers,
            ).status_code,
            404,
        )
        self.client.post("/api/auth/logout", headers=self.headers)
        self.assertEqual(
            self.client.post(self.path, json=body, headers=self.headers).status_code, 401
        )
        self.assertEqual(self.client.get("/api/agents/local/intel").status_code, 401)

    def test_local_budget_failure_can_expand_without_recollection_or_model_request(self):
        from corvus.server.database import connect
        from corvus.server.investigations import service

        with connect(self.settings) as db:
            service.cancel(db, self.alert_id, self.identifier, self.user_id)
        self.identifier = self.request()
        self.path = self.api_path + f"/{self.identifier}/context"
        with patch(
            "corvus.server.investigations.worker.select_context",
            side_effect=ContextBudgetError("bounded"),
        ):
            self.tick()
        failed = self.read(self.identifier)
        self.assertEqual(failed["error_code"], "context_budget_exceeded")
        self.assertIsNone(failed["prepared_input"])
        response = self.client.post(
            self.path,
            json={"profile": "expanded", "expected_evidence_digest": None},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "awaiting_approval")
        self.assertEqual(response.json()["evidence"], failed["evidence"])
        self.model.complete.assert_not_called()
