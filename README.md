# Corvus

An alert investigation service. Corvus connects security detections to supporting evidence, investigation history, and advisory triage. Wazuh is the first security backend.

## Status

**Working:** authenticated Wazuh onboarding, checkpointed alert ingestion, filtering/pagination, sync health, and source inspection. Manual investigations add bounded evidence collection, explicit per-bundle external-processing approval, one Analyst request, validated advisory reports, citations, durable attempt history, and evidence-bound human review with rationale and preserved decisions. Operational queues, rejected-candidate diagnostics, private Markdown/ZIP handoffs, and scheduled encrypted snapshots with isolated restore verification complete the Analyst-first slice. See [prototype scope](docs/prototype.md), [manual triage](docs/manual-triage.md), and [deployment](docs/deployment.md).

**Manual by default:** ingestion alone never queues model requests. Automatic Analyst triage is opt-in per connection, with separate external-processing consent, severity eligibility, and rolling request budgets. It excludes historical backlogs and never retries failed calls. Assessment review is recorded separately; incident resolution and response execution are not implemented.

**Local agents:** Correlation narrows new Analyst input to a few matched events, and Intel inspects structured indicators locally without network/reputation lookups. Focused input defaults to 4 supporting events / 16 KiB; broadening requires an explicit pre-approval choice. See [local agents](docs/local-agents.md).

**Target architecture:** autonomous correlation, investigation, intel, policy-gated containment, and independent verification share a case/evidence record. LangGraph runs the single-pass Analyst workflow; multi-agent handoffs, autonomous enrichment roles, and response agents are not active yet. See [architecture](docs/architecture.md).

The earlier saved-artifact dashboard has been retired. Synthetic fixtures remain development tests, not product data. There is no response executor or autonomous investigation loop.

## Development

Requires Python 3.11+. Install dependencies and run checks on the authorized development VM after syncing committed source; the local checkout is for source editing. See [CONTRIBUTING.md](CONTRIBUTING.md).

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[server,dev]'
.venv/bin/corvus --help

.venv/bin/python -m unittest discover -s tests -v
.venv/bin/ruff check src tests infra evaluations
.venv/bin/ruff format --check src tests infra evaluations
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
  agents/analyst/  Analyst prompt, bounded context selection, LangGraph workflow
  server/         Authenticated API, connections, ingestion, worker
    investigations/ Durable manual triage state and analysis runtime
    migrations/   Ordered PostgreSQL schema upgrades
  evidence.py     Backend-independent evidence collection
  cli.py          Local collection and analysis commands
web/              Next.js landing page and SOC interface
compose.yaml      Application deployment (web, API, worker, PostgreSQL)
infra/            Docker images, proxy configuration, lab helpers
tests/            Regression and boundary tests
evaluations/      Offline synthetic fixtures and scoring
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for module boundaries, tests, and the development workflow.

## GitHub workflow

Edit locally, commit, and push to GitHub. Pull the same source to the authorized VM, run checks there, and deploy only after they pass. The VPS checkout is `/opt/corvus/app`:

```bash
ssh wazuh 'git -C /opt/corvus/app pull --ff-only'
```

Do not edit application code separately on the VPS or copy it there with rsync. Secrets and runtime data stay outside the checkout. Pulling code does not deploy or restart services. Build and update containers with the committed Compose file; see the [deployment guide](docs/deployment.md).

## Boundaries

- Collection is read-only. Model recommendations are not executable actions.
- Failed, partial, or missing evidence must remain visible.
- Logs are untrusted data, never instructions.
- Citation validation does not establish that a claim is true. Reports require human review.
- Real evidence stays local unless external processing is explicitly approved per manual attempt or through a bounded connection-level automatic policy.

## Documentation

- [First prototype scope and operator path](docs/prototype.md)
- [Deployment](docs/deployment.md)
- [Encrypted backups and recovery](docs/operations.md)
- [Architecture](docs/architecture.md)
- [Collector setup and CLI](docs/read-only-cli.md)
- [Manual investigations and approval](docs/manual-triage.md)
- [Analyst configuration and report validation](docs/investigation-reports.md)
- [Human assessment review](docs/report-review.md)
- [Focused context, Correlation, and Intel](docs/local-agents.md)
- [Wazuh lab operations](docs/lab-setup.md)
- [Archive collection and retention](docs/telemetry-archives.md)
- [Windows simulation plan](docs/windows-simulation-plan.md)
- [Offline regression cases](evaluations/README.md)
