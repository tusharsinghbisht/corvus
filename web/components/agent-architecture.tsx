"use client";

import { useState } from "react";
import {
  ArrowLeft,
  ArrowLeftRight,
  ArrowRight,
  ArrowUpDown,
  CheckCheck,
  Database,
  FileSearch,
  LockKeyhole,
  Network,
  Radio,
  Search,
  ShieldCheck,
} from "lucide-react";

const agents = [
  {
    id: "intake",
    name: "Alert intake",
    role: "Connect and preserve",
    icon: Radio,
    status: "Live",
    detail:
      "The ingestion worker receives detections through the security-backend adapter and preserves their native identity, original source, and receipt time.",
    handoff:
      "Creates the alert record that an investigation can reference. It does not send every incoming alert to a model.",
  },
  {
    id: "correlation",
    name: "Correlation agent",
    role: "Find related activity",
    icon: Network,
    status: "Planned",
    detail:
      "Proposes related alerts using host, user, process identity, and time. Relationships remain evidence-linked hypotheses rather than proof that nearby events share a cause.",
    handoff:
      "Offers related alert/evidence sets to the Analyst. The Analyst can request another scoped correlation pass when the investigation needs it.",
  },
  {
    id: "analyst",
    name: "Analyst agent",
    role: "Own the investigation",
    icon: FileSearch,
    status: "Core available",
    detail:
      "Assesses the triggering alert and supporting evidence, separates observations from inferences, and records findings and uncertainty. The target workflow lets it request scoped correlation or intel work when needed.",
    handoff:
      "Combines evidence-linked results into an advisory assessment. A response recommendation goes to the policy/approval boundary, never straight to an executor. Today the core is single-pass; these agent handoffs are not running yet.",
  },
  {
    id: "intel",
    name: "Intel agent",
    role: "Enrich on request",
    icon: Search,
    status: "Planned",
    detail:
      "Returns sourced, time-aware context about indicators and observed behavior. Reputation and threat-intelligence matches are signals to investigate, not automatic proof of malicious activity.",
    handoff:
      "Answers the Analyst's bounded enrichment requests and returns references, freshness, and uncertainty. External lookups require an explicit data-processing policy; this role has no containment authority.",
  },
  {
    id: "policy",
    name: "Policy & approval",
    role: "Code and human authority",
    icon: ShieldCheck,
    status: "Planned",
    detail:
      "A code-enforced boundary checks the proposed action, exact target, evidence, permissions, and approval requirements. It is not another model that can approve its own recommendations.",
    handoff:
      "Only a validated, approved action plan may reach the Containment agent. Automatic triage does not imply automatic response permission.",
  },
  {
    id: "containment",
    name: "Containment agent",
    role: "Execute a scoped plan",
    icon: LockKeyhole,
    status: "Planned",
    detail:
      "Executes only the allowed action and target in an approved plan through a restricted response adapter. Its credentials are separate from the read-only investigation account.",
    handoff:
      "Records the attempt and backend result, then requests independent verification. A successful API acknowledgment is not a claim that containment worked.",
  },
  {
    id: "verification",
    name: "Verification agent",
    role: "Check the outcome",
    icon: CheckCheck,
    status: "Planned",
    detail:
      "Checks fresh telemetry and defined postconditions after an action. It distinguishes verified success, failure, and an unknown outcome instead of trusting the executor's acknowledgment.",
    handoff:
      "Returns outcome evidence to the Analyst and shared case record. Follow-up or rollback still passes through policy and approval; closure is not inferred from silence.",
  },
] as const;

export function AgentArchitecture() {
  const [selected, setSelected] = useState<string>("analyst");
  const active = agents.find((agent) => agent.id === selected)!;
  return (
    <div className="agent-architecture glass-panel">
      <div className="agent-map-heading">
        <div>
          <span className="eyebrow">TARGET SOC WORKFLOW</span>
          <h3>One investigation. Scoped specialists.</h3>
        </div>
        <span className="availability-tag">
          LangGraph orchestration · planned
        </span>
      </div>
      <p className="agent-availability">
        Ingestion is live and the single-pass Analyst core is available.
        Correlation, intel, response orchestration, containment, and
        verification are planned—not active agents in the current deployment.
      </p>
      <div
        className="agent-map"
        role="group"
        aria-label="Explore the target SOC agent architecture"
      >
        {agents.map((agent) => {
          const Icon = agent.icon;
          return (
            <div key={agent.id} className={`agent-stage agent-${agent.id}`}>
              <button
                aria-pressed={selected === agent.id}
                onClick={() => setSelected(agent.id)}
              >
                <span className="agent-icon">
                  <Icon size={22} />
                </span>
                <strong>{agent.name}</strong>
                <span className="agent-role">{agent.role}</span>
                <span
                  className={`agent-status ${agent.status === "Planned" ? "planned" : "available"}`}
                >
                  {agent.status}
                </span>
              </button>
              {agent.id === "intel" ? (
                <ArrowUpDown
                  className="agent-branch-arrow"
                  size={18}
                  aria-hidden="true"
                />
              ) : agent.id === "correlation" ? (
                <ArrowLeftRight
                  className="agent-arrow"
                  size={17}
                  aria-hidden="true"
                />
              ) : (
                agent.id !== "verification" && (
                  <ArrowRight
                    className="agent-arrow"
                    size={17}
                    aria-hidden="true"
                  />
                )
              )}
            </div>
          );
        })}
        <div className="agent-map-annotation">
          <span>ENRICHMENT IS A BRANCH, NOT AUTHORITY.</span>
          <p>
            The Analyst requests intel and receives evidence-linked results.
            Intel does not choose or execute a response.
          </p>
          <div>
            <ArrowLeft size={15} />
            Verification returns outcome evidence to the Analyst and case.
          </div>
        </div>
      </div>
      <div className="agent-case-store">
        <Database size={18} />
        <div>
          <strong>Shared case & evidence record</strong>
          <span>
            Structured tasks, source references, findings, approvals, and
            outcomes—not free-form agent commands.
          </span>
        </div>
        <small>
          Alert/audit storage is live.
          <br />
          Shared case orchestration is planned.
        </small>
      </div>
      <div className="agent-details" aria-live="polite">
        <div>
          <h3>{active.name}</h3>
          <span className="availability-tag">{active.status}</span>
        </div>
        <p>{active.detail}</p>
        <div className="agent-handoff">
          <span>HANDOFF</span>
          <p>{active.handoff}</p>
        </div>
      </div>
    </div>
  );
}
