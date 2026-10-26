# Corvus Architecture

> **Status: living draft — v0.1.** This document describes the current proposed architecture, not an implemented system or a final specification. Update it as experiments, integrations, and implementation change our understanding.

## 1. Purpose and Scope

Corvus is an independent AI SOC agent that consumes security alerts, investigates them using available evidence, and supports policy-governed response through verification and closure.

Wazuh is the first backend, not the product boundary. Corvus owns investigation orchestration, evidence-backed findings, response governance, and evaluation. Existing security systems own telemetry collection, detection, and the security capabilities they expose.

The first implementation targets read-only investigation of suspicious PowerShell execution in an isolated Windows lab. Broader integrations and live response are later stages.

For delivery milestones and evaluation scenarios, see the [initial plan](initial-plan.md).

## 2. Architectural Principles

1. **Evidence before conclusions.** Alerts and rule metadata are leads, not ground truth.
2. **Investigate beyond triggering events.** Relevant non-alert activity must be searchable where collected.
3. **Backend independence.** Keep source-specific APIs, queries, and field mappings inside adapters.
4. **Bounded autonomy.** Code and policy enforce permissions; the model cannot grant itself access.
5. **Explicit uncertainty.** Missing telemetry, failed queries, and contradictory evidence must remain visible.
6. **Durable, auditable work.** Preserve investigation state, evidence references, tool results, and action history.
7. **Simple first.** Logical components do not imply separate services or multiple agents.

## 3. System Context

```text
                         SECURITY DATA PLANE

 Isolated Windows lab                     Compatible dataset replay
          |                                          |
     Wazuh agents                         Validated ingestion path
          |                                          |
          +-------------------+----------------------+
                              |
                        Wazuh server
                     Decoders and rules
                              |
                Indexed alerts / searchable evidence
                              |
                    Read-only backend adapter
                              |
  +---------------------------v-----------------------------------+
  |                          CORVUS                              |
  |                                                              |
  | Alert intake -> Case management -> Investigation orchestrator |
  |                                      |                       |
  |                                Tool gateway                  |
  |                                      |                       |
  |                         Evidence / context adapters           |
  |                                      |                       |
  |                       Findings and response proposal          |
  |                                      |                       |
  |                       Policy and approval boundary           |
  |                                      |                       |
  |                      Restricted action executor              |
  |                                                              |
  | Case state, evidence references, and audit records            |
  +--------------------------------------+-----------------------+
                                         |
                         Authorized security action APIs
                                         |
                         Independent effect verification

 Separate evaluation harness: private ground truth and scenario scoring
```

This is a logical view. Deployment units, databases, queues, and runtime frameworks are not yet selected.

## 4. Components and Responsibilities

| Component | Responsibility | Boundary |
| --- | --- | --- |
| Alert intake | Accept or fetch alerts; validate and normalize them; track ingestion progress | Delivery mechanism is undecided; duplicates must be safe to process |
| Case management | Track investigation scope, related alerts, entities, status, and history | Alert deduplication is distinct from incident correlation |
| Investigation orchestrator | Plan investigative steps, call tools, revise hypotheses, and assemble findings | Operates within query, time, and cost budgets |
| Model interface | Provide reasoning and structured planning through a replaceable model integration | No direct credentials or arbitrary network/tool execution |
| Tool gateway | Validate calls, enforce access scopes and limits, and record results | Reject unsupported operations rather than silently broadening access |
| Backend adapters | Translate normalized requests into source-native operations | Preserve source-native details and surface mapping limitations |
| Context providers | Supply available host, identity, asset, and threat-intelligence context | Report provenance, lookup time, and gaps; providers are not yet selected |
| Evidence handling | Store evidence references, provenance, query scope, and selected snapshots | Avoid copying the full SIEM into Corvus |
| Response policy | Evaluate proposed actions and determine approval requirements | Enforcement is deterministic and outside model reasoning |
| Approval interface | Capture an authorized operator's decision on a specific action | Approval must be bound to the exact target and parameters |
| Action executor | Perform allowlisted actions and track execution status | Separate credentials and permissions from read-only investigation |
| Verification workflow | Check whether the intended effect occurred | API success alone is insufficient |
| Evaluation harness | Run scenarios and compare outputs to private expectations | Ground truth is inaccessible to the investigator |

