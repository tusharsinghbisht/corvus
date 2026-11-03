# Architecture

Corvus is an independent alert investigation service. Wazuh is its first backend, not a lifecycle dependency or a custom SIEM to fork.

## Working today

```text
CLI → evidence collector → Wazuh adapter → indexer (read-only)
           ↓
     private evidence bundle
           ↓
     Analyst → model-provider interface → configured model
           ↓
     report validation → preserved advisory report
```

Source documents and exact references are retained alongside normalized fields. Queries are bounded; errors, truncation, and unavailable context remain explicit. The model has no tools. Provider and model selection are runtime concerns, separate from Corvus's application stack and feature set. The current CLI wires one provider adapter; additional adapters can implement the same Analyst interface. Validation checks structure, evidence binding, citations, and basic recommendation safety—not narrative entailment.

The local artifact dashboard has been retired. Regression fixtures remain offline tests.

## Live application

```text
Browser → Caddy HTTPS → Next.js
                         ↓
                    Python API → PostgreSQL
                                      ↑
                               Python worker
                                      ↓
                                Wazuh adapter
```

- **Next.js:** public landing page and authenticated SOC interface. No credentials or model calls in browser code.
- **Python API:** authenticated connection onboarding, alert queries, source inspection, sessions, manual investigation/approval routes, and evidence-bound human assessment review. No model credentials or calls.
- **Worker:** checkpointed alert ingestion plus an independent manual-triage consumer using the existing collector and Analyst. Only per-attempt manual consent or a separately consented, bounded automatic policy can authorize model calls.
- **PostgreSQL:** normalized alerts plus original JSONB, connections, sessions, audit events, investigation jobs/attempts, saved evidence, candidate reports, provenance, and append-only human assessment reviews. Wazuh retains high-volume telemetry; Corvus does not mirror its archives.
- **Docker Compose:** separate application services and persistent database volume. Existing Caddy provides HTTPS at `corvus.0xbenzo.dev`. No public database/indexer ports, Docker socket, or root application access.

The application covers connection → ingestion → alert inspection → bounded collection → explicit approval → one Analyst request → preserved advisory report. See [manual triage](manual-triage.md) for durable state/recovery and the [deployment guide](deployment.md) for Docker operations and current limits.

## Target multi-agent workflow

```text
Alert intake → Correlation ↔ Analyst → Policy / human approval → Containment → Verification
                               ↕                                               |
                             Intel                    outcome evidence → Analyst / case

                  Shared case, evidence references, tasks, and audit history
```

**LangGraph runs the single-pass Analyst today.** Agent-specific code lives in `src/corvus/agents/analyst/`: bounded context selection, versioned instructions, and prepare → one request → validate graph nodes. The graph has no retry policy or checkpointer; external tracing is disabled. PostgreSQL owns durable attempts, consent, request budgets, and recovery. Multi-agent handoffs, shared case orchestration, and response agents remain planned. A framework checkpoint would not guarantee exactly-once model calls or response execution.

| Role | Responsibility and handoff | Current state |
| --- | --- | --- |
| Alert intake | Preserve detections and native identity; make alerts available for investigation | Live |
| Correlation agent | Propose related alert/evidence sets; respond to scoped Analyst requests | Planned |
| Analyst agent | Own the investigation, request scoped enrichment, and produce an evidence-linked assessment | Single-pass LangGraph workflow, manual/policy-gated triage, and human assessment review; multi-agent handoffs planned |
| Intel agent | Return sourced, time-aware indicator/behavior context to the Analyst | Planned |
| Policy / approval | Validate the exact action and target; require authorization outside the models | Planned; this is code/human authority, not another agent |
| Containment agent | Execute only an approved, scoped plan with separate response credentials | Planned |
| Verification agent | Check fresh post-action evidence independently; return success, failure, or unknown outcome | Planned |

