# Contributing

Corvus is an independent SOC investigation platform. Keep changes operational, understandable, and bounded. Wazuh is the first backend, not the product boundary.

## Repository layout

| Directory | Responsibility |
| --- | --- |
| `src/corvus/adapters/` | Backend retrieval and normalization |
| `src/corvus/providers/` | Replaceable model transports and private configuration |
| `src/corvus/reporting/` | Evidence selection, report contract, validation |
| `src/corvus/server/` | API, authentication, database, connections, ingestion |
| `src/corvus/server/investigations/` | Durable manual investigation state and worker runtime |
| `src/corvus/server/migrations/` | Ordered, transactional PostgreSQL upgrades |
| `web/app/` | Next.js routes and layouts |
| `web/components/`, `web/lib/` | Interface components and typed API contracts |
| `tests/`, `web/tests/` | Python regression/integration tests and browser tests |
| `evaluations/` | Offline synthetic regression data, never product data |
| `infra/` | Deployment images, proxy configuration, operational helpers |
| `docs/` | Architecture, operator workflows, deployment, integration setup |

Keep collection, analysis, and response authority separate. Reuse the existing collector, Analyst interface, and validator rather than adding agent-framework abstractions. Provider/model identities belong in integration configuration and run provenance, not product copy.

## Checks

Python 3.11+ and Node.js are required. Use a virtual environment and the existing lockfile; do not add system services or dependencies without agreement.

```bash
.venv/bin/python -m pip install -e '.[server,dev]'
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/ruff check src tests infra evaluations
.venv/bin/ruff format --check src tests infra evaluations

cd web
npm ci
npm run check
npm run build
npm test -- --project ui
```

Read `web/AGENTS.md` and the installed Next.js guides before editing frontend code. Run build and browser tests sequentially because both write `.next`.

Database tests require `CORVUS_TEST_DATABASE_URL` pointing to a **disposable** PostgreSQL database, never the live database. Use the authorized VM for database services; do not install PostgreSQL locally. Tests create/drop isolated schemas. The workspace browser suite (`npm test -- --project workspace`) uses that variable and starts isolated API/web services. Models and evidence retrieval in these tests are offline fakes; tests must not make billable calls or send real evidence externally.

## Change and deployment workflow

1. Make focused local changes, add boundary/failure-path tests, and update relevant operational docs.
2. Review `git diff` and stage specific paths. Do not include unrelated local edits.
3. Commit and push to GitHub, the source of truth.
4. Pull into `/opt/corvus/app` with `git pull --ff-only`. Run VM checks from this checkout, not a separate application-code copy.
5. Back up the database and configuration before schema changes. Build/update the affected Compose services and verify health. See [deployment](docs/deployment.md).

Secrets, live evidence, model outputs, and runtime state stay outside Git. Never print credentials, bypass per-request external-processing consent, automatically retry an ambiguous model call, expose database/indexer ports publicly, or use `docker compose down -v`.
