import json
import os
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from corvus.errors import BackendError
from corvus.evidence import collect
from corvus.models import SearchResult
from corvus.storage import save_private

STAMP = "2020-01-01T12:00:00Z"
GUID = "{11111111-1111-1111-1111-111111111111}"
PARENT = "{22222222-2222-2222-2222-222222222222}"


def event(identifier="event", **context):
    return {
        "reference": {"backend": "fake", "index": "test-events", "id": identifier},
        "context": {
            "timestamp": STAMP,
            "agent_id": "001",
            "process_guid": GUID,
            "parent_process_guid": PARENT,
            "event_id": "1",
            **context,
        },
        "source": {"native_message": "Original evidence from a non-Wazuh test backend"},
    }


def result(events, **kwargs):
    return SearchResult(
        events=events, query={"test": True}, total=len(events), total_relation="eq", **kwargs
    )


class FakeBackend:
    def __init__(self, alert=None, results=None):
        self.alert = alert or event("alert")
        self.results = list(results or [])
        self.calls = []

    def get_alert(self, index, alert_id):
        return deepcopy(self.alert)

    def search_events(self, **scope):
        self.calls.append(scope)
        response = self.results.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class EvidenceTests(unittest.TestCase):
    def test_collects_via_backend_contract_and_deduplicates(self):
        child = event("child")
        parent = event("parent", process_guid=PARENT)
        backend = FakeBackend(results=[result([child]), result([child, parent])])
        bundle = collect(backend, index="test-alerts", alert_id="alert")
        self.assertEqual(bundle["status"], "collected")
        self.assertEqual(len(bundle["events"]), 2)
        self.assertEqual(len(bundle["queries"]), 2)
        self.assertEqual(backend.calls[1]["process_guids"], [GUID, PARENT])
        self.assertEqual(backend.calls[0]["agent_id"], "001")
        self.assertFalse(any(gap["code"] == "parent_creation_not_found" for gap in bundle["gaps"]))
        self.assertNotIn("disposition", bundle)

    def test_query_failure_does_not_erase_other_evidence(self):
        backend = FakeBackend(
            results=[BackendError("permission_denied", "Denied", 403), result([event()])]
        )
        bundle = collect(backend, index="test-alerts", alert_id="alert")
        self.assertEqual(bundle["status"], "partial")
        self.assertEqual(len(bundle["events"]), 1)
        self.assertEqual(bundle["queries"][0]["status"], "error")

    def test_truncation_is_visible(self):
        backend = FakeBackend(results=[result([event()], truncated=True)])
        bundle = collect(backend, index="test-alerts", alert_id="alert", ancestry_hours=0)
        self.assertEqual(bundle["status"], "partial")

    def test_missing_guid_is_not_an_unbounded_query(self):
        backend = FakeBackend(
            alert=event(process_guid=None, parent_process_guid=None), results=[result([])]
        )
        bundle = collect(backend, index="test-alerts", alert_id="alert")
        self.assertEqual(len(backend.calls), 1)
        self.assertEqual(bundle["gaps"][0]["code"], "ancestry_not_queried")

    def test_missing_agent_and_timezone_are_rejected(self):
        for context in [{"agent_id": None}, {"timestamp": "2026-10-28T12:00:00"}]:
            backend = FakeBackend(alert=event(**context))
            with self.assertRaises(ValueError):
                collect(backend, index="test-alerts", alert_id="alert")
            self.assertFalse(backend.calls)

    def test_open_context_window_is_partial(self):
        stamp = datetime.now(timezone.utc).isoformat()
        backend = FakeBackend(alert=event(timestamp=stamp), results=[result([])])
        bundle = collect(backend, index="test-alerts", alert_id="alert", ancestry_hours=0)
        self.assertEqual(bundle["status"], "partial")
        self.assertIn("context_window_not_elapsed", [gap["code"] for gap in bundle["gaps"]])

    def test_invalid_source_guid_cannot_expand_the_search(self):
        backend = FakeBackend(alert=event(process_guid=["invalid"]), results=[result([])])
        bundle = collect(backend, index="test-alerts", alert_id="alert")
        self.assertEqual(len(backend.calls), 1)
        self.assertEqual(bundle["status"], "partial")
        self.assertIn("invalid_process_guid", [gap["code"] for gap in bundle["gaps"]])

    def test_private_output_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bundle.json"
            save_private(path, {"test": True})
            self.assertEqual(json.loads(path.read_text()), {"test": True})
            if os.name == "posix":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                save_private(path, {"test": False})
            self.assertEqual(json.loads(path.read_text()), {"test": True})
