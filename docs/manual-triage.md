# Manual Analyst investigations

Manual triage is a read-only workflow on an ingested alert. Reports can receive an explicit [human assessment review](report-review.md). This does not close an incident or authorize containment. Ingestion alone never authorizes a model call. Automatic processing requires a separate [connection policy](analyst-policies.md).

## Operator workflow

1. Open an alert and select **Investigate with Analyst**. This queues local collection only.
2. Inspect the saved input, collection scope, original sources, and gaps. The fixed scope is the alert's agent, five minutes either side of its indexed timestamp, up to 100 events per query, and a six-hour process-GUID ancestry pivot when available. The existing collector and read-only adapter perform retrieval; Corvus does not mirror archives.
3. Check the external-processing acknowledgment and select **Approve one Analyst request**. Consent is recorded against this attempt's exact evidence digest, with the operator and approval time. The worker sends the saved evidence, not a later recollection. Evidence selection is **not redaction**; source data may contain personal information or secrets.
4. Review findings, exact citations, alternative explanations, uncertainties, and collection gaps. References open the saved evidence rather than fetching mutable source documents. Passing validation means report integrity, not proven narrative entailment.
5. Inspect attempt history for failures, rejected candidates, original replies, and provenance. Starting a new investigation collects fresh backend context and requires fresh consent. Alternatively, [reuse a saved collection](saved-evidence.md) to prepare a separate manual attempt without recollection. Its original age/gaps remain visible; it still needs fresh processing consent. Earlier attempts remain intact.

Unstarted collection, awaiting-approval work, and queued model work can be cancelled. A request already in flight cannot be cancelled from the browser; leaving the page does not cancel it. There are no automatic retries or alternate-model fallbacks.

## State and durability

PostgreSQL stores one job per alert and an append-only sequence of attempts. An attempt advances through these states:

```text
pending_collection → collecting → awaiting_approval → queued → requesting
                          │              │             │          │
                          ↓              └── cancelled ┘          ├── validated
                        failed                                    ├── rejected
                                                                  ├── failed
                                                                  └── unknown
```

A partial unique index permits only one active attempt per job, including the approval wait. New attempts are serialized by the job row. Approval is a strict boolean plus the exact saved digest; duplicate, stale, or cross-alert approvals are refused. All data APIs require an authenticated session and mutations require the application Origin.

The triage consumer runs independently from ingestion in the worker process. A PostgreSQL session advisory lock elects one consumer, so a slow model request is not reclaimed by an expiring lease. Its successor marks interrupted collection as failed and interrupted requests as **unknown**. It never reissues them. Queued work has not crossed the request boundary and can resume safely.

Before the model call, the worker commits the request-start marker and configured integration provenance. It saves an available model reply before parsing and validating it, then saves the candidate and validation result. Incomplete candidates returned by the provider are retained when available, along with the finish reason and allowlisted token usage even when final content is absent. Private reasoning traces are not retained. A response that reaches its output-token limit is a failed attempt, not an accepted partial report. Budget changes require explicit operator configuration and apply only to future approved requests; there is no automatic escalation. There is still an unavoidable remote-completion/local-save crash window: unknown means the provider may have processed or billed the request, not that it failed to run. Request transport failures are also conservatively unknown. Both failed and unknown states require an explicit new attempt.

Evidence bundles are capped at 16 MiB, with fixed document/query bounds and the adapter's transport request budget. Oversized collection fails rather than being silently truncated for analysis. Provider request limits may be smaller; such failures remain visible without an automatic retry. Query errors and truncation within a saved bundle remain collection gaps. No elevated credentials are requested to bypass missing coverage.

## Implementation map

| Boundary | Location |
| --- | --- |
| Authenticated routes and strict request fields | `src/corvus/server/api.py` |
| Job/attempt creation, consent, cancellation, history | `src/corvus/server/investigations/service.py` |
| Consumer election, recovery, collection, one model request | `src/corvus/server/investigations/worker.py` |
| Ordered database upgrade | `src/corvus/server/migrations/002_triage.sql` |
| Existing backend-independent collector | `src/corvus/evidence.py` |
| Existing single-pass Analyst and validation | `src/corvus/agents/analyst/`, `src/corvus/reporting/` |
| Attempt controls and evidence inspection | `web/components/investigation.tsx` |
| Advisory findings and saved citations | `web/components/investigation-report.tsx` |

LangGraph runs the single-pass Analyst with no tool loop, graph retries, graph checkpoint replay, or external tracing. Automatic mode is independently opt-in per connection and cannot process a historical backlog. See [policies, context selection, and evidence maps](analyst-policies.md). There is no response executor.

## Deployment and verification

Install integration credentials **only in the worker**, using the optional Compose override described in [deployment](deployment.md) and the private [adapter setup guide](providers/azure-foundry.md). Missing configuration produces a terminal configuration failure before a request. Credentials do not belong in PostgreSQL provenance, frontend code, or API settings.

`tests/test_triage.py` exercises real PostgreSQL transactions, concurrent duplicate requests, consent/digest binding, cancellation, interrupted requests, consumer election, failed collection, rejected candidates, and preserved replies. The workspace browser suite uses the real API/state machine with offline collection and a fake model. It never transfers live evidence. Native detection, real ingestion, model transport availability, and report reasoning must be verified separately.
