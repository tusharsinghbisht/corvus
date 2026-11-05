# First prototype: Analyst investigation workspace

## Completed operational slice

One operator can connect a read-only Wazuh backend, inspect real ingested alerts, collect bounded evidence, inspect the exact selected input, explicitly approve one external Analyst request, read an integrity-checked advisory report, record evidence-bound human assessment review, and download a private handoff. Durable PostgreSQL attempt state preserves errors, original candidates, input snapshots, and billing ambiguity without automatic retries.

LangGraph executes the single-pass Analyst workflow. Local deterministic Correlation and Intel stages now support focused evidence preparation and indicator inspection; autonomous roles and handoffs remain planned. This is not a multi-agent SOC or response executor. See [local agents](local-agents.md).

### Operator path

1. **Connections:** onboard the allowlisted backend; inspect sync errors/checkpoints. Pausing ingestion retains evidence. No model processing is implied.
2. **Alerts:** combine time/severity/search/source filters with investigation queues. `Not investigated` has no previous attempt; `Active` has unfinished work; `Needs human review` is the latest validated report without a human decision; `Follow-up needed` and `Assessment reviewed` follow that report's latest decision. `Technical failures` follows the latest attempt's failed/rejected/unknown outcome. These views overlap intentionally: an older reviewed report can coexist with a newer failed attempt. Every queue respects the selected ingestion-time window; use the Analyst page for attempt-level review history beyond it.
3. **Investigate with Analyst:** collect read-only context and inspect selected facts, omissions, and the exact input snapshot. Selected indexed timestamps are canonicalized to RFC3339 without changing instants/fractional precision or original local source evidence. Approve one input digest or cancel. New requests may incur a charge. Automatic mode is a separate, opt-in bounded policy and remains off by default.
4. **Report:** read findings, citation-linked evidence, gaps, alternative hypotheses, and recommendations. Links prove citation membership, not entailment or causal/process ancestry. The latest validated report remains available even if a later attempt fails. Failed/rejected output is never promoted into findings; rejected candidates expose integrity diagnostics and the immutable technical record. The timestamp-format fix applies to newly selected inputs, not saved candidates/approved historical snapshots.
5. **Human review:** accept, reject, or request follow-up with rationale. Acceptance needs source/gap attestation and current integrity revalidation. Concurrent/stale decisions cannot silently overwrite history. Review never changes the model artifact, closes an incident, sends another request, or authorizes response.
6. **Private handoff:** expand `Download investigation handoff` on the exact attempt and acknowledge sensitivity. The Markdown summary includes generation status, advisory report when available, review history, and limitations. The ZIP preserves collected/selected evidence, input snapshot, candidate, provider reply/provenance, reviews, current local revalidation, and a SHA-256 manifest. Checksums detect changes; they are not a signed attestation of truth. Raw model/evidence JSON and source strings remain untrusted; do not execute commands or follow links from them. There is no public share link or additional model call. Downloads are audited and capped at 32 MiB/2,000 review records; protect them on the receiving machine.
7. **Settings:** inspect live heartbeat/configuration presence and encrypted backup/isolated restore status. Use the [operator runbook](operations.md) for scheduled snapshots and recovery. No host administrative command is exposed to the browser.

## Verification boundaries

Regression suites use disposable PostgreSQL, offline evidence, and fake model responses on the authorized VM. Browser checks exercise the real isolated API/database workflow, including approvals, failures, reviews, downloads, filters, responsive UI, and navigation. Backup verification uses a network-isolated restored copy of the actual database, not live writes or endpoint simulations. Production browser verification is read-only beyond login/logout. Existing real model artifacts remain preserved; shipping a prompt/context fix is not proof that a future response will complete or be correct.

## Deliberate prototype limits

- Single operator; no SSO/MFA, granular reviewer separation, or password-rotation UI.
- No incident-resolution lifecycle, assignments, response executor, containment, independent verification agent, or multi-agent handoffs.
- Model narrative quality is advisory and not broadly established; integrity checks and human acceptance are not proof of truth. Output limits/provider failures can still produce incomplete or rejected reports.
- No automatic repair, ambiguous-call retry, historical automatic backlog processing, or billing reconciliation.
- Local encrypted snapshots/verified database restores, but no managed off-host copy, continuous recovery/WAL archive, automated full-host failover, or source-data retention policy.
- No historical ingestion reconciliation beyond the overlap horizon.
- No Atomic Red Team simulations executed. Follow the separate pinned/reviewed Windows plan with explicit endpoint approval; installing this prototype does not approve a simulation.

This is an operational investigation prototype, not an unattended production SOC. Keep automation off until its independent consent, scope, and budgets are intentionally reviewed.
