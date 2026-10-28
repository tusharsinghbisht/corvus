import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

from corvus.analyst import prepare_report
from corvus.evaluation import evaluate_report, evaluate_suite
from corvus.reporting.evidence import EvidenceCatalog
from corvus.reporting.schema import REPORT_SCHEMA
from corvus.reporting.validation import validate_report
from corvus.storage import load_json, parse_json

ROOT = Path(__file__).resolve().parents[1] / "evaluations"


def fixture(directory, case="001"):
    return load_json(ROOT / directory / (case + ".json"))


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.bundle = fixture("fixtures")
        self.report = fixture("reference-reports")

    def test_schema_and_reference_reports_are_valid(self):
        Draft202012Validator.check_schema(REPORT_SCHEMA)
        for case in ("001", "002", "003"):
            with self.subTest(case=case):
                result = validate_report(
                    fixture("reference-reports", case), fixture("fixtures", case)
                )
                self.assertTrue(result["valid"], result)
                self.assertTrue(result["warnings"])

    def test_rejects_schema_violations_without_echoing_content(self):
        mutations = [
            lambda r: r.update(extra="PRIVATE-SENTINEL"),
            lambda r: r.update(response_executed=True),
            lambda r: r.update(disposition="PRIVATE-SENTINEL"),
            lambda r: r.update(summary="  "),
            lambda r: r["findings"][0].update(citations=[]),
            lambda r: r["timeline"][0].update(timestamp="not-a-timestamp"),
            lambda r: r["timeline"][0].update(timestamp="20200101T120000Z"),
            lambda r: r["timeline"][0].update(timestamp="2020-01-01 12:00:00Z"),
        ]
        for mutate in mutations:
            report = deepcopy(self.report)
            mutate(report)
            result = validate_report(report, self.bundle)
            self.assertFalse(result["valid"])
            self.assertNotIn("PRIVATE-SENTINEL", json.dumps(result))

    def test_rejects_wrong_binding_citations_and_finding_links(self):
        mutations = [
            (lambda r: r.update(collection_id="other"), "wrong_collection"),
            (lambda r: r.update(evidence_digest="0" * 64), "wrong_evidence_digest"),
            (
                lambda r: r["findings"][0]["citations"][0].update(backend="other"),
                "unknown_citation",
            ),
            (lambda r: r.update(summary_finding_ids=["F999"]), "unknown_finding_id"),
            (lambda r: r.update(summary_finding_ids=["F1"]), "missing_summary_rationale"),
            (lambda r: r["recommendations"][0].update(finding_ids=["F999"]), "unknown_finding_id"),
            (lambda r: r["findings"][1].update(id="F1"), "duplicate_finding_id"),
            (
                lambda r: r["findings"][1].update(kind="observation"),
                "missing_disposition_reasoning",
            ),
        ]
        for mutate, code in mutations:
            with self.subTest(code=code):
                report = deepcopy(self.report)
                mutate(report)
                result = validate_report(report, self.bundle)
                self.assertIn(code, [item["code"] for item in result["errors"]])

    def test_timeline_must_match_cited_indexed_time(self):
        self.report["timeline"][0]["timestamp"] = "2020-01-01T12:00:01Z"
        result = validate_report(self.report, self.bundle)
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"][0]["code"], "unsupported_timeline_timestamp")
        self.report["timeline"][0]["timestamp"] = "2020-01-01T13:00:00+01:00"
        self.assertTrue(validate_report(self.report, self.bundle)["valid"])

    def test_collection_metadata_citations_are_bound_and_allowlisted(self):
        self.report["findings"][0]["citations"] = [
            {"collection_id": self.bundle["collection_id"], "path": "/queries/0"}
        ]
        self.assertTrue(validate_report(self.report, self.bundle)["valid"])
        for path in ("/queries/100", "/scope/0"):
            self.report["findings"][0]["citations"][0]["path"] = path
            result = validate_report(self.report, self.bundle)
            self.assertIn("unknown_citation", [error["code"] for error in result["errors"]])
        self.report["findings"][0]["citations"][0]["path"] = "/connection"
        self.assertFalse(validate_report(self.report, self.bundle)["valid"])
        self.report["findings"][0]["citations"][0].update(path="/status", collection_id="other")
        self.assertFalse(validate_report(self.report, self.bundle)["valid"])

    def test_missing_evidence_cannot_be_silently_cleared(self):
        bundle = fixture("fixtures", "003")
        report = fixture("reference-reports", "003")
        report["disposition"] = "likely_benign"
        report["findings"][0]["kind"] = "inference"
        result = validate_report(report, bundle)
        self.assertIn("incomplete_benign_clearance", [e["code"] for e in result["errors"]])
        report["disposition"] = "inconclusive"
        report["uncertainties"] = []
        codes = [e["code"] for e in validate_report(report, bundle)["errors"]]
        self.assertIn("unacknowledged_gaps", codes)
        self.assertIn("missing_uncertainty", codes)

    def test_disruptive_recommendations_require_a_malicious_disposition(self):
        for case in ("001", "003"):
            bundle = fixture("fixtures", case)
            for category in ("review_containment", "review_remediation"):
                report = fixture("reference-reports", case)
                report["recommendations"][0]["category"] = category
                result = validate_report(report, bundle)
                self.assertIn(
                    "unsupported_disruptive_recommendation", [e["code"] for e in result["errors"]]
                )

    def test_partial_evidence_can_still_support_malicious_activity(self):
        bundle = fixture("fixtures", "002")
        report = fixture("reference-reports", "002")
        bundle["status"] = "partial"
        bundle["gaps"] = [{"code": "missing_dns", "message": "DNS logs unavailable"}]
        report["uncertainties"] = [
            {"code": "missing_dns", "description": "No DNS logs", "next_step": "Collect DNS logs"}
        ]
        report["evidence_digest"] = EvidenceCatalog(bundle).digest
        self.assertTrue(validate_report(report, bundle)["valid"])

    def test_partial_query_is_respected_even_if_bundle_status_is_wrong(self):
        self.bundle["queries"][0]["truncated"] = True
        self.report["evidence_digest"] = EvidenceCatalog(self.bundle).digest
        self.assertFalse(validate_report(self.report, self.bundle)["valid"])

    def test_catalog_rejects_conflicting_and_malformed_evidence(self):
        for change in ("conflict", "missing_source", "bad_reference", "bad_gaps"):
            bundle = deepcopy(self.bundle)
            if change == "conflict":
                event = deepcopy(bundle["events"][0])
                event["source"]["different"] = True
                bundle["events"].append(event)
            elif change == "missing_source":
                del bundle["alert"]["source"]
            elif change == "bad_reference":
                bundle["alert"]["reference"]["extra"] = "ignored?"
            else:
                bundle["gaps"] = [{"description": "no code"}]
            with self.subTest(change=change), self.assertRaises(ValueError):
                EvidenceCatalog(bundle)

    def test_preparation_excludes_secrets_and_evaluator_metadata(self):
        self.bundle.update(
            connection={"password": "SECRET-SENTINEL"},
            backend_requests=[{"private": "SECRET-SENTINEL"}],
            expected_disposition="TRUTH-SENTINEL",
            fixture_path="TRUTH-SENTINEL",
        )
        before = deepcopy(self.bundle)
        request = prepare_report(self.bundle)
        self.assertNotIn("SECRET-SENTINEL", json.dumps(request))
        self.assertNotIn("TRUTH-SENTINEL", json.dumps(request))
        self.assertEqual(before, self.bundle)
        self.assertEqual(request["evidence_digest"], self.report["evidence_digest"])
        request["evidence"]["events"][0]["source"]["changed"] = True
        request["report_schema"]["additionalProperties"] = True
        self.assertEqual(before, self.bundle)
        self.assertFalse(REPORT_SCHEMA["additionalProperties"])

    def test_digest_changes_when_evidence_changes(self):
        self.bundle["alert"]["source"]["new_observation"] = "changed"
        self.assertNotEqual(EvidenceCatalog(self.bundle).digest, self.report["evidence_digest"])

    def test_integrity_does_not_pretend_to_verify_claim_meaning(self):
        self.report["findings"][0]["statement"] = "An unsupported claim attached to real citations."
        result = validate_report(self.report, self.bundle)
        self.assertTrue(result["valid"])
        self.assertIn("human review", result["warnings"][0])


