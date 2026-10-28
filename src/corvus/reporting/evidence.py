"""Select analyst-visible evidence, bind reports to it, and resolve exact references."""

import hashlib
import json
from copy import deepcopy

from jsonschema import Draft202012Validator

from .schema import REFERENCE_SCHEMA

# No connection credentials, transport audit, fixture paths, or evaluator metadata.
VISIBLE_FIELDS = (
    "schema_version",
    "collection_id",
    "status",
    "collector",
    "alert",
    "entities",
    "scope",
    "queries",
    "events",
    "gaps",
    "limitations",
)
_REFERENCE_VALIDATOR = Draft202012Validator(REFERENCE_SCHEMA)


def reference_key(reference):
    if "path" in reference:
        return "collection", reference["collection_id"], reference["path"]
    return "event", reference["backend"], reference["index"], reference["id"]


class EvidenceCatalog:
    def __init__(self, bundle):
        if not isinstance(bundle, dict) or bundle.get("schema_version") != "0.1":
            raise ValueError("Unsupported evidence bundle schema")
        if not isinstance(bundle.get("collection_id"), str) or not bundle["collection_id"]:
            raise ValueError("Evidence bundle needs a collection ID")
        if bundle.get("status") not in ("collected", "partial"):
            raise ValueError("Unsupported evidence collection status")
        if not isinstance(bundle.get("events"), list) or len(bundle["events"]) > 5000:
            raise ValueError("Evidence bundle needs an events list of at most 5000 documents")
        for field in ("queries", "gaps"):
            if not isinstance(bundle.get(field), list) or not all(
                isinstance(item, dict) for item in bundle[field]
            ):
                raise ValueError(f"Evidence bundle needs a {field} list of objects")
        if any(not isinstance(gap.get("code"), str) or not gap["code"] for gap in bundle["gaps"]):
            raise ValueError("Every collection gap needs a code")
        self.documents = {}
        for document in [bundle.get("alert"), *bundle["events"]]:
            if not isinstance(document, dict) or not _REFERENCE_VALIDATOR.is_valid(
                document.get("reference")
            ):
                raise ValueError("Every evidence document needs a complete source reference")
            if not isinstance(document.get("context"), dict) or not isinstance(
                document.get("source"), dict
            ):
                raise ValueError("Every evidence document needs context and source objects")
            key = reference_key(document["reference"])
            if key in self.documents and self.documents[key] != document:
                raise ValueError("Conflicting evidence documents share the same reference")
            self.documents[key] = document
        self.view = deepcopy({key: bundle[key] for key in VISIBLE_FIELDS if key in bundle})
        canonical = json.dumps(
            self.view, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
        self.digest = hashlib.sha256(canonical).hexdigest()
        self.collection_id = bundle["collection_id"]
        self.metadata = {}
        for field in ("status", "scope", "queries", "gaps", "limitations"):
            if field not in self.view:
                continue
            value = self.view[field]
            self.metadata[("collection", self.collection_id, "/" + field)] = value
            if isinstance(value, list):
                for index, item in enumerate(value):
                    self.metadata[("collection", self.collection_id, f"/{field}/{index}")] = item
        self.gap_codes = {gap["code"] for gap in bundle["gaps"]}
        self.partial = bundle["status"] == "partial" or any(
            query.get("status") in ("error", "partial")
            or query.get("partial")
            or query.get("truncated")
            for query in bundle["queries"]
        )
