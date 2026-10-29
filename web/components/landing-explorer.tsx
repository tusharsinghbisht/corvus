"use client";

import { useState } from "react";
import {
  ArrowDown,
  ArrowRight,
  Braces,
  Database,
  FileCheck2,
  Layers3,
  ListChecks,
  LockKeyhole,
  Network,
  Radio,
  ScanLine,
} from "lucide-react";

const flows = {
  ingestion: {
    label: "Live ingestion",
    description:
      "A source-preserving path from Wazuh to your queue. This is running in the live workspace.",
    nodes: [
      {
        name: "Wazuh",
        subtitle: "Detection source",
        icon: Radio,
        detail:
          "Wazuh owns detection and telemetry retention. Corvus reads alert indices across agents and rule levels without changing rules or endpoint configuration.",
      },
      {
        name: "Adapter",
        subtitle: "Read-only boundary",
        icon: Network,
        detail:
          "The Python adapter translates backend records into normalized context while keeping native index/document references and the original source payload.",
      },
      {
        name: "Worker",
        subtitle: "Checkpointed ingestion",
        icon: Layers3,
        detail:
          "Overlapping bounded windows, idempotent inserts, and transactional checkpoints make retries inspectable. Incomplete queries do not silently advance the checkpoint.",
      },
      {
        name: "PostgreSQL",
        subtitle: "Durable records",
        icon: Database,
        detail:
          "Normalized columns support filtering and time-window queries. JSONB preserves the full alert. Connections, sessions, and audit events live alongside the operational record.",
      },
      {
        name: "Workspace",
        subtitle: "Authenticated review",
        icon: LockKeyhole,
        detail:
          "Next.js presents the queue through authenticated Python APIs. Operators can filter alerts, inspect source documents, and see connection health and backfill progress.",
      },
    ],
  },
  analyst: {
    label: "Analyst pipeline",
    description:
      "The read-only Analyst engine is implemented. Connecting investigations to the dashboard is the next integration.",
    nodes: [
      {
        name: "Select",
        subtitle: "Operator intent",
        icon: ScanLine,
        detail:
          "Choose a real alert and explicitly approve external processing of the selected evidence. Ingestion alone does not trigger a model call.",
      },
      {
        name: "Collect",
        subtitle: "Bounded context",
        icon: Layers3,
        detail:
          "Retrieve surrounding activity and process-GUID ancestry through the adapter. Preserve source references, query scope, truncation, and missing-evidence gaps.",
      },
      {
        name: "Analyze",
        subtitle: "Azure Foundry",
        icon: Braces,
        detail:
          "One request to the configured DeepSeek-V4-Flash deployment produces a structured advisory report. The model has no endpoint tools and executes no response actions.",
      },
      {
        name: "Validate",
        subtitle: "Report integrity",
        icon: FileCheck2,
        detail:
          "Check schema, evidence binding, citations, timeline references, and basic recommendation safety. Invalid candidates are retained rather than silently repaired.",
      },
      {
        name: "Review",
        subtitle: "Human judgment",
        icon: ListChecks,
        detail:
          "Inspect observations, inferences, alternative explanations, and uncertainty. Passing reference checks does not prove a narrative claim is supported.",
      },
    ],
  },
};

export function ArchitectureExplorer() {
  const [flow, setFlow] = useState<keyof typeof flows>("ingestion");
  const [selected, setSelected] = useState(0);
  const current = flows[flow];
  const node = current.nodes[selected];
  return (
    <div className="architecture-explorer glass-panel">
      <div className="explorer-toolbar">
        <div
          className="segmented-control"
          role="group"
          aria-label="Explore data flow"
        >
          {(Object.keys(flows) as (keyof typeof flows)[]).map((key) => (
            <button
              key={key}
              aria-pressed={flow === key}
              onClick={() => {
                setFlow(key);
                setSelected(0);
              }}
            >
              {flows[key].label}
            </button>
          ))}
        </div>
        <span className="explorer-caption">CLICK A STAGE TO EXPLORE</span>
      </div>
      <p className="explorer-intro">{current.description}</p>
      <div className="architecture-flow">
        {current.nodes.map((item, index) => {
          const Icon = item.icon;
          return (
            <div className="architecture-step" key={item.name}>
              <button
                aria-pressed={index === selected}
                onClick={() => setSelected(index)}
              >
                <span className="architecture-icon">
                  <Icon size={23} />
                </span>
                <strong>{item.name}</strong>
                <span>{item.subtitle}</span>
              </button>
              {index < current.nodes.length - 1 && (
                <ArrowRight
                  className="flow-arrow"
                  size={19}
                  aria-hidden="true"
                />
              )}
            </div>
          );
        })}
      </div>
      <div className="architecture-detail" aria-live="polite">
        <span className="detail-index">0{selected + 1}</span>
        <div>
          <h3>
            {node.name}
            <ArrowDown size={16} />
          </h3>
          <p>{node.detail}</p>
        </div>
      </div>
    </div>
  );
}

export function AnalystModes() {
  const [mode, setMode] = useState<"manual" | "auto">("manual");
  return (
    <div className="mode-explorer glass-panel">
      <div className="mode-switch">
        <div
          className="segmented-control"
          role="group"
          aria-label="Explore Analyst operating modes"
        >
          <button
            aria-pressed={mode === "manual"}
            onClick={() => setMode("manual")}
          >
            Manual
          </button>
          <button
            aria-pressed={mode === "auto"}
            onClick={() => setMode("auto")}
          >
            Automatic
          </button>
        </div>
        <span className="availability-tag">
          {mode === "manual"
            ? "Analyst core available · dashboard next"
            : "Planned · not enabled"}
        </span>
      </div>
      <div className="mode-content" aria-live="polite">
        <div>
          <span className="eyebrow">
            {mode === "manual"
              ? "YOU CHOOSE THE STARTING POINT"
              : "EXPLICIT SCOPE, EXPLICIT LIMITS"}
          </span>
          <h3>
            {mode === "manual"
              ? "Investigate deliberately."
              : "Automate the handoff. Not the authority."}
          </h3>
          <p>
            {mode === "manual"
              ? "Choose an alert, review the evidence-processing boundary, and request an investigation. The Analyst gathers scoped context and returns a report for review."
              : "The planned automatic mode will enqueue only eligible new alerts after a connection is explicitly opted in. Severity thresholds and request budgets will limit what gets processed."}
          </p>
        </div>
        <ol>
          {(mode === "manual"
            ? [
                "Select a real alert",
                "Approve selected evidence processing",
                "Collect context and analyze",
                "Review findings and uncertainty",
              ]
            : [
                "Explicitly enable per connection",
                "Set eligibility and request limits",
                "Queue eligible new alerts only",
                "Keep human review and audit history",
              ]
          ).map((item, index) => (
            <li key={item}>
              <span>0{index + 1}</span>
              {item}
            </li>
          ))}
        </ol>
      </div>
      <p className="mode-footnote">
        These controls explain the workflow; they do not change your connection
        settings or send evidence anywhere.
      </p>
    </div>
  );
}