class EvaluationTests(unittest.TestCase):
    def test_reference_suite_passes_with_explicit_limitations(self):
        result = evaluate_suite(ROOT / "suite.json", ROOT / "reference-reports")
        self.assertEqual((result["passed"], result["total"]), (3, 3))
        self.assertTrue(result["human_review_required"])
        self.assertIn("not a real-world", result["limitations"][0])

    def test_wrong_disposition_and_unsafe_recommendation_fail(self):
        report = fixture("reference-reports")
        report["disposition"] = "malicious"
        report["recommendations"][0]["category"] = "review_containment"
        result = evaluate_report(fixture("fixtures"), report, fixture("expectations"))
        self.assertFalse(result["automated_pass"])
        self.assertFalse(result["checks"]["expected_disposition"])
        self.assertFalse(result["checks"]["recommendation_safety"])

    def test_required_evidence_must_be_in_findings_not_just_timeline(self):
        report = fixture("reference-reports")
        reference = fixture("fixtures")["alert"]["reference"]
        for item in report["findings"]:
            item["citations"] = [reference]
        result = evaluate_report(fixture("fixtures"), report, fixture("expectations"))
        self.assertFalse(result["checks"]["required_finding_evidence"])
        self.assertEqual(result["required_evidence_coverage"], 0)

    def test_bad_benchmark_expectations_are_configuration_errors(self):
        for corrupt in ("unknown_reference", "unknown_field"):
            expectations = fixture("expectations")
            if corrupt == "unknown_reference":
                expectations["required_finding_evidence"][0]["id"] = "not-present"
            else:
                expectations["unexpected"] = True
            with self.assertRaises(ValueError):
                evaluate_report(fixture("fixtures"), fixture("reference-reports"), expectations)

    def test_missing_reports_fail_without_inventing_results(self):
        with tempfile.TemporaryDirectory() as directory:
            result = evaluate_suite(ROOT / "suite.json", directory)
        self.assertEqual(result["passed"], 0)
        self.assertTrue(all("error" in case for case in result["cases"]))

    def test_manifest_paths_and_unsafe_ids_are_rejected(self):
        manifest = load_json(ROOT / "suite.json")
        for alteration in ("escape", "unsafe_id"):
            value = deepcopy(manifest)
            if alteration == "escape":
                value["cases"][0]["bundle"] = "../outside.json"
            else:
                value["cases"][0]["id"] = "../outside"
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "suite.json"
                path.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    evaluate_suite(path, ROOT / "reference-reports")

    def test_duplicate_case_ids_are_rejected(self):
        manifest = load_json(ROOT / "suite.json")
        manifest["cases"][1]["id"] = manifest["cases"][0]["id"]
        original_load = load_json

        def load(path):
            return manifest if Path(path) == ROOT / "suite.json" else original_load(path)

        with patch("corvus.evaluation.load_json", side_effect=load), self.assertRaises(ValueError):
            evaluate_suite(ROOT / "suite.json", ROOT / "reference-reports")


class JSONInputTests(unittest.TestCase):
    def test_duplicate_keys_and_nonstandard_numbers_are_rejected(self):
        for payload in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', "bad json"):
            with self.assertRaises(ValueError):
                parse_json(payload)

    def test_input_size_and_object_shape_are_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_text("[]")
            with self.assertRaises(ValueError):
                load_json(path)
            path.write_text('{"payload":"' + "x" * 100 + '"}')
            with patch("corvus.storage.MAX_JSON_BYTES", 64), self.assertRaises(ValueError):
                load_json(path)
