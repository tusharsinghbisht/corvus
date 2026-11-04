"""Prepare only the three reviewed Atomic tests; never execute or fetch prerequisites."""

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import yaml

PIN = "e8cfc418a064ee50d831f41a8aeccf5b80a202f5"
TESTS = {
    "T1082": (
        "66703791-c902-4560-8770-42b8a91f7667",
        "227c971954b4da7bcac0ebc5b6e04644298bc7aa62a5a56df96c0904c0eb3e06",
    ),
    "T1033": (
        "aab580c7-cc30-4a7c-b5a9-46a29066b022",
        "89984708eef6026a48025624cf7b90d0865c0b622c4c683c8c1956b87c29e410",
    ),
    "T1059.001": (
        "a538de64-1c74-46ed-aa60-b995ed302598",
        "54ebdbccfd6d5435a52bb048b3e8b9de541d8f0bd6c86f97ff982a15f1a76945",
    ),
}


def prepare(directory, computer, rounds=3):
    if not 1 <= rounds <= 3:
        raise ValueError("Only one to three bounded rounds supported")
    tests = []
    for technique, (guid, digest) in TESTS.items():
        path = directory / "definitions" / (technique + ".yaml")
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError("Pinned definition checksum mismatch")
        definition = yaml.safe_load(content)
        test = next(
            item for item in definition["atomic_tests"] if item.get("auto_generated_guid") == guid
        )
        if test.get("dependencies") or test.get("dependency_executor_name"):
            raise ValueError("Prerequisites are not allowed")
        command = test["executor"]["command"]
        for key, value in test.get("input_arguments", {}).items():
            command = command.replace("#{" + key + "}", value["default"])
        if "#{" in command:
            raise ValueError("Unresolved Atomic input")
        tests.append(
            {
                "technique": technique,
                "guid": guid,
                "name": test["name"],
                "command": command.strip(),
                "definition_sha256": digest,
                "executor": test["executor"]["name"],
            }
        )
    now = datetime.now(timezone.utc)
    campaign = {
        "schema_version": "0.1",
        "run_id": "CORVUS-ART-" + now.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8],
        "upstream_commit": PIN,
        "expected_computer_name": computer,
        "agent_id": "001",
        "rounds": rounds,
        "tests": tests,
        "scope": "Reviewed read-only discovery and harmless encoded PowerShell only; no prerequisite downloads, security tampering, persistence, credentials, lateral movement, or response actions.",
    }
    target = directory / "ground-truth" / "campaign.json"
    with target.open("x") as file:
        json.dump(campaign, file, indent=2)
    target.chmod(0o600)
    return campaign


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--computer", required=True)
    parser.add_argument("--rounds", type=int, default=3)
    args = parser.parse_args()
    os.umask(0o077)
    campaign = prepare(args.directory, args.computer, args.rounds)
    print(campaign["run_id"])
