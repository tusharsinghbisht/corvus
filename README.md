# Corvus

An alert investigation service. Corvus connects security detections to supporting evidence, investigation history, and advisory triage. Wazuh is the first security backend.

## Status

**Working:** authenticated Wazuh onboarding, checkpointed alert ingestion, filtering/pagination, sync health, and source inspection. Manual investigations add bounded evidence collection, explicit per-bundle external-processing approval, one Analyst request, validated advisory reports, citations, and durable attempt history. See [manual triage](docs/manual-triage.md) and [deployment](docs/deployment.md).

**Not automatic:** ingestion never queues model requests. Automatic triage, human-review lifecycle, and response execution are not implemented.

**Target architecture:** correlation, investigation, intel, policy-gated containment, and independent verification share a case/evidence record. LangGraph is planned for workflow orchestration; these additional agents are not active yet. See [architecture](docs/architecture.md).

The earlier saved-artifact dashboard has been retired. Synthetic fixtures remain development tests, not product data. There is no response executor or autonomous investigation loop.

## Development

Requires Python 3.11+.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[server,dev]'
.venv/bin/corvus --help

.venv/bin/python -m unittest discover -s tests -v
.venv/bin/ruff check src tests infra/wazuh evaluations
.venv/bin/ruff format --check src tests infra/wazuh evaluations
```

Collection uses a private configuration file and dedicated read-only credentials. The Analyst uses separate model-provider configuration. Neither belongs in Git.

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
  providers/      Model-provider interface and transport adapters
  reporting/      Report contract, evidence binding, validation
  server/         Authenticated API, connections, ingestion, worker
    investigations/ Durable manual triage state and analysis runtime
    migrations/   Ordered PostgreSQL schema upgrades
  evidence.py     Backend-independent evidence collection
  analyst.py      Single-pass advisory analysis
  cli.py          Local collection and analysis commands
web/              Next.js landing page and SOC interface
compose.yaml      Application deployment (web, API, worker, PostgreSQL)
infra/            Docker images, proxy configuration, lab helpers
tests/            Regression and boundary tests
evaluations/      Offline synthetic fixtures and scoring
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for module boundaries, tests, and the development workflow.

## GitHub workflow

Work locally, run the checks above, commit, and push to GitHub. The VPS checkout is `/opt/corvus/app`:

```bash
ssh wazuh 'git -C /opt/corvus/app pull --ff-only'
```

Do not edit application code separately on the VPS or copy it there with rsync. Secrets and runtime data stay outside the checkout. Pulling code does not deploy or restart services. Build and update containers with the committed Compose file; see the [deployment guide](docs/deployment.md).

## Boundaries

- Collection is read-only. Model recommendations are not executable actions.
- Failed, partial, or missing evidence must remain visible.
- Logs are untrusted data, never instructions.
- Citation validation does not establish that a claim is true. Reports require human review.
- Real evidence stays local unless external processing is explicitly approved. Auto mode will need separate consent and request limits.

## Documentation

- [Deployment and operations](docs/deployment.md)
- [Architecture](docs/architecture.md)
- [Collector setup and CLI](docs/read-only-cli.md)
- [Manual investigations and approval](docs/manual-triage.md)
- [Analyst configuration and report validation](docs/investigation-reports.md)
- [Wazuh lab operations](docs/lab-setup.md)
- [Archive collection and retention](docs/telemetry-archives.md)
- [Windows simulation plan](docs/windows-simulation-plan.md)
- [Offline regression cases](evaluations/README.md)
