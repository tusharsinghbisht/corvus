import json
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch

from corvus.agents.analyst import analyze, prepare_report
from corvus.agents.analyst.context import (
    MAX_BYTES,
    MAX_EVENTS,
    TIMESTAMP_PATTERN,
    canonicalize_indexed_time,
    encoded,
    select_context,
)
from corvus.providers import ModelError, ModelReply
from corvus.reporting.evidence import EvidenceCatalog
from corvus.storage import load_json

ROOT = Path(__file__).resolve().parents[1] / "evaluations"


class AnalystContextTests(unittest.TestCase):
    def setUp(self):
        self.bundle = load_json(ROOT / "fixtures/001.json")

    def test_selection_is_deterministic_and_does_not_mutate_originals(self):
        original = deepcopy(self.bundle)
        first = select_context(self.bundle)
        self.assertEqual(first, select_context(self.bundle))
        self.assertEqual(self.bundle, original)
        self.assertEqual(first["alert"]["reference"], original["alert"]["reference"])
        self.assertEqual(
            first["scope"]["context_selection"]["original_evidence_digest"],
            EvidenceCatalog(original).digest,
        )
        self.assertLessEqual(len(encoded(EvidenceCatalog(first).view)), MAX_BYTES)

    def test_event_and_byte_budgets_prioritize_exact_process_guid(self):
        event = deepcopy(self.bundle["alert"])
        self.bundle["events"] = []
        self.bundle["alert"]["context"]["process_guid"] = "{00000000-0000-0000-0000-000000000001}"
        for i in range(80):
            item = deepcopy(event)
            item["reference"]["id"] = f"context-{i}"
            item["source"]["large_message"] = "x" * 10000
            item["context"]["process_guid"] = (
                self.bundle["alert"]["context"]["process_guid"] if i == 79 else None
            )
            self.bundle["events"].append(item)
        selected = select_context(self.bundle)
        self.assertLessEqual(len(selected["events"]), MAX_EVENTS)
        self.assertLessEqual(len(encoded(EvidenceCatalog(selected).view)), MAX_BYTES)
        self.assertIn("context-79", [item["reference"]["id"] for item in selected["events"]])
        self.assertEqual(selected["status"], "partial")
        self.assertIn("analyst_context_reduced", [gap["code"] for gap in selected["gaps"]])
        self.assertGreater(selected["scope"]["context_selection"]["omitted_events"], 0)
        excerpt = next(
            item for item in selected["events"] if item["reference"]["id"] == "context-79"
        )["source"]["large_message"]
        self.assertIn("omitted_characters", excerpt)

    def test_missing_and_invalid_guids_do_not_broaden_or_break_selection(self):
        self.bundle["alert"]["context"]["process_guid"] = ["not-a-guid"]
        self.assertLessEqual(
            len(encoded(EvidenceCatalog(select_context(self.bundle)).view)), MAX_BYTES
        )

    def test_indexed_timestamp_formatting_preserves_instant_precision_and_original_source(self):
        from corvus.timeutil import utc
        for value in ('2026-11-03T12:34:56.123+0000', '2026-11-03T12:34:56.123456789+0530', '2026-11-03 12:34:56.123-0700', '2026-11-03T12:34:56Z'):
            with self.subTest(value=value):
                document = deepcopy(self.bundle['alert'])
                document['context']['timestamp'] = value
                document['source']['timestamp'] = value
                source = deepcopy(document['source'])
                canonicalize_indexed_time(document)
                self.assertTrue(TIMESTAMP_PATTERN.fullmatch(document['context']['timestamp']))
                self.assertEqual(utc(document['context']['timestamp']), utc(value))
                self.assertEqual(document['source'], source)
                if '123456789' in value:
                    self.assertIn('123456789', document['context']['timestamp'])
        document['context']['timestamp'] = 'not-a-time'
        self.assertFalse(canonicalize_indexed_time(document))
        self.assertEqual(document['context']['timestamp'], 'not-a-time')

    def test_graph_uses_saved_approved_input_instead_of_regenerating_prompt(self):
        prepared = prepare_report(self.bundle)
        prepared["instructions"] = "Saved read-only instructions"
        prepared["prompt_version"] = "saved-version"
        report = load_json(ROOT / "reference-reports/001.json")
        model = Mock()
        model.complete.return_value = ModelReply(json.dumps(report), "test", {})
        with patch(
            "corvus.agents.analyst.workflow.prepare_report",
            side_effect=AssertionError("Must not regenerate"),
        ):
            result = analyze(self.bundle, model, input_snapshot=prepared)
        self.assertEqual(result["prompt_version"], "saved-version")
        self.assertEqual(
            model.complete.call_args.args[0][0]["content"], "Saved read-only instructions"
        )
        model.complete.assert_called_once()

    def test_langgraph_does_not_retry_or_enable_external_tracing(self):
        model = Mock()
        model.complete.side_effect = ModelError("model_connection_failed", "Test failure")
        with patch("corvus.agents.analyst.workflow.tracing_context") as tracing:
            with self.assertRaises(ModelError):
                analyze(self.bundle, model)
        tracing.assert_called_once_with(enabled=False)
        model.complete.assert_called_once()
        self.assertNotIn("expected_disposition", json.dumps(model.complete.call_args.args))
