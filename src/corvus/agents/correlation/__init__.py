"""Local, deterministic evidence correlation. Relationships are hints, not causal proof."""

from uuid import UUID

from ...timeutil import utc

VERSION = "0.1"


def guid(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = UUID(value)
        return str(parsed) if parsed.int else None
    except ValueError:
        return None


def command(document):
    source = document["source"]
    value = source.get("command_line")
    if not value:
        data = source.get("data")
        win = data.get("win") if isinstance(data, dict) else None
        fields = win.get("eventdata") if isinstance(win, dict) else None
        value = fields.get("commandLine") if isinstance(fields, dict) else None
    return value if isinstance(value, str) and len(value) >= 32 else None


def identity(document):
    """Deduplicate a Windows event mirrored into alert/archive indices, not merely same text."""
    source = document["source"]
    data = source.get("data")
    win = data.get("win") if isinstance(data, dict) else None
    system = win.get("system") if isinstance(win, dict) else None
    if isinstance(system, dict):
        parts = (
            document["context"].get("agent_id"),
            system.get("channel"),
            system.get("eventRecordID"),
            system.get("systemTime"),
        )
        if isinstance(parts[2], int) and not isinstance(parts[2], bool):
            parts = (*parts[:2], str(parts[2]), parts[3])
        if all(isinstance(part, str) and part for part in parts):
            return ("windows", *parts)
    return ("reference", *[document["reference"][key] for key in ("backend", "index", "id")])


def correlate(bundle, *, expanded=False):
    trigger = bundle["alert"]
    context = trigger["context"]
    process, parent = guid(context.get("process_guid")), guid(context.get("parent_process_guid"))
    trigger_command = command(trigger)
    seen = {identity(trigger)}
    ranked = []
    for event in bundle["events"]:
        item = event["context"]
        if (
            not isinstance(context.get("agent_id"), str)
            or not context["agent_id"]
            or item.get("agent_id") != context["agent_id"]
        ):
            continue
        try:
            distance = abs((utc(item["timestamp"]) - utc(context["timestamp"])).total_seconds())
        except (KeyError, ValueError):
            distance = float("inf")
        subject, owner = guid(item.get("process_guid")), guid(item.get("parent_process_guid"))
        if process and subject == process:
            rank, reason = 0, "Same process GUID"
        elif parent and subject == parent:
            rank, reason = 1, "Trigger parent GUID matches this process"
        elif process and owner == process:
            rank, reason = 2, "Parent GUID matches trigger process; child candidate"
        elif trigger_command and command(event) == trigger_command and distance <= 900:
            rank, reason = (
                3,
                "Exact command-line match within fifteen minutes; not proof of authorization",
            )
        elif expanded and parent and owner == parent:
            rank, reason = 4, "Shared parent GUID; sibling candidate"
        elif expanded:
            rank, reason = (
                5,
                "Same agent and indexed-time proximity only; not a verified relationship",
            )
        else:
            continue
        kind = str(item.get("event_id") or event["source"].get("event_id") or "")
        creation = kind == "1"
        ranked.append(
            (
                rank,
                not creation,
                distance,
                tuple(event["reference"][key] for key in ("backend", "index", "id")),
                event,
                reason,
                (rank, str(item.get("channel") or ""), kind),
            )
        )
    result, categories, counts = [], set(), {}
    duplicates = 0
    for *_, event, reason, category in sorted(ranked, key=lambda row: row[:4]):
        key = identity(event)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        relation = category[0]
        if not expanded and (
            category in categories or counts.get(relation, 0) >= (2 if relation == 0 else 1)
        ):
            continue
        categories.add(category)
        counts[relation] = counts.get(relation, 0) + 1
        result.append({"document": event, "reason": reason})
    return {
        "version": VERSION,
        "mode": "local_deterministic",
        "candidates": result,
        "duplicate_events": duplicates,
        "limitations": [
            "GUID/command matches are correlation hints, not proof of causation, authorization, or maliciousness.",
            "Only the saved bounded collection is inspected; no new queries, external requests, or model calls.",
        ],
    }
