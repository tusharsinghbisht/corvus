"""Deterministic, bounded Analyst input. Originals stay in the investigation record."""

import json
from copy import deepcopy

from ...reporting.evidence import EvidenceCatalog
from ...timeutil import utc

CONTEXT_VERSION = "1.0"
MAX_EVENTS = 24
MAX_BYTES = 64 * 1024
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


def select_context(bundle):
    catalog = EvidenceCatalog(bundle)
    selected = deepcopy(bundle)
    selected["events"] = []
    selection = {
        "version": CONTEXT_VERSION,
        "original_evidence_digest": catalog.digest,
        "collected_events": len(bundle["events"]),
        "selected_events": 0,
        "omitted_events": len(bundle["events"]),
        "excerpted_documents": 0,
        "original_bytes": len(encoded(catalog.view)),
        "strategy": "Trigger always retained; process-GUID matches first, then indexed-time proximity. Maximum 24 context events and 64 KiB selected evidence. Excerpts are explicitly marked; originals remain local.",
    }
    selected["scope"]["context_selection"] = selection
    selected["alert"]["source"], reduced = project(bundle["alert"]["source"])
    selection["excerpted_documents"] = int(reduced)
    # One explicit gap covers all context selection omissions; it is required by validation.
    gap = {
        "code": "analyst_context_reduced",
        "message": "Analyst input omits collected events or source content. Inspect scope.context_selection and local originals; omissions are not evidence of absence.",
    }
    selected["gaps"].append(gap)
    selected["status"] = "partial"
    trigger = bundle["alert"]["context"]
    guids = {
        value
        for value in (trigger.get("process_guid"), trigger.get("parent_process_guid"))
        if isinstance(value, str) and value
    }
    timestamp = utc(trigger["timestamp"])

    def rank(event):
        context = event["context"]
        match = any(
            isinstance(value, str) and value in guids
            for value in (context.get("process_guid"), context.get("parent_process_guid"))
        )
        try:
            distance = abs((utc(context["timestamp"]) - timestamp).total_seconds())
        except (KeyError, ValueError):
            distance = float("inf")
        return not match, distance, json.dumps(event["reference"], sort_keys=True)

    for event in sorted(bundle["events"], key=rank):
        if len(selected["events"]) >= MAX_EVENTS:
            break
        candidate = deepcopy(event)
        candidate["source"], changed = project(candidate["source"])
        selected["events"].append(candidate)
        selection["selected_events"] += 1
        selection["omitted_events"] -= 1
        selection["excerpted_documents"] += int(changed)
        if len(encoded(EvidenceCatalog(selected).view)) > MAX_BYTES:
            selected["events"].pop()
            selection["selected_events"] -= 1
            selection["omitted_events"] += 1
            selection["excerpted_documents"] -= int(changed)
    if not selection["omitted_events"] and not selection["excerpted_documents"]:
        selected["gaps"].remove(gap)
        selected["status"] = bundle["status"]
    selected["events"].sort(key=lambda event: str(event["context"].get("timestamp", "")))
    if len(encoded(EvidenceCatalog(selected).view)) > MAX_BYTES:
        raise ValueError("Trigger and collection metadata exceed the selected context budget")
    return selected
