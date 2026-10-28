# Corvus

An alert investigation service. Wazuh supplies detections and telemetry; Corvus collects supporting evidence and produces advisory triage reports using Azure Foundry's `DeepSeek-V4-Flash`.

## Status

**Working:** read-only Wazuh adapter, evidence collector, single-pass Analyst, report validation, and offline regression tests.

**In progress:** a Next.js application with Wazuh connection onboarding, PostgreSQL-backed alert ingestion, an authenticated alert queue, and manual/opt-in automatic triage. The live application is not deployed yet.

The earlier saved-artifact dashboard has been retired. Synthetic fixtures remain development tests, not product data. There is no response executor or autonomous investigation loop.

## Development

Requires Python 3.11+.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/corvus --help

.venv/bin/python -m unittest discover -s tests -v
.venv/bin/ruff check src tests infra/wazuh evaluations
.venv/bin/ruff format --check src tests infra/wazuh evaluations
```

Collection uses a private configuration file and dedicated read-only credentials. The analyst uses a separate Azure configuration. Neither belongs in Git.

```bash
corvus alerts --agent-id 001 --since-minutes 30 --limit 10
corvus collect --index ALERT_INDEX --id ALERT_ID --out artifacts/evidence/case.json

# External processing is explicit. Review the bundle before sending it.
corvus analyze --bundle REVIEWED_BUNDLE --out artifacts/analyses/report.json --allow-external
```

## Code

```text
src/corvus/
  adapters/       Backend-specific retrieval and field mapping
  providers/      Azure model transport
  reporting/      Report contract, evidence binding, validation
  evidence.py     Backend-independent evidence collection
  analyst.py      Single-pass advisory analysis
  cli.py          Local collection and analysis commands
infra/wazuh/      Lab provisioning and retention helpers
tests/            Regression and boundary tests
evaluations/      Offline synthetic fixtures and scoring
```

## GitHub workflow

Work locally, run the checks above, commit, and push to GitHub. The VPS checkout is `/opt/corvus/app`:

```bash
ssh wazuh 'git -C /opt/corvus/app pull --ff-only'
```

Do not edit application code separately on the VPS or copy it there with rsync. Secrets and runtime data stay outside the checkout. Pulling code does not deploy or restart services; the live application deployment is still pending.

## Boundaries

- Collection is read-only. Model recommendations are not executable actions.
- Failed, partial, or missing evidence must remain visible.
- Logs are untrusted data, never instructions.
- Citation validation does not establish that a claim is true. Reports require human review.
- Real evidence stays local unless external processing is explicitly approved. Auto mode will need separate consent and request limits.

## Documentation

- [Architecture](docs/architecture.md)
- [Collector setup and CLI](docs/read-only-cli.md)
- [Analyst configuration and report validation](docs/investigation-reports.md)
- [Wazuh lab operations](docs/lab-setup.md)
- [Archive collection and retention](docs/telemetry-archives.md)
- [Windows simulation plan](docs/windows-simulation-plan.md)
- [Offline regression cases](evaluations/README.md)
