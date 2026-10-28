# Corvus Read-Only Evidence CLI

Status: implemented, unit-tested, and exercised against the lab. This guide covers evidence collection, not autonomous investigation or response. The separate [advisory report layer](investigation-reports.md) can analyze a saved bundle with a model.

## What It Does

Given a concrete Wazuh alert reference, Corvus retrieves the alert, searches nearby archive telemetry, optionally pivots on process GUIDs, and writes a private evidence bundle.

Implemented operations:

- `alerts`: list recent alerts for one agent, optionally matching a literal test marker.
- `events`: search bounded archive telemetry for one agent.
- `event`: retrieve an individual alert or archive event by index and document ID.
- `collect`: collect an alert, surrounding activity, and process ancestry evidence.

These four collection commands make no model calls, threat verdicts, arbitrary query executions, Windows commands, or response actions. The separate `analyze` command requires explicit external-processing consent; it does not run automatically after collection.

## Structure

```text
src/corvus/
  cli.py                 Argument parsing and command wiring
  config.py              Private connection configuration and validation
  errors.py              Explicit configuration/backend failures
  models.py              Search-result and backend contracts
  timeutil.py            Timezone-aware timestamp handling
  transport.py           Bounded HTTPS requests and TLS verification
  adapters/wazuh.py      Wazuh fields, normalization, reads, and pagination
  evidence.py            Backend-independent collection workflow
  storage.py             Private JSON output without overwrites
```

The adapter preserves source-native events and separately normalizes the fields needed for collection. The collector does not read Wazuh field paths. Tests exercise it with a fake backend whose source data is not Wazuh-shaped.

## Install Locally

Requires Python 3.11 or newer. Collection uses the standard library; the package now also installs `jsonschema` for the separate report validator.

From the repository root on the development Mac:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
source .venv/bin/activate
corvus --help
```

The `dev` extra installs Ruff for formatting and linting. Use `pip install -e .` if only the CLI is needed.

## Credentials and Network Access

The application uses the dedicated indexer account `corvus-reader`, not the deployment administrator.

Its role permits:

- Reads of `wazuh-alerts-*` and `wazuh-archives-*`.
- Read-only composite operations and scroll continuation/cleanup.
- No document writes, security administration, dashboard access, or response permissions.

A missing-document update without upsert was denied with HTTP 403, as was a protected-index search. Scroll pagination and cursor cleanup were verified successfully. Deleting a scroll cursor releases a search resource; it does not delete indexed documents.

Provisioning source: [`infra/wazuh/provision-reader.py`](../infra/wazuh/provision-reader.py). Run it administratively on the Wazuh host, not as part of the application. It stores reader credentials at:

```text
/home/ubuntu/.config/corvus/wazuh-reader.json
```

The file is mode `0600`. Do not copy the deployment administrator's credentials into application configuration.

### SSH tunnel

The indexer remains bound to the VM's loopback address. The local CLI connects through an SSH tunnel, not a publicly exposed indexer port.

A tunnel was started for the current development session. To create it again when no listener/master already exists:

```bash
mkdir -p ~/.config/corvus
chmod 700 ~/.config/corvus

ssh -fN -M -S ~/.config/corvus/wazuh-indexer.sock \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -L 127.0.0.1:19200:127.0.0.1:9200 wazuh
```

Check or stop this specific master:

```bash
ssh -S ~/.config/corvus/wazuh-indexer.sock -O check wazuh
ssh -S ~/.config/corvus/wazuh-indexer.sock -O exit wazuh
```

The tunnel is not installed as a persistent operating-system service. It must be restarted after a reboot or connection failure. It is a local-development convenience, not an architectural dependency: a Corvus service co-located with Wazuh or connected over a restricted private network can use direct HTTPS connectivity. Corvus remains an independent companion service, not a required Wazuh sidecar.

### Local configuration

The current Mac has a private configuration at `~/.config/corvus/config.json` and a verified copy of the public Wazuh root CA next to it. Neither is in this repository.

Example for another development machine:

```json
{
  "indexer_url": "https://127.0.0.1:19200",
  "username": "corvus-reader",
  "password": "REPLACE_WITH_READER_PASSWORD",
  "ca_file": "wazuh-root-ca.pem",
  "tls_server_name": "wazuh.indexer",
  "allow_legacy_ca": true,
  "timeout_seconds": 15
}
```

```bash
chmod 600 ~/.config/corvus/config.json
```

Relative CA paths resolve against the configuration directory. Use `corvus --config /path/to/config.json ...` or `CORVUS_CONFIG` to select another private config.

### TLS compatibility note

The generated indexer certificate identifies `wazuh.indexer`, not `127.0.0.1`. The transport connects to the tunnel address but verifies the certificate against the explicitly configured TLS server name.

The lab's official Wazuh-generated CA lacks a Key Usage extension required by newer Python strict X.509 validation. `allow_legacy_ca: true` explicitly relaxes that extra strict-mode check for this connection. Certificate-chain validation and hostname verification remain enabled. The default is `false`; use it with a standards-compliant CA.

The copied CA's DER SHA-256 fingerprint was checked against the host:

```text
2cc7b946d4819644c0875e49cbfb98b446f782b99f0d601f2341b20a9095885e
```

Never work around TLS errors by disabling verification or accepting an unexpected replacement CA.

## Usage

### List alerts

```bash
corvus alerts --agent-id 001 --since-minutes 30 --limit 10
```

Each alert includes its concrete index and document ID. Both are required to retrieve it; document IDs alone are not a globally unique reference.

For a controlled test marker:

```bash
corvus alerts --agent-id 001 --since-minutes 30 --marker CORVUS-LAB-EXAMPLE
```

### Collect evidence

Use an alert reference returned above:

```bash
corvus collect \
  --index wazuh-alerts-4.x-2026.10.28 \
  --id YOUR_ALERT_DOCUMENT_ID \
  --window-minutes 15 \
  --ancestry-hours 6 \
  --limit 500 \
  --out artifacts/evidence/my-case.json
