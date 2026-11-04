"""Build private replay cases from preserved real events; ground truth stays separate."""

import argparse
import gzip
import hashlib
import json
from collections import defaultdict
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from corvus.reporting.evidence import EvidenceCatalog
from corvus.timeutil import utc


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def export(path):
    events = []
    with gzip.open(path, "rt") as file:
        for line in file:
            row = json.loads(line)
            if row["type"] == "event":
                events.append(row["document"])
            else:
                manifest = row
    if not manifest["complete_within_queries"] or len(events) != manifest["events"]:
        raise ValueError("Incomplete indexed export")
    return events, manifest


def windows(document):
    data = document["source"].get("data")
    return data.get("win", {}) if isinstance(data, dict) else {}


def event_identity(document):
    win = windows(document)
    system = win.get("system", {})
    return tuple(
        str(value or "")
        for value in (
            document["context"].get("agent_id"),
            system.get("channel"),
            system.get("eventRecordID"),
            system.get("systemTime"),
        )
    )


def ref(document):
    return tuple(document["reference"][key] for key in ("backend", "index", "id"))


def build(root):
    campaign = load(root / "ground-truth/campaign.json")
    native = root / "native/verified" / campaign["run_id"]
    execution = load(native / "execution.json")
    for item in load(native / "SHA256SUMS.json"):
        path = native / item["file"]
        if (
            path.parent != native
            or path.stat().st_size != item["bytes"]
            or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]
        ):
            raise ValueError("Native file checksum mismatch")
    archives, archive_manifest = export(root / "evidence/campaign-archives.ndjson.gz")
    alerts, alert_manifest = export(root / "evidence/campaign-alerts.ndjson.gz")
    groups = defaultdict(list)
    for record in execution["records"]:
        if record["exit_code"] != 0:
            raise ValueError("Unsuccessful command cannot be labeled completed")
        groups[(record["round"], record["guid"])].append(record)
    if len(groups) != 12:
        raise ValueError("Expected three controls and nine reviewed tests")
    cases = []
    inputs = root / "inputs"
    inputs.mkdir(mode=0o700)
    for (round_number, guid), records in groups.items():
        first = min(utc(record["start_utc"]) for record in records)
        last = max(utc(record["end_utc"]) for record in records)
        pids = {str(record["cmd_pid"]) for record in records}
        anchors = [
            event
            for event in archives
            if str(event["context"].get("event_id")) == "1"
            and str(event["context"].get("process_id")) in pids
            and first - timedelta(seconds=10)
            <= utc(event["context"]["timestamp"])
            <= last + timedelta(seconds=45)
        ]
        if not anchors:
            raise ValueError("Missing real Sysmon execution anchor; do not invent a case")
        guids = {
            event["context"]["process_guid"]
            for event in anchors
            if event["context"].get("process_guid")
        }
        for _ in range(8):
            expanded = guids | {
                event["context"]["process_guid"]
                for event in archives
                if event["context"].get("process_guid")
                and event["context"].get("parent_process_guid") in guids
                and first - timedelta(seconds=10)
                <= utc(event["context"]["timestamp"])
                <= last + timedelta(minutes=2)
            }
            if expanded == guids:
                break
            guids = expanded
        evidence = [
            event
            for event in archives
            if (
                event["context"].get("process_guid") in guids
                or event["context"].get("parent_process_guid") in guids
            )
            and first - timedelta(seconds=10)
            <= utc(event["context"]["timestamp"])
            <= last + timedelta(minutes=2)
        ]
        identities = {event_identity(event) for event in evidence if all(event_identity(event))}
        detections = [
            event
            for event in alerts
            if event["context"].get("process_guid") in guids
            or (all(event_identity(event)) and event_identity(event) in identities)
        ]
        trigger = detections[0] if detections else anchors[0]
        events = [event for event in evidence if ref(event) != ref(trigger)]
        bundle = {
            "schema_version": "0.1",
            "collection_id": str(uuid4()),
            "status": "partial",
            "collector": {
                "name": "corvus-private-dataset",
                "mode": "read_only",
                "data_kind": "real_telemetry",
            },
            "alert": trigger,
            "entities": trigger["context"],
            "scope": {
                "agent_id": "001",
                "start": (first - timedelta(seconds=10)).isoformat(),
                "end": (last + timedelta(minutes=2)).isoformat(),
                "time_field": "timestamp",
                "trigger_kind": "native_detection"
                if detections
                else "native_archive_event_not_detection",
            },
            "queries": [
                {
                    "name": "saved_process_guid_replay",
                    "status": "ok",
                    "returned": len(events),
                    "event_references": [event["reference"] for event in events],
                }
            ],
            "events": events,
            "gaps": [
                {
                    "code": "process_guid_replay_scope",
                    "message": "Only the recorded process GUID tree is included. Other log channels, PID-only events, unrelated activity, and controller script contents are excluded. This is not comprehensive host coverage.",
                }
            ],
            "limitations": [
                "Saved real source documents and native references, not rewritten synthetic detections.",
                "A source archive anchor is not an alert when scope.trigger_kind says native_archive_event_not_detection.",
                "Process relationships and timing do not prove malicious intent, authorization, or completed impact.",
            ],
        }
        digest = EvidenceCatalog(bundle).digest
        name = "case-" + str(len(cases) + 1).zfill(2) + ".json"
        with (inputs / name).open("x") as file:
            json.dump(bundle, file, ensure_ascii=False, indent=2)
        (inputs / name).chmod(0o600)
        cases.append(
            {
                "input": name,
                "round": round_number,
                "guid": guid,
                "technique": records[0]["technique"],
                "role": records[0]["role"],
                "command_records": [record["id"] for record in records],
                "operator_intent": "authorized harmless laboratory procedure, not a compromise",
                "execution_observed": True,
                "cmd_pids": sorted(pids),
                "anchor_references": [event["reference"] for event in anchors],
                "events": len(events),
                "native_alerts": len(detections),
                "native_alert_references": [event["reference"] for event in detections],
                "evidence_digest": digest,
                "model_processed": False,
                "expected_disposition": None,
            }
        )
    result = {
        "schema_version": "0.1",
        "run_id": campaign["run_id"],
        "cases": cases,
        "archive_export_events": len(archives),
        "alert_export_events": len(alerts),
        "limitations": [
            "Three repetitions of three reviewed techniques plus controls are an operational smoke dataset, not a broad attack benchmark.",
            "Ground truth must not be included in model input. Markers alone do not establish authorized activity.",
            "An observed process and native detection are separate outcomes; no synthetic alerts or malicious verdict labels were added.",
            "Native export recovery and the failed initial controller are preserved for audit.",
            "No model calls, response execution, or cloud deletion were performed.",
        ],
    }
    with (root / "ground-truth/dataset.json").open("x") as file:
        json.dump(result, file, indent=2)
    print(
        json.dumps(
            {
                "replay_cases": len(cases),
                "controls": sum(case["role"] == "control" for case in cases),
                "technique_cases": sum(case["role"] == "technique_emulation" for case in cases),
                "cases_with_native_alerts": sum(bool(case["native_alerts"]) for case in cases),
                "all_real_execution_anchors": True,
            }
        )
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    build(parser.parse_args().directory)
