# Corvus: Initial Architecture and Implementation Plan

Status: Initial proposal. No deployment or implementation is implied by this document.

## 1. Vision

Corvus is an autonomous AI SOC agent that investigates SIEM-generated alerts and supports the security operations lifecycle:

**Triage → correlation → evidence collection → enrichment and adversary context → response planning → containment and remediation → verification and closure.**

The long-term goal is policy-bounded autonomy: Corvus investigates independently and executes only actions explicitly permitted by policy. High-impact actions require approval unless a narrowly scoped policy authorizes them.

The initial goal is narrower: prove that Corvus can investigate an alert using real telemetry, produce evidence-backed conclusions, recognize uncertainty, and recommend a safe response.

## 2. Initial Architecture Decision

Use **Wazuh as the first security backend**, rather than building a custom detection engine before building Corvus.

Corvus will be an independent application that integrates with Wazuh through an adapter. It will not require a Wazuh fork, and its investigation logic should not depend directly on Wazuh-specific APIs or query syntax.

### Why this approach

- Reuse existing collection, decoding, detection, indexing, and operational interfaces.
- Work with realistic alerts and integration constraints instead of fabricated alert payloads.
- Focus engineering effort on investigation, evidence handling, response safety, and evaluation.
- Preserve a path to other SIEM and security-tool integrations.

### Alternatives considered

| Approach | Benefit | Initial decision |
| --- | --- | --- |
| Public telemetry plus a custom Sigma runner | Reproducible detection experiments | Defer: too much detection-engine work before validating the agent |
| Wazuh plus controlled lab telemetry | Existing security platform and accessible endpoint workflows | Adopt as the first integration |
| A Sigma-compatible detection backend | Useful for testing Sigma conversion and rule portability | Revisit if Sigma becomes a concrete requirement |
| Fabricated alerts without underlying telemetry | Fast interface prototyping | Allow only for unit tests, not investigation evaluation |

Wazuh primarily uses its own decoders and XML-based rules; it does not natively use Sigma as its detection rule language. Sigma portability is not an MVP requirement.

## 3. MVP Scope

### In scope

- One Wazuh deployment and a small isolated endpoint lab.
- Windows endpoint telemetry as the first investigation domain.
- Existing Wazuh detections, with targeted custom rules only where necessary.
- Alert ingestion and normalization into a Corvus-owned contract.
- Read-only searches across alerts and relevant non-alert telemetry.
- Entity pivots involving hosts, users, processes, and other available fields.
- Evidence-backed investigation reports and response recommendations.
- Explicit handling of missing evidence and unavailable tools.
- Reproducible test scenarios and a separate ground-truth evaluator.
- Simulated response before narrowly scoped live response testing.

### Out of scope initially

- A new SIEM, custom general-purpose detection engine, or Sigma execution engine.
- Full coverage of cloud, email, network, identity, and endpoint investigations.
- Unrestricted autonomous containment or remediation.
- Production deployment and production security credentials.
- Claims of enterprise readiness based only on curated datasets.

## 4. Proposed Architecture

```text
Isolated lab endpoints                 Public datasets
        |                                    |
  Wazuh agents                    Replay / compatible ingestion
        |                                    |
        +------------------+-----------------+
                           |
                     Wazuh server
                  Decoding and detection
                           |
            Indexed alerts + searchable evidence
                           |
                     Wazuh adapter
                           |
                         Corvus
                 +---------+---------+
                 |                   |
         Investigation tools    Context providers
                 |
         Evidence-backed findings
                 |
       Response policy and approval
                 |
       Restricted action executor
                 |
     Wazuh active response / other APIs
                 |
         Post-action verification

Separate evaluator: scenario ground truth and expected outcomes
```

The exact storage topology is not yet selected. Non-alert evidence may be indexed through a deliberately configured Wazuh archive pipeline or stored in a separate searchable telemetry backend.

### Important interface distinction

- The **Wazuh server API** provides management and operational information.
- The **Wazuh indexer search interface** provides access to indexed alerts and other indexed events.
- Searchable alerts do not imply that all surrounding raw telemetry is collected, retained, or indexed.

Evidence coverage must be validated before implementing agent reasoning.

## 5. Telemetry and Evidence Strategy

### Start with a live, controlled lab

Use an isolated Windows endpoint with suitable logging, such as Sysmon and relevant Windows event channels. The exact event configuration must be selected according to the first investigation scenarios.

Before adding AI, manually demonstrate that the environment can retrieve:

- An alert and its triggering events.
- Surrounding process activity, where collected.
- Relevant authentication activity.
- Related network or DNS activity, where collected.
- Host and user context sufficient for the scenario.

A missing source or field must be recorded as a coverage limitation, not treated as evidence that an activity did not occur.

### Add public datasets for replay

Candidate sources include OTRF Security-Datasets / Mordor, Splunk Attack Data, and Splunk BOTS datasets. Evaluate licensing, provenance, formats, field coverage, and benign activity before adopting any dataset.

Dataset ingestion is not assumed to work out of the box. Validate decoding, field mappings, timestamps, and rule behavior. A historical event file may require an ingestion adapter or custom decoder before it produces meaningful Wazuh alerts.

### Preserve provenance

Retain, subject to the lab's storage and privacy policy:

- Original events or retrievable references to them.
- Parsed and normalized fields.
- Source and event identifiers.
- Event time and ingestion time.
- Parser or mapping versions where applicable.

