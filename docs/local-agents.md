# Focused Analyst input and local agents

Corvus now has working **local deterministic Correlation and Intel stages** alongside the single-request Analyst. These are not additional LLM conversations, autonomous investigators, threat-reputation services, or response agents. They make no external request or billable model call.

## Smaller default input

New dashboard investigations default to **focused** context: the trigger plus **at most four supporting events**, with a **16 KiB selected-evidence cap**. Fixed instructions/report schema are additional input; byte counts are not tokenizer estimates. The broader bounded collection remains local, unchanged.

Correlation ranks matching process GUIDs, parent/child candidates, and exact long command-line matches within fifteen minutes on the same agent. GUIDs are normalized for comparison; missing, malformed, or zero GUIDs do not become matches. Mirrored Windows records are deduplicated using agent/channel/event-record ID/source system time. Focused mode selects representative event kinds, limits repeated process activity, and does **not** pad input with siblings or merely nearby events. Without a qualifying match, trigger-only input is valid. This is not proof of no relevant activity.

The input records why each supporting event was selected. A match is a selection hint, not verified ancestry, causation, authorization, or maliciousness. Query counts/status/scope still describe the original local query; reference listings may be shortened to selected documents with explicit omission counts. A shortened list is not an empty query.

Verbose `full_log` and Windows system message renderings may be omitted when structured Windows event data exists. Those renderings can contain additional text: omissions are explicit, originals remain local, and the input becomes partial. Long-field excerpts and other omissions remain marked. Partial evidence still cannot support benign clearance; no validator gate was weakened.

## Deliberately broaden before approval

While a **manual attempt awaits approval**, choose:

- **Focused:** up to 4 supporting events / 16 KiB.
- **Broader:** up to 12 supporting events / 48 KiB; permits bounded sibling/time-proximity candidates, explicitly labeled as weaker relationships.

This reselects from the saved local collection without recollecting, sending evidence anywhere, or invoking a model. It preserves the original collection and updates the selected evidence, exact input snapshot, and digest. Client consent is cleared. A stale digest cannot approve or overwrite the new selection. Once approved, queued, requesting, or completed, that input is immutable; profile switching is not a retry or report repair.

If the trigger/metadata cannot fit the focused cap, the local collection is retained with `context_budget_exceeded`. A manual operator can try the broader profile locally before approving anything. If even that does not fit, nothing is sent. Automatic policies use focused input and do not escalate budgets or profiles after a failure. Deployment does not enable automation.

Saved historical reports, rejected candidates, and approved inputs are not retroactively trimmed or relabeled. They retain their actual historical event counts, digests, and prompts. Current prompt version is 0.6; context selection version is 2.0. CLI analysis still honors its explicitly reviewed bundle; these dashboard selection defaults do not silently rewrite CLI input.

## Agent views

Agents → **Correlation** and **Intel** show real saved inputs available for inspection, with exact attempt links. This is not a count of completed autonomous investigations. Open an attempt and expand **Correlation & Intel · local inspection** inside its selected context.

- **Correlation** is actually executed during new input preparation. Recorded selection reasons are shown without reconstructing relationship claims for historical inputs that predate them.
- **Intel** inspects allowlisted structured IP, DNS-query, and hash fields in the saved selected input. It reports syntactic/address-class facts with exact document references and JSON field paths. It is computed locally on inspection, not a generation-time artifact or extra Analyst input. It does not mine arbitrary command text or follow embedded URLs. Its observations/source listings are bounded; truncation is explicit.

Private, special-use, or globally routable addresses are not safe/malicious verdicts. A syntactically valid hash is not proof of file identity or reputation. There is no DNS resolution, threat-feed, geolocation, sandbox, or external lookup. No indicators found in these fields does not mean none exist.

## Still planned

Autonomous Correlation/Intel LLM roles, investigative tool loops, multi-agent case/task orchestration, containment, and post-response independent verification remain planned. Local stages do not grant consent, accept assessments, resolve incidents, or authorize response. Human assessment review and any future response approval remain separate.

Checks run on the authorized VM with disposable PostgreSQL, offline model/backend fakes, browser tests, and private count-only previews of saved evidence. Shipping a smaller prompt is not proof that the live model will complete or reason correctly; a new real request still needs explicit selected-input approval.
