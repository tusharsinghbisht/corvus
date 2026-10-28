"""A single JSON Schema shared by prompting, validation, and schema export."""


def text(limit=4000):
    return {"type": "string", "minLength": 1, "maxLength": limit, "pattern": r"\S"}


def choices(*values):
    return {"type": "string", "enum": list(values)}


def array(items, minimum=0, maximum=64, unique=False):
    return {
        "type": "array",
        "items": items,
        "minItems": minimum,
        "maxItems": maximum,
        "uniqueItems": unique,
    }


def record(properties):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


REFERENCE_SCHEMA = record({"backend": text(128), "index": text(512), "id": text(512)})
COLLECTION_REFERENCE_SCHEMA = record(
    {
        "collection_id": text(128),
        "path": {
            "type": "string",
            "pattern": r"^/(status|scope|queries|gaps|limitations)(/[0-9]+)?$",
        },
    }
)
CITATIONS = array(
    {"anyOf": [{"$ref": "#/$defs/reference"}, {"$ref": "#/$defs/collection_reference"}]},
    minimum=1,
    maximum=32,
    unique=True,
)
FINDING_IDS = array({"type": "string", "pattern": r"^F[1-9][0-9]{0,2}$"}, 1, 64, True)
DISPOSITIONS = choices("malicious", "likely_benign", "inconclusive")
RECOMMENDATIONS = choices(
    "investigate", "monitor", "review_containment", "review_remediation", "no_action"
)
REPORT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Corvus advisory investigation report v0.1",
    "$defs": {"reference": REFERENCE_SCHEMA, "collection_reference": COLLECTION_REFERENCE_SCHEMA},
    **record(
        {
            "schema_version": {"const": "0.1"},
            "collection_id": text(128),
            "evidence_digest": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
            "disposition": DISPOSITIONS,
            "summary": text(8000),
            "summary_finding_ids": FINDING_IDS,
            "findings": array(
                record(
                    {
                        "id": {"type": "string", "pattern": r"^F[1-9][0-9]{0,2}$"},
                        "kind": choices("observation", "inference"),
                        "statement": text(),
                        "citations": CITATIONS,
                    }
                ),
                minimum=1,
            ),
            "timeline": array(
                record(
                    {
                        "timestamp": {
                            "type": "string",
                            "format": "date-time",
                            "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$",
                        },
                        "description": text(),
                        "citations": CITATIONS,
                    }
                ),
                maximum=128,
            ),
            "entities": array(
                record(
                    {
                        "kind": choices("host", "user", "process", "file", "network"),
                        "value": text(1024),
                        "citations": CITATIONS,
                    }
                )
            ),
            "alternative_explanations": array(
                record({"explanation": text(), "assessment": text(), "citations": CITATIONS}),
                minimum=1,
                maximum=16,
            ),
            "uncertainties": array(
                record({"code": text(128), "description": text(), "next_step": text()})
            ),
            "recommendations": array(
                record(
                    {
                        "category": RECOMMENDATIONS,
                        "description": text(),
                        "rationale": text(),
                        "finding_ids": FINDING_IDS,
                    }
                ),
                minimum=1,
                maximum=16,
            ),
            "limitations": array(text(), minimum=1, maximum=32, unique=True),
            "response_executed": {"const": False},
        }
    ),
}