The initial implementation should favor a single application with clear module boundaries. Separate services or multi-agent coordination should be introduced only when a demonstrated need justifies them.

## 5. Wazuh Integration Boundary

### Alert and evidence access

- Use the Wazuh indexer search interface for indexed alerts and other indexed telemetry.
- Use the Wazuh server API for applicable management and operational information.
- Validate the exact supported operations against the selected Wazuh version.
- Start with read-only credentials and narrowly scoped index access.

Wazuh's native detection pipeline uses decoders and XML-based rules. Sigma execution is not part of this architecture's initial requirements.

### Non-alert telemetry

An alert index is not a complete evidence store. Configure and validate the collection, retention, forwarding, and indexing of relevant non-alert events.

Two storage options remain open:

1. A deliberately configured Wazuh archive/indexing pipeline.
2. A separate searchable telemetry store behind an evidence adapter.

The choice depends on scenario coverage, operational complexity, and storage cost. Missing data must not be presented as a successful search proving an activity did not happen.

### Response access

Wazuh active response is one possible execution mechanism for configured actions. Do not assume every desired containment action is available natively. Each action requires a defined implementation, authorization policy, failure handling, and verification procedure.

## 6. Investigation Data Flow

1. **Receive an alert.** Preserve its source identity, timestamps, rule metadata, entities, and original payload or reference.
2. **Create or attach to a case.** Handle duplicate delivery safely. Correlation with other cases requires explicit supporting evidence.
3. **Establish scope.** Define entities, an initial time range, available sources, and an investigation budget.
4. **Gather evidence.** Retrieve triggering events and pivot into relevant surrounding activity through bounded tools.
5. **Evaluate hypotheses.** Consider benign explanations, contradictory observations, and missing coverage. Expand scope only within configured limits.
6. **Produce findings.** Separate observations from inferences, cite evidence, and record uncertainty.
7. **Propose a response.** In the initial read-only phase, stop at recommendations.
8. **Authorize and execute, when enabled.** Apply policy and any required approval before dispatching an action.
9. **Verify and report.** Record the observed effect, unresolved questions, and final or partial outcome.

An investigation can pause or end as inconclusive. It should not continue indefinitely or manufacture a definitive answer to satisfy the workflow.

## 7. Conceptual Data Contracts

These describe responsibilities, not finalized schemas or API signatures.

| Object | Initial information to preserve |
| --- | --- |
| Alert | Corvus ID, source-native ID, backend, rule metadata, event/ingest times, entities, evidence references, original payload reference |
| Case | Related alerts, scope, entity references, status, investigation history, findings, timestamps |
| Evidence | Stable reference, source event ID, provenance, event/retrieval times, relevant fields or snapshot, query context |
| Tool result | Request and query scope, execution status, coverage limitations, pagination/truncation, returned evidence references |
| Finding | Claim, supporting and conflicting evidence, inference versus observation, uncertainty |
| Response proposal | Action, exact target, parameters, rationale, supporting evidence, expected effect, recovery considerations |
| Approval | Approver, decision, authorized proposal version, timestamp, expiry or other constraints |
| Action record | Authorization reference, request identity, execution status, errors, timestamps, verification result |

Prefer stable host and identity identifiers where available. Hostnames, IP addresses, and display names alone may be ambiguous or change over time.

### Tool result semantics

Distinguish at least:

- Successful query with results.
- Successful query with no results in the stated scope.
- Partial or truncated results.
- Unavailable or uncollected source.
- Permission denial.
- Invalid query or unsupported operation.
- Timeout or backend failure.

An empty result is meaningful only in the context of collection coverage, retention, query scope, and backend health.

## 8. State and Persistence

Persist enough state to resume an investigation and explain its outcome without depending solely on model conversation history.

Proposed case lifecycle:

```text
received -> investigating -> findings_ready -> closed
                  |
                  +-> waiting_for_input -> investigating
                  |
                  +-> failed / cancelled
```

Case closure records a disposition such as supported malicious activity, likely benign activity, or inconclusive. Closure does not imply successful remediation.

