"""Deterministic, bounded Analyst input. Originals stay in the investigation record."""

import json
import re
from copy import deepcopy

from ...reporting.evidence import EvidenceCatalog
from ...reporting.schema import REPORT_SCHEMA
from ...timeutil import utc
from ..correlation import correlate

CONTEXT_VERSION = "2.1"
TIMESTAMP_PATTERN = re.compile(
    REPORT_SCHEMA["properties"]["timeline"]["items"]["properties"]["timestamp"]["pattern"]
)
MAX_EVENTS = 4
MAX_BYTES = 16 * 1024
PROFILES = {"focused": (MAX_EVENTS, MAX_BYTES), "expanded": (12, 48 * 1024)}


class ContextBudgetError(ValueError):
    pass


PRIORITY = (
    "timestamp",
    "agent",
    "rule",
    "data",
    "win",
    "eventdata",
    "system",
    "eventID",
    "image",
    "commandLine",
    "parentImage",
    "parentCommandLine",
    "processGuid",
    "parentProcessGuid",
    "processId",
    "user",
    "targetFilename",
    "targetObject",
    "destinationIp",
    "destinationPort",
    "sourceIp",
    "hashes",
)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def project(value, path="", depth=0):
    """Keep useful structure; mark excerpts explicitly rather than silently rewriting facts."""
    if isinstance(value, str) and len(value) > 1800:
        return {"excerpt": value[:1800], "omitted_characters": len(value) - 1800}, True
    if isinstance(value, (dict, list)) and depth >= 7:
        return {"omitted_nested_value": True}, True
    if isinstance(value, dict):
        keys = sorted(value, key=lambda key: (PRIORITY.index(key) if key in PRIORITY else 100, key))
        result, reduced = {}, len(keys) > 24
        for key in keys[:24]:
            result[key], changed = project(value[key], path + "/" + key, depth + 1)
            reduced |= changed
        if len(keys) > 24:
            result["_corvus_omitted_fields"] = len(keys) - 24
        return result, reduced
    if isinstance(value, list):
        result, reduced = [], len(value) > 8
        for item in value[:8]:
            projected, changed = project(item, path, depth + 1)
            result.append(projected)
            reduced |= changed
        if len(value) > 8:
            result.append({"omitted_items": len(value) - 8})
        return result, reduced
    return value, False


def canonicalize_indexed_time(document):
    """Format only the indexed context timestamp; never infer source event time or round it."""
    value = document["context"].get("timestamp")
    if not isinstance(value, str):
        return False
    try:
        instant = utc(value)
    except ValueError:
        return False
    canonical = re.sub(r"([+-][0-9]{2})([0-9]{2})$", r"\1:\2", value)
    if len(canonical) > 10 and canonical[10] in ("t", " "):
        canonical = canonical[:10] + "T" + canonical[11:]
    if TIMESTAMP_PATTERN.fullmatch(canonical) and utc(canonical) == instant:
        document["context"]["timestamp"] = canonical
        return canonical != value
    return False


def source_view(source):
    value = deepcopy(source)
    data = value.get("data")
    win = data.get("win") if isinstance(data, dict) else None
    omitted = []
    if isinstance(win, dict) and isinstance(win.get("eventdata"), dict) and win["eventdata"]:
        if "full_log" in value:
            value.pop("full_log")
            omitted.append("/full_log")
        if isinstance(win.get("system"), dict) and "message" in win["system"]:
            win["system"].pop("message")
            omitted.append("/data/win/system/message")
    projected, reduced = project(value)
    if omitted:
        projected["_corvus_omitted_renderings"] = omitted
    return projected, reduced or bool(omitted)