Agent handoffs are structured tasks bound to a case and evidence references, not unrestricted commands between models. Findings, requested capabilities, tool outcomes, approvals, and budgets belong to the shared investigation record. PostgreSQL stores alerts, connections, sessions, audit events, and manual investigation attempts; shared case/task orchestration is not implemented yet.

The Analyst can request correlation or intel work without granting either role response authority. Containment cannot bypass policy, and an executor acknowledgment is not proof of containment. Verification returns outcome evidence to the case and Analyst; follow-up actions and rollback still require authorization. Automatic triage never implies automatic containment.

## Storage

Use PostgreSQL first. Transactions, uniqueness constraints, job state, indexed filtering, time buckets, and percentiles cover the current workload. DuckDB is an option for later offline analysis. ClickHouse needs measured analytical scale to justify another datastore; it is not needed now.

Alert identity is `(connection, native index, native document ID)`. Keep indexed/source time separate from Corvus receipt time. Preserve triage attempts rather than overwriting them. Host-only encrypted snapshots with isolated restore verification protect the prototype; off-host copies and live source-data retention remain operator responsibilities. See [backup/recovery](operations.md) and [completed prototype scope](prototype.md). Do not treat local snapshots as full disaster recovery.

## Ingestion

Poll `wazuh-alerts-*` across all agents and severities using dedicated reader credentials and verified TLS. Start from an explicit backfill boundary, use overlapping bounded windows, and deduplicate inserts. Advance the checkpoint only after a complete window is committed. Split oversized windows; show a blocked checkpoint instead of silently dropping excess results.

Timestamp polling has a bounded late-arrival horizon; it cannot guarantee capture of arbitrarily backdated documents. Show sync health and lag. Do not modify Wazuh detections just to make a demonstration pass.

## Analyst modes

The manual Analyst pipeline is deterministic: queue → bounded evidence collection → inspect/approve saved input → one model request → validation → preserved candidate requiring human review. [Human assessment review](report-review.md) records acceptance, rejection, or follow-up against the exact report/evidence. It is not incident resolution or response authorization.

- **Manual is the default.** Each request explicitly acknowledges external evidence processing.
- **Auto is opt-in per connection.** Separate external-processing consent, medium+/high+/critical eligibility, rolling connection/global budgets, and a fresh activation boundary are required. Only new 5–15-minute-old alerts qualify; historical backlogs and previously investigated alerts are excluded. See [Analyst policies and context](analyst-policies.md).
- Permit one active job per alert. Preserve failures and retries as separate attempts.
- Allow a short post-alert collection window. Partial evidence cannot become benign clearance.
- Do not automatically retry a model call after a crash or ambiguous timeout; it may already have been billed.
- Model completion is not incident resolution. Recommendations do not authorize containment.

## Security

Authenticate every data API. Use Argon2 passwords, expiring server-side sessions, secure HttpOnly same-site cookies, mutation-origin checks, and login throttling. Connection onboarding accepts only operator-allowlisted indexer destinations and an installed CA, not arbitrary URLs. Encrypt stored reader passwords with a server-held key.

Model-provider credentials belong only to the analysis runtime. No secrets in frontend variables or logs. Evidence selection is not PII redaction. The landing page may be public; alert data must not be exposed before authentication and HTTPS are verified.

## Initial metrics

Use real alert volume, severity/agent distribution, ingestion lag, queue depth/age, triage duration, failed/rejected attempts, and explicitly labeled model dispositions. Human-review metrics need recorded reviewer actions. MTTD needs a defensible attack-start timestamp; MTTR needs an actual response lifecycle. Do not fabricate them from model completion times.

## Lab verification

Use only the reviewed Atomic Red Team procedures in the [Windows simulation plan](windows-simulation-plan.md). Verify command execution, telemetry collection, native detection, ingestion, and Analyst reasoning separately. A safe emulation payload is not proof of a malicious compromise.

Operational details: [lab setup](lab-setup.md), [archives](telemetry-archives.md), [collector](read-only-cli.md), and [reports](investigation-reports.md).
