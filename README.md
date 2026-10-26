# Corvus

**An autonomous AI SOC agent—from SIEM alert to evidence-backed response.**

Corvus aims to investigate security alerts, correlate related activity, gather and enrich evidence, and carry incidents through policy-governed containment, remediation, and verification.

> **Project status: architecture and planning.** This repository currently contains the initial design, not a working agent or deployable integration. Capabilities described below are planned unless explicitly stated otherwise.

## Vision

Security alerts are starting points, not conclusions. Corvus is designed to investigate what happened, determine what the evidence supports, and recommend or execute an appropriate response within explicit safety boundaries.

The intended SOC workflow is:

```text
Triage → correlation → evidence collection → enrichment and adversary context
       → response planning → containment and remediation → verification and closure
```

The goal is more than alert summarization: conclusions should be traceable to evidence, uncertainty should be explicit, and response outcomes should be verified.

## Initial Approach

Corvus will start with **Wazuh as its first security backend**. Wazuh will provide collection and detection infrastructure; Corvus will focus on investigation and response orchestration.

- **Integrate, do not fork:** Keep Corvus independent of Wazuh through a backend adapter.
- **Reuse detection infrastructure:** Use existing Wazuh rules before considering a custom detection engine.
- **Investigate beyond the alert:** Query relevant non-alert telemetry, not just the triggering events.
- **Start read-only:** Validate investigation quality before enabling response actions.
- **Evaluate reproducibly:** Combine a controlled endpoint lab with compatible dataset replay and separate ground truth.

Wazuh uses its own decoders and XML-based rules. Native Sigma execution is not assumed or required for the initial milestone.

## Planned Architecture

```text
Lab endpoints / compatible dataset replay
                    |
            Wazuh collection and detection
                    |
       Indexed alerts + searchable telemetry
                    |
              Wazuh adapter
                    |
                  Corvus
          Investigation and context tools
                    |
         Evidence-backed findings
                    |
        Response policy and approval
                    |
         Restricted action executor
                    |
       Post-action verification
```

Searchable alerts do not automatically provide all the evidence an investigation needs. Collection, retention, and search access for relevant non-alert telemetry must be configured and validated. The exact evidence-storage topology is still an open design decision.

## First Milestone

Investigate **suspicious PowerShell execution** in an isolated Windows lab using an alert and the available surrounding telemetry.

The first workflow should:

1. Retrieve the alert and its supporting events.
2. Inspect process ancestry, authentication context, and related activity where available.
3. Consider legitimate explanations and identify missing evidence.
4. Produce an evidence-backed disposition and response recommendation.
5. Distinguish supported malicious activity, likely benign activity, and inconclusive cases.

Tests will include malicious behavior, legitimate administrative lookalikes, missing telemetry, and related activity across alerts or hosts.

## Safety Principles

Autonomy must be bounded by policy, not granted implicitly to the model.

- Treat logs, command lines, and external content as untrusted evidence—not instructions.
- Enforce permissions and action validation outside the model.
- Allow only explicitly authorized response actions with validated targets.
- Require approval for disruptive actions unless narrowly authorized by policy.
- Maintain an audit trail of evidence, decisions, approvals, and actions.
- Keep action recommendation, authorization, execution, and verification distinct.

An accepted action request is not proof of containment. Live response testing belongs in an isolated, authorized environment and follows read-only investigation and simulated response testing.

## Roadmap

- [ ] Provision the Wazuh lab and validate telemetry coverage.
- [ ] Define alert, evidence, and investigation contracts.
- [ ] Implement the read-only Wazuh adapter and investigation tools.
- [ ] Build the first evidence-backed investigation workflow.
- [ ] Add repeatable scenarios and a ground-truth evaluation harness.
- [ ] Introduce simulated response with policy and approval checks.
- [ ] Test a narrowly scoped live response with independent verification.
- [ ] Expand scenario coverage and validate a second security backend.

A custom SIEM, unrestricted autonomous response, and production deployment are outside the initial scope.

## Documentation

- [Architecture — living draft](docs/architecture.md) — component boundaries, data flow, integration contracts, state, safety, and evolving technical decisions.
- [Initial architecture and implementation plan](docs/initial-plan.md) — design decisions, telemetry strategy, integration contracts, milestones, evaluation, and open questions.

## Getting Started

Start with the [initial plan](docs/initial-plan.md). The application stack, deployment configuration, model provider, and runtime interfaces have not yet been selected; installation and execution instructions will be added with the implementation.