def select_context(bundle, *, profile="focused", saved_collection=None, workflow="direct"):
    if profile not in PROFILES:
        raise ValueError("Unknown context profile")
    max_events, max_bytes = PROFILES[profile]
    catalog = EvidenceCatalog(bundle)
    correlation = correlate(bundle, expanded=profile == "expanded")
    selected = deepcopy(bundle)
    selected["events"] = []
    if workflow not in ("direct", "agentic"):
        raise ValueError("Unsupported investigation workflow")
    if workflow == "agentic":
        selected["scope"]["approved_capabilities"] = {
            "workflow": "analyst.agentic.v1",
            "max_model_requests": 3,
            "tools": ["correlation", "intel"],
            "scope": "selected evidence only; no external lookups or response actions",
        }
    if saved_collection:
        selected["scope"]["saved_collection_reuse"] = deepcopy(saved_collection)
        selected["gaps"].append(
            {
                "code": "saved_collection_reused",
                "message": "Historical saved evidence was reused without a fresh backend query. Preserve its original time and coverage; these observations do not establish current endpoint state.",
            }
        )
    selection = {
        "version": CONTEXT_VERSION,
        "profile": profile,
        "max_events": max_events,
        "max_bytes": max_bytes,
        "correlation_version": correlation["version"],
        "matches": [],
        "original_evidence_digest": catalog.digest,
        "collected_events": len(bundle["events"]),
        "selected_events": 0,
        "omitted_events": len(bundle["events"]),
        "excerpted_documents": 0,
        "canonicalized_indexed_timestamps": 0,
        "original_bytes": len(encoded(catalog.view)),
        "strategy": "Trigger retained. Focused mode selects representative process-GUID or exact command matches only, without time-only filler or siblings. Expanded mode permits bounded broader context. Verbose Windows renderings may be omitted when structured event data exists; additional text may be lost. All omissions are explicit and originals stay local.",
    }
    selected["scope"]["context_selection"] = selection
    selected["alert"]["source"], reduced = source_view(bundle["alert"]["source"])
    selection["excerpted_documents"] = int(reduced)
    selection["canonicalized_indexed_timestamps"] = int(
        canonicalize_indexed_time(selected["alert"])
    )

    def sync_query_references():
        # Reference lists repeat data already in selected documents. Preserve actual query
        # counts/status/scope, but do not spend the small input budget listing omitted IDs.
        references = {
            json.dumps(document["reference"], sort_keys=True)
            for document in [selected["alert"], *selected["events"]]
        }
        omitted = 0
        for original, query in zip(bundle["queries"], selected["queries"]):
            if isinstance(original.get("event_references"), list):
                kept = [
                    reference
                    for reference in original["event_references"]
                    if json.dumps(reference, sort_keys=True) in references
                ]
                query["event_references"] = kept
                count = len(original["event_references"]) - len(kept)
                if count:
                    query["omitted_event_references"] = count
                    query["reference_list_scope"] = (
                        "Selected input only; returned/total counts still describe the original local query."
                    )
                else:
                    query.pop("omitted_event_references", None)
                    query.pop("reference_list_scope", None)
                omitted += count
        selection["omitted_query_references"] = omitted

    sync_query_references()
    # One explicit gap covers all context selection omissions; it is required by validation.
    gap = {
        "code": "analyst_context_reduced",
        "message": "Analyst input omits collected events or source content. Inspect scope.context_selection and local originals; omissions are not evidence of absence.",
    }
    selected["gaps"].append(gap)
    selected["status"] = "partial"
    for match in correlation["candidates"]:
        if len(selected["events"]) >= max_events:
            break
        candidate = deepcopy(match["document"])
        candidate["source"], changed = source_view(candidate["source"])
        canonicalized = canonicalize_indexed_time(candidate)
        selected["events"].append(candidate)
        selection["matches"].append(
            {"reference": candidate["reference"], "reason": match["reason"]}
        )
        selection["selected_events"] += 1
        selection["omitted_events"] -= 1
        selection["excerpted_documents"] += int(changed)
        selection["canonicalized_indexed_timestamps"] += int(canonicalized)
        sync_query_references()
        if len(encoded(EvidenceCatalog(selected).view)) > max_bytes:
            selected["events"].pop()
            selection["matches"].pop()
            selection["selected_events"] -= 1
            selection["omitted_events"] += 1
            selection["excerpted_documents"] -= int(changed)
            selection["canonicalized_indexed_timestamps"] -= int(canonicalized)
            sync_query_references()
    if (
        not selection["omitted_events"]
        and not selection["excerpted_documents"]
        and not selection["omitted_query_references"]
    ):
        selected["gaps"].remove(gap)
        selected["status"] = "partial" if saved_collection else bundle["status"]
    selected["events"].sort(key=lambda event: str(event["context"].get("timestamp", "")))
    if len(encoded(EvidenceCatalog(selected).view)) > max_bytes:
        raise ContextBudgetError(
            "Trigger and collection metadata exceed this context budget; choose a broader profile locally"
        )
    return selected