Response actions have a separate lifecycle:

```text
proposed -> policy_evaluation -> approval_pending (if required)
                                      |
                 authorized <---------+
                      |
                 dispatched -> execution_result -> verification_result
```

Denial, expiry, cancellation, failure, and unknown outcomes must be representable. An ambiguous execution result must not trigger a blind retry of a disruptive action.

Storage technology is undecided. The logical needs are case state, evidence metadata or selected snapshots, action records, and an append-oriented audit history. These need not be separate databases.

## 9. Trust and Safety Boundaries

### Untrusted evidence versus instructions

Logs, command lines, file content, threat-intelligence text, and retrieved documents may contain attacker-controlled instructions. Treat them as evidence only. Do not allow retrieved content to change tool permissions, execution policy, or approval requirements.

### Read versus write access

Investigation tools and response executors should use separate permissions and credentials. A response proposal is data submitted for authorization, not an executable command supplied by the model.

### Approval integrity

Bind approvals to a specific action, target, and parameter set. Material changes require fresh authorization. Recheck policy and approval validity before execution, especially after delays or restarts.

### Privacy and secrets

Keep credentials outside prompts and case reports. Define redaction and external-model data policies before sending sensitive telemetry to a model provider. Audit records must not become a second uncontrolled repository of secrets.

### Environment isolation

Use authorized, isolated lab endpoints for attack simulation and live response testing. No production credentials or production containment are part of the initial scope.

## 10. Reliability and Observability

- Track intake checkpoints and handle repeated alert delivery idempotently.
- Bound searches by time range, result volume, timeout, and pagination.
- Apply retry/backoff to appropriate transient read failures.
- Make action retries conditional on known execution state and backend guarantees.
- Record tool calls, durations, errors, model usage, and investigation costs.
- Preserve original event time and ingestion time; document replay time transformations.
- Record model, prompt, adapter, and relevant configuration versions for evaluation.
- Return partial or inconclusive outcomes when required dependencies are unavailable.

Operational logs should help distinguish collection, detection, adapter, model, policy, and execution failures.

## 11. Evaluation Architecture

The evaluation harness supplies controlled scenarios and privately stores expected outcomes. Corvus sees only the alerts, accessible telemetry, and permitted context.

The first scenario family is suspicious PowerShell execution, with malicious, legitimate, incomplete-evidence, and multi-alert variants.

Evaluate:

- Disposition accuracy and evidence quality.
- Unsupported claims and missed contradictory evidence.
- Retrieval of useful non-alert events.
- Handling of absent sources and tool failures.
- Unnecessary or unauthorized response recommendations.
- Execution and verification correctness when enabled.
- Latency, query volume, model cost, and run-to-run variability.

Historical replay can validate investigation and response selection. It cannot prove that a containment action stopped an attack; that requires controlled live testing.

## 12. Decision Register

These are current directions and may be revised with evidence.

| Topic | Current direction | Still open |
| --- | --- | --- |
| First backend | Wazuh, integrated through an adapter | Version, deployment, access configuration |
| Initial domain | Windows endpoint investigation | Exact logging configuration and rules |
| Detection | Reuse Wazuh detections | Targeted custom rules if scenarios require them |
| Agent topology | Simple orchestrated workflow first | Model and orchestration framework |
| Deployment shape | One application with logical modules initially | Runtime, packaging, durable job mechanism |
| Evidence storage | Search backend plus Corvus provenance/references | Archive indexing versus separate telemetry store; retention |
| Response | Read-only first, simulation next, restricted live actions later | First action, approval mechanism, verification method |
| Evaluation | Controlled lab plus validated replay | Dataset selection, baseline, acceptance thresholds |

## 13. How This Document Evolves

Update this document when component boundaries, data contracts, trust assumptions, deployment shape, or integration decisions change.

- Mark proposals as proposals until validated.
- Record important decisions and their rationale; avoid silently turning assumptions into facts.
- Add concrete schemas and deployment diagrams as implementation emerges.
- Move substantial trade-off discussions into dedicated decision records when useful.
- Keep the [README](../README.md) and [initial plan](initial-plan.md) aligned with material architectural changes.
