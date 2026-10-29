# Live application deployment

The application runs in Docker Compose on the Wazuh VM. GitHub is the source of truth; `/opt/corvus/app` is the VPS checkout. Do not edit a second application copy there.

## Services

- `web`: Next.js landing page, login, alert queue, source inspection, connection setup, and per-alert investigations.
- `api`: authenticated FastAPI data, manual collection, and explicit approval endpoints. No model credentials.
- `worker`: polls Wazuh and independently consumes manual investigations. Only an explicitly approved attempt can invoke the Analyst; no automatic triage or response execution.
- `db`: PostgreSQL 17 with a persistent `corvus_database` volume.

Only the existing Caddy proxy exposes HTTPS. Application services publish no host ports. PostgreSQL is on an internal network; web/API/worker join the existing Wazuh network for routing. The application has no Docker socket or mounted Wazuh internals. Application processes run as UID 10001 with read-only filesystems and bounded memory/CPU/logs.

## First deployment

From the VPS checkout:

```bash
git pull --ff-only
sudo python3 infra/provision-app.py
export CORVUS_REVISION="$(git rev-parse --short=12 HEAD)"
docker compose --env-file ~/.config/corvus/app/deploy.env build api web
docker compose --env-file ~/.config/corvus/app/deploy.env up -d --wait
```

The provisioner verifies the pinned Wazuh CA and creates private configuration under `~ubuntu/.config/corvus/app/`. It refuses to replace existing secrets. Reader credentials are entered through the connection form and encrypted in PostgreSQL with a separate server-held key. Model integration is installed separately, worker-only, as described below.

Add the versioned `infra/caddy/corvus.caddy` site block to the existing `/opt/wazuh-docker/single-node/Caddyfile`, preserving the Wazuh site. Back up the original first; validate with `caddy validate --config /etc/caddy/Caddyfile` inside the Caddy container before reloading it. Do not restart or recreate the Wazuh stack just to deploy Corvus. DNS for `corvus.0xbenzo.dev` must point to the VM and public port 443 must be reachable for HTTPS issuance.

Retrieve browser credentials **in your own private terminal**, not in chat or logs:

```bash
ssh wazuh 'python3 -m json.tool ~/.config/corvus/app/login.json'
```

Open `https://corvus.0xbenzo.dev`. Use Connections to onboard `https://wazuh.indexer:9200` with the existing dedicated `corvus-reader` account. Its private credentials are in `~ubuntu/.config/corvus/wazuh-reader.json`. Never use the indexer administrator account.

## Manual Analyst configuration

The base Compose deployment can collect and preserve evidence without model credentials. Install the selected integration's private configuration as `~ubuntu/.config/corvus/app/analyst.json`, owned by container UID/GID `10001:10001` with mode `0600`. Use the [adapter setup guide](providers/azure-foundry.md) for its contents; never print the key or commit this file.

Enable the optional override for **every subsequent Compose command**, including rebuilds and updates:

```bash
export COMPOSE_FILE=compose.yaml:compose.analyst.yaml
```

Persist `COMPOSE_FILE=compose.yaml:compose.analyst.yaml` in the private `deploy.env` so the normal `--env-file` workflow continues to include it. The override adds the model configuration mount only to `worker`; `api` and `web` must not receive it. The worker records the configured integration and actual served identity in attempt provenance, never the credential. Missing/invalid configuration fails the attempt before any model request. No fallback is configured.

Opening an alert and collecting evidence does not send it externally. The operator must inspect the saved input and approve that exact digest for one request. Deploying credentials, enabling ingestion, or restarting the worker does not create triage jobs or process a historical backlog. See [manual triage](manual-triage.md) for states, cancellation, failures, and explicit retries.

Worker shutdown has a 210-second grace period for in-flight requests. A forced shutdown or crash after the durable request-start marker leaves an unknown outcome; the next consumer preserves it without retry. Even a request with no saved result may already have been billed.

## Ingestion behavior

- All agents and rule levels are included; no Windows-only filter.
- The initial backfill is an explicit 1–24 hour window, visible in connection details. This does not import all historical indices.
- Polling runs every five seconds; initial backfill can take several minutes. The browser refreshes every five seconds on the first page, without overlapping slow requests. Historical pages do not auto-refresh.
- Inserts deduplicate by connection/index/document ID. Keyset pagination handles equal timestamps.
- Five-minute query windows overlap by two minutes. Oversized windows split within a bounded request/document budget. Incomplete results and failed transactions do not advance checkpoints.
- Alerts arriving with timestamps older than the overlap horizon can be missed. Reconciliation outside that horizon is not implemented.
- Pausing retains data/checkpoints; resuming catches up from the last checkpoint. Sync errors and catch-up state remain visible.

## Authentication and limitations

A single operator account is bootstrapped with Argon2. Sessions are hashed in PostgreSQL, expire after 12 hours, and use Secure/HttpOnly/SameSite cookies over HTTPS. Mutation requests require an exact Origin. Ten failed logins in 15 minutes trigger a global pilot throttle. Connection destinations are operator-allowlisted; arbitrary URL/CA uploads are not exposed. Validation errors never echo passwords.

This is a single-operator pilot: no SSO/MFA, granular roles, password-rotation UI, recorded human-review workflow, automatic triage, or response executor. External-processing approval is per manual attempt, not standing connection-level consent. Source documents may contain personal data/secrets. Alert retention and scheduled encrypted backups are not yet configured; do not treat the persistent volume alone as a backup. Caddy's CSP allows inline scripts/styles for Next.js hydration; no untrusted HTML is rendered.

## Updates and checks

```bash
git status --short          # inspect unexpected VPS edits before pulling
git pull --ff-only
export CORVUS_REVISION="$(git rev-parse --short=12 HEAD)"
docker compose --env-file ~/.config/corvus/app/deploy.env build api web
docker compose --env-file ~/.config/corvus/app/deploy.env up -d --wait
docker compose --env-file ~/.config/corvus/app/deploy.env ps
```

Do not run `down -v`; it deletes the database. Back up PostgreSQL and the configuration/encryption key before schema-changing releases. Initialization applies ordered migrations under a database advisory lock. Schema version 2 adds manual investigation jobs/attempts without rewriting alerts; do not roll back application code to version-1-only initialization after upgrading. Audit events are in PostgreSQL; container logs intentionally omit source bodies and credentials.

## Local checks

```bash
.venv/bin/python -m pip install -e '.[server,dev]'
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/ruff check src tests infra evaluations
cd web
npm ci
npm run check
npm run build
```

Browser checks require `npx playwright install chromium`. Run `npm test -- --project ui` for public-page interactions, self-hosted fonts, responsive layout, and sidebar behavior; layout tests mock API responses only inside the browser.

PostgreSQL integration tests require `CORVUS_TEST_DATABASE_URL` pointing to a **disposable database**. They create/drop isolated schemas, not production data. With that variable set, `npm test -- --project workspace` starts isolated services on 8768/8769 and tests authentication, connection controls, and alert browsing against PostgreSQL. These integration cases are explicitly skipped without the database variable. Run build and browser tests sequentially because both use `.next`. Test records never enter the live application's database.
