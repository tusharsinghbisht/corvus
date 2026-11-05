# Reuse a saved collection

When an endpoint is retired or backend retention expires, an earlier investigation's original evidence can still be useful. Corvus can prepare a **new manual attempt from that saved collection**, without an indexer request, endpoint connection, model call, or automatic retry.

This path uses only collections already saved in PostgreSQL. It does not import arbitrary files, load simulation ground truth, or query the private dataset directory.

## Operator flow

1. Open a finished attempt with a valid saved original collection. Choose **Reuse saved evidence** in the investigation header or expand the same disclosure below the report.
2. Check the original collection time and locally stored event count. Choose focused (4 supporting events / 16 KiB) or explicitly broader (12 / 48 KiB) input.
3. Acknowledge that the evidence is historical and does not establish current endpoint state. This acknowledgement is **not external-processing consent**. Select **Prepare from saved evidence**.
4. Corvus creates and pins a separate attempt in `awaiting_approval`. Review its exact selected input, original gaps, local Correlation/Intel views, and historical-data warning. Preparation did not refresh the observations.
5. Only the normal, separate **Approve one Analyst request** action can authorize a new model call. It may incur another charge even if the original request failed or has an unknown outcome. Cancel the new attempt if it is not needed.

The collection's original ID, timestamp, documents, query results, and gaps remain unchanged. Reuse time is not collection time. Unknown original age stays explicitly unknown; a new attempt timestamp is never substituted as observation freshness.

## Bindings and safeguards

- Sources must be terminal (`validated`, `rejected`, `failed`, `unknown`, or `cancelled`) and contain a valid original collection. Active or missing/invalid collections cannot be reused.
- The authenticated API requires the application Origin, a strict historical acknowledgement, profile allowlist, and the **original collection digest**, not the old selected-input digest. A stale source binding or cross-alert source is refused.
- Reuse and fresh collection share the same job-row lock and single-active-attempt constraint. Simultaneous preparations cannot create duplicate active jobs. Finish/cancel existing work first.
- The new attempt is always manual, including when its source was automatic. It does not inherit processing consent, approvals, policy authorization, result, reply, or human review.
- Raw original evidence is copied without rewriting it. The selected input adds `scope.saved_collection_reuse` and a `saved_collection_reused` gap **before** applying the byte budget. The original collection digest remains separately recorded. Historical coverage is partial; existing benign-clearance restrictions still apply.
- Switching focused/broader profiles before approval retains the historical annotation and gap, changes the selected digest, and clears client consent. Approved/started/completed inputs remain immutable.
- A valid preparation commits `awaiting_approval`, not a collection or model queue entry. The worker ignores it until a separate approval. Preparation cannot resume or repair a billed request.
- Source attempt/collection IDs, source digest, original time, and reuse time are preserved in provenance and private exports. Markdown handoffs explicitly say that no new backend query occurred.

The Analyst is instructed to scope findings to the original period and not infer current endpoint state, remediation, containment, or incident resolution. Input warnings and integrity validation do not prove narrative quality. Reusing a report never means its old conclusion or review was accepted for a new attempt.

## Verification

VM-only integration tests cover original preservation, no inherited consent/reviews/replies, historical annotations under both profiles, digest conflicts, simultaneous reuse/fresh collection, invalid sources, explicit handling of unknown/restored attempts, and a single fake model request after fresh approval. Browser checks prepare and pin an historical attempt, reload without consent, and cancel it without a model request or recollection.

Production deployment and read-only verification do not create a reuse attempt, submit a review, or call the model. Any real run remains an explicit operator decision.
