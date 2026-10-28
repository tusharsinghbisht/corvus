# Windows technique-emulation plan

Target: authorized lab endpoint `windy` (Wazuh agent `001`), PowerShell over SSH. Real telemetry, not rewritten synthetic events. No simulation has been performed as part of this plan yet.

## Framework choice

**Atomic Red Team is the sole simulation framework for this implementation.** Use reviewed tests from [Atomic Red Team](https://github.com/redcanaryco/atomic-red-team), executed directly or through its PowerShell runner [Invoke-AtomicRedTeam](https://github.com/redcanaryco/invoke-atomicredteam). Invoke-AtomicRedTeam is a runner for the same test library, not a second emulation framework. Individual tests are inspectable and can be chained into a controlled scenario producing real endpoint telemetry.

CALDERA is not part of this deployment or execution plan. Its extra controller and endpoint agent are unnecessary for validating the first live ingestion/Analyst workflow. No simulation framework has been installed or executed yet.

Reviewed upstream snapshots (pin and re-fetch before execution):
- Atomic Red Team: `e8cfc418a064ee50d831f41a8aeccf5b80a202f5`
- Invoke-AtomicRedTeam: `8af478bb9e4637df568ac1e596553b025b16cd1b`

**Never run every test under a technique ID.** T1059.001 includes credential-theft tooling as well as harmless PowerShell examples. Select a reviewed test GUID, inspect its commands/dependencies/cleanup, and disable automatic prerequisite downloads. Do not disable Defender, AMSI, logging, or execution policy to force a test to succeed.

## First campaign

| Stage | Technique / procedure | Purpose |
| --- | --- | --- |
| Control | Normal PowerShell inventory and a unique temporary marker | Establish benign lookalike and collection behavior |
| Discovery | T1082, System Information Discovery; GUID `66703791-c902-4560-8770-42b8a91f7667` | Native systeminfo and read-only disk registry query |
| Discovery | T1033, User Discovery — whoami; GUID `aab580c7-cc30-4a7c-b5a9-46a29066b022` | Local user/security-context discovery only |
| Suspicious execution | T1059.001, PowerShell Command Execution; GUID `a538de64-1c74-46ed-aa60-b995ed302598` | Encoded/obfuscated PowerShell with harmless output, not malware |
| Controlled chain, later | Above discovery/execution plus a plain-text download from an owned lab server | Correlate process/file/network evidence without executing a downloaded payload |

Use a unique run ID and a dedicated temporary working directory. Record actual parent/child PIDs and GUIDs; do not claim an Office parent or full compromise when only command-shell execution was emulated. If inputs change to add a marker, preserve the exact resolved command and label the adaptation.

First pass excludes credential dumping, lateral movement, exploitation, real C2, security tampering, account creation, log clearing, destructive file operations, and persistence. Reversible user-scope scheduled-task/Run-key tests can be a later separately reviewed stage after snapshot/cleanup verification.

## Execution and verification

1. Check agent/Sysmon health, time synchronization, private connectivity, and available disk. Record baseline alert rates and the active Sysmon config hash. Take an endpoint snapshot if available before any stateful test.
2. Preserve pinned test definitions, SHA-256 hashes, resolved inputs, host, start/end UTC timestamps, exit status, and exact cleanup steps in a private controller manifest.
3. Run a single reviewed procedure through PowerShell, wait for telemetry, and independently verify Windows event records, searchable archives, and any Wazuh alert references.
4. Record **telemetry observed**, **native detection fired**, **Corvus ingested**, and **Analyst processed** as separate outcomes. A command may generate telemetry without triggering an alert. Do not invent an alert or silently install a new detection rule to hide that gap.
5. Once ingested, manually request Analyst triage with explicit Azure-transfer consent after inspecting the selected bundle. Keep evaluator intent/expected outcomes out of the prompt. Marker text alone is not evidence of authorized activity.
6. Review report claims against source fields: execution vs intent, PID vs GUID, connection vs download/C2/exfiltration, attempted vs completed actions, and unknown vs absent activity. Harmless payloads exercising suspicious syntax are not automatically proof of a malicious compromise.
7. Clean only run-owned files/resources. Verify cleanup; preserve telemetry and manifests. Stop on unexpected behavior, security-product health changes, or scope expansion.

Only selected, approved evidence is sent to the exact configured `DeepSeek-V4-Flash` deployment. No automatic retries/fallbacks or response execution. The dashboard should show these as ordinary real collected alerts, with simulation ground truth kept separately for review—not a synthetic-case score masquerading as a live SOC.