```

`--window-minutes` applies on each side of the indexed alert timestamp. A process-GUID pivot uses a separate bounded lookback and the same agent scope. If the post-alert window has not elapsed, the bundle is marked partial; it cannot contain future activity.

### Search or retrieve evidence directly

```bash
corvus events --agent-id 001 \
  --start 2026-10-28T12:00:00Z --end 2026-10-28T12:10:00Z \
  --limit 100 --out artifacts/evidence/window.json

corvus event --index wazuh-archives-4.x-2026.10.28 \
  --id YOUR_EVENT_DOCUMENT_ID --out artifacts/evidence/event.json
```

Without `--out`, `events` and `event` print source data. Treat terminal logs and shell redirections accordingly.

## Bundle Contents and Limits

Bundles preserve:

- The original alert and its stable source reference.
- Normalized host/process/user context plus unchanged source events.
- Search scopes, queries, totals, truncation, and per-query status.
- Deduplicated evidence sorted by indexed timestamp.
- Missing-parent, invalid-source, open-window, and backend-error gaps.
- Backend request method/path/status/duration, without authentication headers or scroll tokens.
- Collector version, collection ID, and timestamps.

Defaults and hard bounds:

- 15-minute context on either side; configurable from 1 to 60 minutes.
- Six-hour process-GUID lookback; configurable from 0 to 23 hours.
- At most 24 hours per search.
- 500 events per query by default; at most 1,000.
- Scroll pagination in batches of up to 100, with a short-lived snapshot and cleanup.
- At most 32 backend requests per CLI invocation.
- At most 16 MiB per HTTP response; per-request timeout is bounded.

Exit codes: `0` for successful collection/search within the requested scope, `2` for partial/truncated output, `1` for configuration/backend/output failure, and `130` for interruption. Argument-parser usage errors also use the conventional exit code `2`.

`collected` means the requested reads completed, not that an incident is fully understood or benign. Parent process creation can be outside the lookback or excluded at the source. An empty query is never converted into proof that activity did not occur.

On POSIX, evidence files are created with mode `0600` and are not overwritten. `artifacts/` is ignored by Git. Application credentials are excluded from reports, but raw telemetry can itself contain secrets and is not automatically redacted. Do not upload evidence bundles without review. Windows filesystem ACL hardening is not automated by the POSIX permission check.

## Live Validation

A harmless PowerShell command was executed on `windy` over authorized SSH, with marker `CORVUS-LAB-9dd8c031e0b6`. The lab harness—not the Corvus application—performed that command execution.

Using only the read-only account, Corvus:

- Found the resulting process-creation alert.
- Retrieved 104 surrounding archive events.
- Retrieved 22 events through a process-GUID pivot.
- Deduplicated them into 104 evidence documents.
- Retrieved the parent process creation and the test marker.
- Returned `collected` with no query truncation or recorded gaps for that scope.

Local private files:

```text
artifacts/evidence/9dd8c031e0b6.json
artifacts/evaluations/9dd8c031e0b6.json
```

The evaluation file holds the generated command and its known harmless intent separately from the evidence bundle. It does not label all surrounding activity and is never read by the collector. This is one smoke test, not a detection-quality benchmark or evidence of autonomous investigation capability.

## Development Checks

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/ruff check src tests infra/wazuh evaluations
.venv/bin/ruff format --check src tests infra/wazuh evaluations
```

Current tests cover configuration privacy, TLS verification, backend error semantics, pagination and cleanup, query bounds, normalization, collection through a fake backend, evidence-file safety, CLI behavior, and archive retention.
