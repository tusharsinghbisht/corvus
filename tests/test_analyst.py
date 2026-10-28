import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from corvus.analyst import analyze
from corvus.cli import main
from corvus.providers import ModelReply
from corvus.providers.azure_foundry import FoundryConfig
from corvus.storage import load_json

ROOT = Path(__file__).resolve().parents[1] / "evaluations"


class AnalystTests(unittest.TestCase):
    def setUp(self):
        self.bundle = load_json(ROOT / "fixtures/001.json")
        self.report = load_json(ROOT / "reference-reports/001.json")
        self.model = Mock()
        self.model.complete.return_value = ModelReply(
            json.dumps(self.report), "test-model", {"total_tokens": 30}
        )

    def test_one_provider_neutral_call_without_evaluator_or_connection_data(self):
        self.bundle["connection"] = {"password": "NEVER-SEND-THIS"}
        self.bundle["expected_disposition"] = "DO-NOT-LEAK-TRUTH"
        result = analyze(self.bundle, self.model)
        self.assertEqual(result["status"], "validated")
        self.assertTrue(result["human_review_required"])
        self.model.complete.assert_called_once()
        messages = self.model.complete.call_args.args[0]
        serialized = json.dumps(messages)
        self.assertNotIn("NEVER-SEND-THIS", serialized)
        self.assertNotIn("DO-NOT-LEAK-TRUTH", serialized)
        self.assertEqual([m["role"] for m in messages], ["system", "user"])
        self.assertIn("untrusted DATA", messages[0]["content"])

    def test_invalid_json_and_fabricated_citations_are_saved_as_rejected(self):
        self.model.complete.return_value = ModelReply("not JSON", "test-model", {})
        result = analyze(self.bundle, self.model)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["unparseable_output"], "not JSON")
        self.report["findings"][0]["citations"][0]["id"] = "fabricated"
        self.model.complete.return_value = ModelReply(json.dumps(self.report), "test-model", {})
        result = analyze(self.bundle, self.model)
        self.assertEqual(result["status"], "rejected")
        self.assertIn("unknown_citation", [e["code"] for e in result["validation"]["errors"]])

    def test_evidence_instructions_remain_data_not_system_instructions(self):
        bundle = load_json(ROOT / "fixtures/003.json")
        report = load_json(ROOT / "reference-reports/003.json")
        self.model.complete.return_value = ModelReply(json.dumps(report), "test-model", {})
        result = analyze(bundle, self.model)
        system, user = self.model.complete.call_args.args[0]
        self.assertNotIn("Ignore all prior instructions", system["content"])
        self.assertIn("Ignore all prior instructions", user["content"])
        self.assertEqual(result["report"]["disposition"], "inconclusive")


class ReportingCLITests(unittest.TestCase):
    def invoke(self, argv):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return main(argv)

    @patch("corvus.cli.load_config")
    @patch("corvus.reporting.cli.load_foundry_config")
    def test_offline_commands_need_no_credentials_or_model_calls(self, foundry, wazuh):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "request.json"
            self.assertEqual(
                self.invoke(
                    [
                        "prepare-report",
                        "--bundle",
                        str(ROOT / "fixtures/001.json"),
                        "--out",
                        str(output),
                    ]
                ),
                0,
            )
            self.assertIn("evidence_digest", load_json(output))
            self.assertEqual(
                self.invoke(
                    [
                        "validate-report",
                        "--bundle",
                        str(ROOT / "fixtures/001.json"),
                        "--report",
                        str(ROOT / "reference-reports/001.json"),
                    ]
                ),
                0,
            )
            self.assertEqual(
                self.invoke(
                    [
                        "evaluate",
                        "--suite",
                        str(ROOT / "suite.json"),
                        "--reports",
                        str(ROOT / "reference-reports"),
                    ]
                ),
                0,
            )
            self.assertEqual(
                self.invoke(["report-schema", "--out", str(Path(directory) / "schema.json")]), 0
            )
        foundry.assert_not_called()
        wazuh.assert_not_called()

    @patch("corvus.reporting.cli.AzureFoundryClient")
    @patch("corvus.reporting.cli.load_foundry_config")
    def test_external_consent_and_output_collision_are_checked_before_model_call(
        self, config, client
    ):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "analysis.json"
            argv = ["analyze", "--bundle", str(ROOT / "fixtures/001.json"), "--out", str(output)]
            self.assertEqual(self.invoke(argv), 1)
            output.write_text("existing")
            self.assertEqual(self.invoke(argv + ["--allow-external"]), 1)
            self.assertEqual(output.read_text(), "existing")
        config.assert_not_called()
        client.assert_not_called()

    @patch("corvus.cli.load_config")
    @patch("corvus.reporting.cli.AzureFoundryClient")
    @patch("corvus.reporting.cli.load_foundry_config")
    def test_model_report_is_private_and_failed_validation_has_distinct_exit(
        self, config, client, wazuh
    ):
        config.return_value = FoundryConfig(
            "https://test.openai.azure.com/openai/v1", "test-only-secret"
        )
        report = load_json(ROOT / "reference-reports/001.json")
        with tempfile.TemporaryDirectory() as directory:
            for index, mutate in enumerate((False, True)):
                if mutate:
                    report["summary_finding_ids"] = ["F999"]
                client.return_value.complete.return_value = ModelReply(
                    json.dumps(report), "DeepSeek-V4-Flash", {}
                )
                path = Path(directory) / (str(index) + ".json")
                status = self.invoke(
                    [
                        "analyze",
                        "--bundle",
                        str(ROOT / "fixtures/001.json"),
                        "--out",
                        str(path),
                        "--allow-external",
                    ]
                )
                self.assertEqual(status, 2 if mutate else 0)
                self.assertNotIn("test-only-secret", path.read_text())
                self.assertTrue(load_json(path)["human_review_required"])
        wazuh.assert_not_called()
