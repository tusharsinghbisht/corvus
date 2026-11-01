# Analyst context and automatic policies

Manual investigation is the default. Enabling ingestion, installing model credentials, visiting Settings, or deploying this release never enables automatic evidence transfer. Configure each connection in **Settings → Automatic triage policy**. The alert's Analyst mode disclosure exposes the same connection policy; it is not a way to enroll a historical alert.

## Eligibility and consent

A separately acknowledged connection-level policy authorizes external processing of selected evidence. Choose minimum severity: medium+ (7–16), high+ (12–16, default), or critical (15–16). This is Wazuh's rule-level mapping, not a claim that severity proves compromise.

All of these conditions must hold:

- Connection ingestion and its automatic policy are enabled.
- Alert level meets the configured threshold.
- Both indexed timestamp and Corvus receipt time are on/after policy activation.
- Alert is at least five minutes old, allowing the bounded post-alert collection window to elapse, and no more than 15 minutes old.
- No previous investigation job exists for the alert. Failed, rejected, unknown, cancelled, or manually investigated alerts are not automatically retried.
- Per-connection rolling-hour and rolling-24-hour budgets and the global rolling-24-hour budget have room.

Every policy edit increments its version, establishes a fresh activation boundary when enabled, and cancels unstarted automatic work. Disabling ingestion/policy or expiring the 15-minute window prevents a queued request from starting. An in-flight request cannot be recalled. Manual per-alert requests remain separately available and require approval of their exact selected input.

## Budgets and recovery

Defaults are two automatic reservations per connection per rolling hour, ten per rolling 24 hours, and twenty globally per rolling 24 hours. These are request reservations, not guarantees of completed reports. Failed collection, configuration failures, and cancelled work still consume their reservation; edits and restarts do not reset usage. Manual requests are not counted against automatic budgets.

A database transaction lock serializes reservations and policy changes. The existing single-consumer advisory lock remains responsible for triage execution. Consent, eligibility, version, and current budgets are rechecked at the durable request-start boundary. Each automatic attempt retains its policy snapshot and the operator who authorized standing consent. No request, graph node, or ambiguous crash outcome is automatically retried.

## Bounded Analyst context

`src/corvus/agents/analyst/context.py` deterministically selects the input before approval or policy-authorized processing:

- Always retain the triggering alert and exact backend/index/document references.
- Prefer exact process GUID, parent creation, children/siblings, then indexed-time proximity. This selects context; it does not prove ancestry or causation.
- Include at most 24 supporting events and at most 64 KiB of selected evidence, including collection metadata. This is a byte budget, not an exact tokenizer count.
- Bound nesting, object fields, lists, and long source strings. Excerpts explicitly record omitted content; full local evidence is retained separately.
- Preserve normalized identifiers and indexed timestamps. Do not invent missing facts or perform model summarization of evidence before approval.
- Record selection version, original digest, selected/omitted event counts, excerpted-document count, and original size in collection scope.

If substantive content is omitted, the selected bundle is partial and records `analyst_context_reduced`. Existing validation requires acknowledging this gap and forbids benign clearance from partial evidence. Selection is **not redaction**. A smaller prompt does not guarantee correct reasoning or prevent sensitive data transfer; manual inspection or standing consent is still required.

The selected bundle is stored as `analysis_evidence`, alongside unmodified collected `evidence`. Approval, invocation, report validation, and citations bind to its exact digest. Old attempts without selected bundles continue to use their original evidence/digest; they are never retroactively rewritten.

## Agent boundaries and interface

The Analyst lives in `src/corvus/agents/analyst/`: `prompt.py`, `context.py`, and `workflow.py`. Its LangGraph is prepare input → one model request → validate candidate. It has no checkpointer, tool loop, automatic retry policy, or external tracing. PostgreSQL—not graph replay—owns jobs, approvals, budgets, and recovery. Shared provider transports and report contracts remain outside agent-specific folders. Other agents do not yet have implementations.

Alert pages default to the latest report that passed integrity checks, even if a newer attempt failed. Reports show findings, interpretation, alternative explanations, gaps, and advisory recommendations. The interactive evidence map connects a finding only to its actual report citations; edges mean “cited by”, not verified entailment or causality. Node inspection displays source facts, not a fabricated process/correlation graph. Raw records remain under technical disclosures.
