# Advisory investigation reports

The Analyst produces a single-pass, read-only report from a saved evidence bundle. It cannot request more evidence, run endpoint commands, or execute recommendations. Provider and model selection are runtime configuration, not platform features.

## Workflow

```text
Saved evidence → selected input → Analyst → model-provider interface
                                     ↓
                              candidate report
                                     ↓
                         schema and integrity checks
                                     ↓
                          private analysis artifact
```

- `analyst.py` prepares input and invokes the `AnalystModel` interface once.
- `providers/` contains provider-specific transport and configuration adapters.
- `reporting/schema.py` defines the report contract.
- `reporting/evidence.py` selects evidence, resolves references, and computes its digest.
- `reporting/validation.py` checks structure, bindings, references, and recommendation safety.
- `evaluation.py` scores offline regression cases; it makes no model calls.

The CLI and manual-triage worker currently wire one provider adapter. Its endpoint, credential file, deployment identifier, and transport limits are documented in the [adapter setup guide](providers/azure-foundry.md). Other providers require an adapter and selection wiring; a provider-selection UI is not implemented.

## Commands

Prepare and inspect input without credentials or network access:

```bash
corvus report-schema --out artifacts/reports/schema.json
corvus prepare-report --bundle REVIEWED_BUNDLE --out artifacts/reports/prepared.json
```

Preparation excludes connection settings, transport audit data, unknown top-level metadata, and evaluator expectations. **It is not a telemetry redactor:** source logs can still contain secrets or personal data.

Generate one report after explicitly approving external processing:

```bash
corvus analyze --bundle REVIEWED_BUNDLE \
  --out artifacts/analyses/my-run/report.json --allow-external
```

Without `--allow-external`, the command stops before loading model credentials or making a request. Review live evidence before approving transfer. Changing a model or provider must not bypass that decision.

Output preserves the candidate, validation result/version, analysis ID, prompt version, evidence digest, actual served model, token usage, timing, and human-review requirement. Invalid output is retained as rejected rather than silently repaired. Provider failures remain operational errors, not invented inconclusive reports.

CLI files are private, exclusive, and never overwritten. Existing output is checked before a billable request. This CLI is not a durable job system; failure between a completed request and saving its response remains possible.

The live application adds [durable manual investigations](manual-triage.md): saved bounded evidence, exact-digest approval, one request per attempt, preserved replies before validation, and attempt history. Interrupted/ambiguous model requests become unknown and require an explicit new attempt; they are not automatically retried. Model credentials are worker-only.

Revalidate a saved candidate against its exact evidence:

```bash
corvus validate-report --bundle REVIEWED_BUNDLE --report SAVED_REPORT
```

Stored validation describes generation-time checks. It is not a substitute for revalidation after the validator changes.

Exit codes: `0` completed/passed; `2` rejected or evaluation failed; `1` operational error; `130` interrupted. Parser usage errors also return `2`.

## Report contract

Reports contain:

- `malicious`, `likely_benign`, or `inconclusive` disposition, scoped to the supplied evidence.
- A summary linked to finding IDs, separating observations from inferences.
- Timeline, entities, alternative explanations, uncertainties, recommendations, and limitations.
- Exact evidence references and `response_executed: false`.

Event citations retain their complete backend/index/document identity. Collection facts cite allowlisted metadata paths: `/status`, `/scope`, `/queries`, `/gaps`, `/limitations`, or existing numbered list entries. An alert cannot stand in for a query-error record. Timeline times must match a cited normalized indexed timestamp, not an inferred original event time.

Validation checks schema, collection/digest binding, reference existence, finding links, and these conservative rules:

- Every collection gap must be acknowledged.
- Inconclusive and partial evidence require uncertainty.
- Partial collection cannot support benign clearance; affirmative evidence can still support malicious activity with acknowledged gaps.
- A definitive disposition needs an inference linked from the summary.
- Containment/remediation review recommendations require a malicious disposition. Uncertainty alone is insufficient.

These are report-integrity gates, **not action authorization**. A digest is not a signature or proof of source authenticity. A correct reference does not prove a claim follows from the evidence. All reports require human review.

## Regression checks and known limits

The [offline cases](../evaluations/README.md) exercise legitimate lookalikes, suspicious activity, failed collection, missing ancestry, and instructions embedded in evidence. They are simplified synthetic tests, not live captures or a real-world accuracy benchmark. Evaluator expectations and authored reference reports are not supplied to the Analyst.

```bash
corvus evaluate --suite evaluations/suite.json --reports evaluations/reference-reports
corvus evaluate --suite evaluations/suite.json --reports artifacts/analyses/my-run
```

The historical three-case model batch matched all disposition labels but passed only **2/3 automated cases**: an inconclusive report recommended unsupported containment. The current gate rejects that recommendation. Review also found PID/GUID confusion, overconfident timing, and unsupported destination reputation claims despite valid references. Automated passes are not semantic approval or independent human acceptance.

Historical model testing used synthetic input only; no live Windows bundle was uploaded. Failed candidates and original inputs remain in private artifacts. Prompt changes have not been shown to eliminate these reasoning failures.

Current limits: one model call per approved attempt, no investigative tool loop, no response executor, no automatic redaction, and no recorded human-review lifecycle. Durable jobs are available in the live application, not the CLI. JSON inputs cap at 16 MiB; evidence catalogs cap at 5,000 documents plus the alert. Duplicate JSON keys and non-standard numeric values are rejected. Provider-specific request/token limits belong to the selected adapter.