Replay should preserve event relationships and explicitly document any timestamp transformations. Later tests should exercise delayed and out-of-order events.

### Avoid evaluation leakage

Ground-truth labels, attack narratives, and expected conclusions belong in the evaluator. Do not expose them through searchable documents, scenario filenames, alert annotations added for evaluation, or tool responses.

## 6. Corvus Integration Contracts

Define backend-independent interfaces before implementing the Wazuh adapter. Initial capabilities may include:

```text
get_alert(alert_id)
search_events(filters, time_range)
get_event(event_id)
get_host_context(host_id)
get_identity_context(identity_id)
request_response(action, target, justification)
get_action_status(action_id)
```

These are conceptual contracts, not finalized API signatures.

### Alert contract

Include source, source-native alert ID, rule ID, timestamps, entities, severity, and evidence references. Preserve source-native details alongside normalized fields.

Rule descriptions, severity, and ATT&CK mappings are investigative leads, not proof of compromise.

### Evidence contract

Return stable references, source information, timestamps, relevant event fields, and query scope. Clearly distinguish empty results from errors, unavailable sources, incomplete results, or access restrictions.

Use bounded queries and pagination. Corvus must not interpret a truncated search as a complete account of activity.

### Investigation output

Produce a report containing:

- Initial alert and investigation scope.
- Findings and supporting evidence references.
- Relevant timeline and entities.
- Alternative explanations considered.
- Missing evidence and uncertainty.
- Disposition: supported malicious activity, likely benign activity, or inconclusive.
- Recommended response and rationale.
- Action and verification status, when applicable.

## 7. Safety and Response Boundaries

Begin in read-only mode. Introduce simulated response before live actions.

- Treat telemetry, command lines, and external intelligence as untrusted data, not instructions to the agent.
- Enforce permissions outside the model.
- Expose only allowlisted actions with validated targets and parameters.
- Do not provide unrestricted shell execution or unrestricted active-response access.
- Require approval for disruptive actions unless explicitly authorized by a narrow policy.
- Record evidence, policy decisions, approvals, requests, results, and verification.
- Handle retries without accidentally duplicating destructive operations.
- Define rollback or recovery procedures where an action supports them.

Keep these states distinct:

1. An action was recommended.
2. An action was authorized.
3. An action was requested.
4. The execution system reported success or failure.
5. Independent evidence verified the intended effect.

An accepted API request does not prove successful containment. Historical replay cannot demonstrate that a response stopped an attack; that requires a controlled live environment and appropriate verification evidence.

## 8. First Investigation Scenario

Start with **suspicious PowerShell execution**.

Corvus should inspect the triggering event, process ancestry, available logon context, and related activity before recommending a disposition or response.

Test at least these variants:

1. Controlled malicious behavior with corroborating evidence.
2. Legitimate administrative activity with similar indicators.
3. Missing telemetry that prevents a confident conclusion.
4. Related activity across multiple alerts or hosts.

Do not consider the scenario complete merely because the agent repeats the alert description or recognizes a suspicious command.

## 9. Implementation Milestones

| Milestone | Deliverable | Exit criteria |
| --- | --- | --- |
| 1. Lab and telemetry | Wazuh deployment, isolated endpoint, logging configuration | Manually retrieve an alert and relevant surrounding non-alert events |
| 2. Read-only integration | Alert adapter and bounded evidence-query tools | Contracts distinguish results, errors, missing coverage, and truncation |
| 3. Investigation workflow | Evidence-backed report for the first scenario | Conclusions are traceable to retrieved evidence; uncertainty is explicit |
| 4. Evaluation harness | Repeatable scenario runs and private ground truth | Malicious, benign, and inconclusive variants can be compared across revisions |
| 5. Simulated response | Policy checks, approval flow, action audit trail | Unauthorized actions are blocked and action states remain distinct |
| 6. Controlled live response | A narrow, reversible action in the isolated lab | Execution and intended effect are verified independently |
| 7. Broader validation | More scenarios and eventually a second backend | Identify assumptions tied to Wazuh and test portability |

## 10. Evaluation

Track more than whether the final classification matches a label:

- Correctness of disposition and supporting reasoning.
- Whether factual claims have valid evidence references.
- Retrieval of relevant evidence beyond the triggering alert.
- Recognition of missing or contradictory evidence.
- False or unnecessary containment recommendations.
- Policy enforcement and approval behavior.
- Accuracy of action execution and verification status.
- Investigation latency, query volume, and model cost.
- Reproducibility across repeated runs.

Set quantitative acceptance thresholds after establishing a baseline. Report scenario coverage and limitations alongside aggregate results; do not infer production reliability from a small curated benchmark.

## 11. Open Decisions

- Wazuh version, deployment topology, and resource budget.
- Endpoint provisioning and logging configuration.
- Storage, retention, and indexing strategy for non-alert events.
- Initial detection rules and exact scenario definitions.
- Application stack, model provider, and orchestration approach.
- Identity and asset-context sources.
- Credential management, access scopes, and audit storage.
- First allowed response action and its verification procedure.
- Dataset licensing and replay adapters.

## 12. Guiding Principle

Build the smallest environment that can answer this question honestly:

> Given a realistic alert, access to imperfect evidence, and bounded permissions, can Corvus investigate correctly and recommend or perform a safe, verifiable response?

Reuse detection infrastructure. Own the investigation workflow, evidence quality, safety boundaries, and evaluation.
