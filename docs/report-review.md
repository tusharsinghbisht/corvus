# Human assessment review

A model report passing integrity checks is not a human decision. Corvus records human assessment review separately from model output, incident resolution, and authorization for endpoint actions.

## Operator workflow

1. Open a report that passed integrity checks. The alert's evidence map and findings remain available while reviewing.
2. Check the main claims against their source facts, especially PID/GUID identity, attempted versus completed behavior, network/persistence claims, gaps, and legitimate alternatives.
3. Under **Human review**, choose:
   - **Accept assessment**: the assessment is supported within its stated scope. Requires an explicit evidence/gaps attestation.
   - **Reject assessment**: record unsupported conclusions or other assessment problems. The original report remains preserved.
   - **Needs follow-up**: record what remains to be investigated. This does not queue collection or a model request.
4. Enter a rationale of 10–2,000 characters and save. Notes are rendered as untrusted plain text, remain in Corvus, and are never automatically sent to the Analyst.
5. Subsequent decisions append to history rather than changing or deleting earlier records. Review history is paginated; older decisions remain accessible.

The alert queue displays the review status of its latest report that passed integrity checks, alongside any newer attempt failure. The Analyst page filters by human review state. Its report counts are per investigation attempt, not per incident. Links from that page open the exact attempt rather than silently selecting a different report.

## Binding, concurrency, and validation

Each review stores the authenticated reviewer, sequence, insertion time, decision, rationale, evidence attestation, analysis ID, selected-evidence digest, report digest, generation validator version, and a fresh local integrity-validation result.

The report digest binds the assessment, analysis identity, selected evidence identity, prompt version, and generation-time validation. Accepting an assessment also requires passing the current validator against the saved selected evidence. Rejection/follow-up can record a problem even if current validation no longer passes. Technically rejected or incomplete candidates cannot be promoted to accepted assessments through review.

A digest is not a signature or proof of narrative entailment. Database operators remain able to modify runtime data; scheduled protected backups and stronger tamper-evidence are separate operational work.

Reviews serialize on the attempt row. Each submission includes the exact report/evidence binding and the review sequence the operator saw. Stale targets or concurrent/stale-tab decisions return **409** and require an explicit reload before resubmission. There is no automatic mutation retry. If a network failure makes saving ambiguous, inspect history before trying again.

A changed report snapshot makes its previous decision stale. A new model attempt always starts with no human review; acceptance is never inherited from an earlier attempt. The viewed assessment is pinned while reviewing so a newly completed attempt does not silently replace an in-progress review.

## Boundaries

- Acceptance is not confirmation of compromise, incident closure, containment approval, or a response-execution token.
- Review does not change the model disposition, native severity, collected evidence, input snapshot, candidate, or generation-time validation.
- The stored model artifact keeps `human_review_required: true`: it records that model output required human review at generation. Recorded review is separate state, not a rewritten model claim.
- The current validator checks integrity and conservative constraints, not whether prose follows from evidence. Human attestation is also not an automated accuracy guarantee.
- No review action invokes a model, retries an attempt, enables automation, or executes a recommendation.
- Existing authentication, Origin checks, and the single-operator pilot permissions apply. There is no reviewer-role separation, SSO/MFA, incident lifecycle, or response executor.

## Implementation and checks

- `src/corvus/server/investigations/reviews.py`: exact binding, append-only API, current revalidation, optimistic concurrency, and history.
- `src/corvus/server/investigations/overview.py`: page-bounded alert enrichment and Analyst review queues; notes/model content are not exposed in queue rows.
- `src/corvus/server/migrations/004_report_reviews.sql`: review history; existing reports start unreviewed and remain otherwise unchanged.
- `web/components/report-review.tsx`: decision form, attestation, history, and stale-tab recovery.
- `tests/test_reviews.py`: real disposable PostgreSQL, binding and concurrency failures, immutable model artifacts, history pagination, and no model calls.
- Workspace browser tests cover review decisions, untrusted note rendering, stale tabs, reload persistence, deep links, and queue/filter state using offline evidence and a fake model.
