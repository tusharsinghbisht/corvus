# Windows dataset and endpoint retirement

## Captured 2026-11-04

A private real-telemetry dataset is preserved on the **Wazuh VM**, independently of `windy`:

```text
/home/ubuntu/.config/corvus/datasets/atomic-20261104/
```

The final encrypted handoff is `atomic-20261104.tar.gz.fernet` alongside that directory. It uses the existing host backup key, retained separately outside Git. Never print or upload the key, source evidence, command output, or decrypted archive.

### What was executed

The three pinned/reviewed tests in the [simulation plan](windows-simulation-plan.md) were executed directly from their resolved Atomic Red Team definitions. There was no framework-wide invocation or prerequisite installation. The encoded PowerShell payload only prints `Hello, from PowerShell!`.

- Three rounds of T1082 system information/disk enumeration, T1033 `whoami /all`, and T1059.001 harmless obfuscated PowerShell.
- Three read-only administrative inventory controls.
- **12 procedure cases / 15 command executions**, since T1082 contains two commands. All recorded command exits were zero. The expected harmless PowerShell output was independently checked for all three repetitions.
- No credential theft, persistence, lateral movement, downloaded payload execution, security-policy changes, containment, or endpoint deletion.
- Sysmon and Wazuh services remained running. An existing unrestricted PowerShell execution policy was observed, not changed.

These are authorized harmless emulations, **not ground-truth malicious compromises** or a broad accuracy benchmark. A native alert does not change that distinction.

### Preserved material

- Pinned upstream YAML, source hashes, exact resolved commands, PIDs, UTC start/end times, exit codes, and captured output.
- Campaign-window native EVTX exports from Sysmon, PowerShell Operational, Security, System, and Application.
- Retained full native exports from the same five channels: **107,641 records** at capture, including 69,762 Sysmon, 2,160 PowerShell, 32,502 Security, 2,796 System, and 421 Application records. These are retained log contents, not a guarantee of lifetime history.
- A complete bounded indexed campaign export containing **1,102 archive events and 198 alerts**. Broader retained-index exports, if present, have their own complete-query manifests; partial files are not dataset inputs or sealed members.
- **12 evidence-bound replay inputs** under `inputs/`, each rooted in real recorded execution. All have real native detections; the **33 unique case-linked native alerts** were also verified present in Corvus. No synthetic detection was inserted.
- `ground-truth/dataset.json` maps case files to authorized procedures and execution records. **Never include this file, campaign annotations, execution output, or evaluator expectations in Analyst input.**

Raw telemetry includes SSH/controller and export activity. Replay inputs select recorded process-GUID trees and explicitly mark excluded channels/controller script contents and partial coverage. Real source fields and native references are not rewritten. Markers alone must not be treated as proof of authorized behavior. Native detection, execution observed, Corvus ingestion, and model processing are separate outcomes. No new model request was made and automatic policies stayed disabled.

### Verification and recovery notes

The native transfer was compressed before copying. The compressed archive hash and all **43 native artifact hashes** were checked on the Wazuh VM. Native files were read by the Windows event-log API before transfer. On Linux, all ten EVTX files have valid magic and header CRC and sample record XML was readable with `python-evtx==0.8.1`.

These Windows exports use EVTX **3.2**. That library's convenience `FileHeader.verify()` hardcodes minor version 3.1 and returns false; this is documented rather than treated as a successful strict heuristic or silently changing source bytes. Header CRC and sample decoding are not a full semantic/count validation. Original EVTX and complete indexed JSON remain available for stronger offline decoding later.

The initial controller ran one harmless inventory control but recorded a null exit status due to process-handle handling. It stopped before Atomic execution and is preserved separately under `ground-truth/failed-attempt/`; it is not counted as a successful case. The corrected controller completed all 15 commands. Its SSH wait expired during slow historical-log enumeration; only that verified completed-test controller was stopped. The read-only finalizer finished native capture without replaying tests. The exact original campaign EVTX query end was not persisted before interruption; this uncertainty is explicit in `native-export.json`, while command and native event timestamps remain preserved.

## Offline use

Use the canonical Git checkout on the authorized VM. No endpoint connection or model credential is needed to validate saved inputs:

```bash
cd /opt/corvus/app
# Preparation checks definitions and writes a new campaign only; it does not execute tests.
# Do not rerun an existing campaign merely because capture/transfer failed.

# These commands need existing captures and refuse to overwrite prior output:
.venv/bin/python infra/simulations/build.py /private/new-dataset-directory
sudo .venv/bin/python infra/simulations/seal.py /private/new-dataset-directory
```

`capture.py` runs inside the authenticated API container using the dedicated read-only indexer account. Redirect its output to a private host file, never chat or Git. It bounds time, queries, events, and bytes; complete leaf searches must succeed before a final manifest is published. The shell must use `pipefail` when compressing output. Failed `.partial` files are not complete exports. Retention may already have deleted older indexed data; no export can reconstruct it.

`seal.py` includes only verified native copies, definitions, ground truth, replay inputs, and completed evidence files. It excludes partial exports and private diagnostic logs, authenticates encryption, and rechecks every decrypted member checksum before publication. Keep the encrypted package and key separately off-host for protection against losing the Wazuh VM; that replication is not automated.

## Retiring windy

The captured dataset can be used without `windy`, and its preserved files are outside Wazuh's three-day archive deletion policy. Verify the final sealed-package result before termination. This is a **dataset export, not a full disk/VM backup**: retain any unrelated endpoint files, configuration, or snapshots you need separately.

No cloud stop/termination was performed by Corvus or the capture tools. Stopping an EC2 instance stops compute charges but attached EBS/snapshots can continue to cost money. Termination and volume/snapshot retention choices remain an explicit owner action; do not delete the Wazuh VM or dataset storage by mistake.
