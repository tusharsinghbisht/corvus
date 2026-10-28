"""Offline contract/regression scoring. No model calls and no semantic judge."""

import re
from pathlib import Path

from jsonschema import Draft202012Validator

from .reporting.evidence import EvidenceCatalog, reference_key
from .reporting.schema import DISPOSITIONS, RECOMMENDATIONS, REFERENCE_SCHEMA, array, record, text
from .reporting.validation import report_document, validate_report
from .storage import load_json

EXPECTATIONS_SCHEMA = record(
    {
        "case_id": text(64),
        "provenance": {"const": "synthetic"},
        "expected_disposition": DISPOSITIONS,
        "required_finding_evidence": array(REFERENCE_SCHEMA, minimum=1, unique=True),
        "required_uncertainties": array(text(128), unique=True),
        "forbidden_recommendations": array(RECOMMENDATIONS, unique=True),
        "human_review_questions": array(text(), minimum=1),
    }
)


def evaluate_report(bundle, candidate, expectations):
    if not Draft202012Validator(EXPECTATIONS_SCHEMA).is_valid(expectations):
        raise ValueError("Invalid evaluator expectations")
    report = report_document(candidate)
    validation = validate_report(report, bundle)
    shaped = isinstance(report, dict) and not any(
        error["code"] == "schema_violation" for error in validation["errors"]
    )
    cited = (
        {reference_key(ref) for finding in report["findings"] for ref in finding["citations"]}
        if shaped
        else set()
    )
    required = {reference_key(ref) for ref in expectations["required_finding_evidence"]}
    # Invalid benchmark configuration must not be mistaken for poor analyst performance.
    catalog = EvidenceCatalog(bundle)
    if not required <= set(catalog.documents):
        raise ValueError("Evaluator expects evidence that is not in its bundle")
    uncertainty = {item["code"] for item in report["uncertainties"]} if shaped else set()
    categories = {item["category"] for item in report["recommendations"]} if shaped else set()
    checks = {
        "report_integrity": validation["valid"],
        "expected_disposition": shaped
        and report["disposition"] == expectations["expected_disposition"],
        "required_finding_evidence": required <= cited,
        "required_uncertainties": set(expectations["required_uncertainties"]) <= uncertainty,
        "recommendation_safety": not (set(expectations["forbidden_recommendations"]) & categories),
    }
    return {
        "case_id": expectations["case_id"],
        "automated_pass": all(checks.values()),
        "checks": checks,
        "required_evidence_coverage": len(required & cited) / len(required),
        "validation": validation,
        "human_review_required": True,
        "human_review_questions": expectations["human_review_questions"],
    }


def _suite_file(root, relative):
    if not isinstance(relative, str) or Path(relative).is_absolute():
        raise ValueError("Suite paths must be relative")
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Suite paths must stay within the suite directory")
    return path


def evaluate_suite(manifest_path, reports_directory):
    manifest_path = Path(manifest_path).expanduser().resolve()
    manifest = load_json(manifest_path)
    if manifest.get("schema_version") != "0.1" or not isinstance(manifest.get("cases"), list):
        raise ValueError("Invalid evaluation manifest")
    if not 1 <= len(manifest["cases"]) <= 100:
        raise ValueError("Evaluation suite must contain 1 to 100 cases")
    results = []
    seen = set()
    for case in manifest["cases"]:
        if not isinstance(case, dict) or set(case) != {"id", "bundle", "expectations"}:
            raise ValueError("Invalid evaluation case entry")
        identifier = case["id"]
        if (
            not isinstance(identifier, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", identifier)
            or identifier in seen
        ):
            raise ValueError("Case IDs must be unique safe identifiers")
        seen.add(identifier)
        bundle = load_json(_suite_file(manifest_path.parent, case["bundle"]))
        expectations = load_json(_suite_file(manifest_path.parent, case["expectations"]))
        if expectations.get("case_id") != identifier:
            raise ValueError("Case and expectation IDs do not match")
        # Validate benchmark configuration even if a candidate report is missing.
        evaluate_report(bundle, {}, expectations)
        try:
            candidate = load_json(Path(reports_directory).expanduser() / (identifier + ".json"))
        except (OSError, ValueError):
            results.append(
                {
                    "case_id": identifier,
                    "automated_pass": False,
                    "error": "Candidate report is missing or unreadable",
                    "human_review_required": True,
                }
            )
            continue
        results.append(evaluate_report(bundle, candidate, expectations))
    return {
        "schema_version": "0.1",
        "scope": "synthetic_contract_and_expectation_checks",
        "cases": results,
        "passed": sum(item["automated_pass"] for item in results),
        "total": len(results),
        "human_review_required": True,
        "limitations": [
            "These small synthetic cases are regression checks, not a real-world accuracy benchmark.",
            "Evidence citation coverage does not establish semantic support or detect every unsafe claim.",
            "Human review is required even when all automated checks pass.",
        ],
    }
