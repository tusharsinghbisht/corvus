"""Structural and reference integrity, not semantic proof of model-written claims."""

from jsonschema import Draft202012Validator, FormatChecker

from ..timeutil import utc
from .evidence import EvidenceCatalog, reference_key
from .schema import REPORT_SCHEMA

VALIDATION_VERSION = "0.2"
_VALIDATOR = Draft202012Validator(REPORT_SCHEMA, format_checker=FormatChecker())


def citation_groups(report):
    for field in ("findings", "timeline", "entities", "alternative_explanations"):
        for position, item in enumerate(report[field]):
            yield f"/{field}/{position}/citations", item["citations"]


def validate_report(report, bundle):
    catalog = EvidenceCatalog(bundle)
    result = {
        "valid": False,
        "validation_version": VALIDATION_VERSION,
        "errors": [],
        "warnings": [
            "Citation existence does not prove that evidence supports a claim; human review is required."
        ],
        "citations_checked": 0,
        "unique_citations": 0,
    }

    def error(code, path, message):
        result["errors"].append({"code": code, "path": path, "message": message})

    for issue in _VALIDATOR.iter_errors(report):
        path = "/" + "/".join(str(part) for part in issue.absolute_path)
        # jsonschema's default message can include the entire sensitive input value.
        error("schema_violation", path, f"Report violates schema constraint: {issue.validator}")
        if len(result["errors"]) >= 50:
            break
    if result["errors"]:
        return result
    if report["collection_id"] != catalog.collection_id:
        error("wrong_collection", "/collection_id", "Report belongs to another collection")
    if report["evidence_digest"] != catalog.digest:
        error(
            "wrong_evidence_digest", "/evidence_digest", "Report does not match this evidence view"
        )
    ids = [finding["id"] for finding in report["findings"]]
    if len(set(ids)) != len(ids):
        error("duplicate_finding_id", "/findings", "Finding IDs must be unique")
    links = [("/summary_finding_ids", report["summary_finding_ids"])] + [
        (f"/recommendations/{i}/finding_ids", item["finding_ids"])
        for i, item in enumerate(report["recommendations"])
    ]
    for path, values in links:
        if set(values) - set(ids):
            error("unknown_finding_id", path, "Linked finding does not exist")
    seen = set()
    for path, references in citation_groups(report):
        for reference in references:
            key = reference_key(reference)
            seen.add(key)
            result["citations_checked"] += 1
            if key not in catalog.documents and key not in catalog.metadata:
                error(
                    "unknown_citation",
                    path,
                    "Cited event or allowed collection metadata is not in the bundle",
                )
    result["unique_citations"] = len(seen)
    for i, item in enumerate(report["timeline"]):
        timestamps = []
        for reference in item["citations"]:
            document = catalog.documents.get(reference_key(reference))
            if document:
                try:
                    timestamps.append(utc(document["context"].get("timestamp")))
                except ValueError:
                    pass
        try:
            timestamp = utc(item["timestamp"])
        except ValueError:
            timestamp = None
        if timestamp is None or timestamp not in timestamps:
            error(
                "unsupported_timeline_timestamp",
                f"/timeline/{i}/timestamp",
                "Timeline time must match a cited document's normalized indexed timestamp",
            )
    uncertainty_codes = [item["code"] for item in report["uncertainties"]]
    if len(set(uncertainty_codes)) != len(uncertainty_codes):
        error("duplicate_uncertainty_code", "/uncertainties", "Uncertainty codes must be unique")
    if catalog.gap_codes - set(uncertainty_codes):
        error(
            "unacknowledged_gaps",
            "/uncertainties",
            "Report must acknowledge every collection gap code",
        )
    if (catalog.partial or report["disposition"] == "inconclusive") and not uncertainty_codes:
        error(
            "missing_uncertainty",
            "/uncertainties",
            "Incomplete evidence needs explicit uncertainty",
        )
    if catalog.partial and report["disposition"] == "likely_benign":
        error(
            "incomplete_benign_clearance",
            "/disposition",
            "This MVP does not clear partial collections as likely benign",
        )
    if report["disposition"] != "inconclusive" and not any(
        finding["kind"] == "inference" for finding in report["findings"]
    ):
        error(
            "missing_disposition_reasoning",
            "/findings",
            "A definitive disposition needs an inference finding",
        )
    if report["disposition"] != "malicious" and any(
        item["category"] in ("review_containment", "review_remediation")
        for item in report["recommendations"]
    ):
        error(
            "unsupported_disruptive_recommendation",
            "/recommendations",
            "This MVP permits containment/remediation review recommendations only with a malicious disposition; uncertainty alone is insufficient",
        )
    inference_ids = {
        finding["id"] for finding in report["findings"] if finding["kind"] == "inference"
    }
    if report["disposition"] != "inconclusive" and not inference_ids.intersection(
        report["summary_finding_ids"]
    ):
        error(
            "missing_summary_rationale",
            "/summary_finding_ids",
            "Disposition summary must link to an inference finding",
        )
    result["valid"] = not result["errors"]
    return result


def report_document(document):
    """Accept a report alone or the application-generated analysis envelope."""
    return document.get("report") if "analysis_id" in document else document
