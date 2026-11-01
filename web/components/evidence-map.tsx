"use client";

import { useState } from "react";
import type { Citation, Evidence, Report } from "@/lib/investigations";
import { DocumentFacts, EvidenceFacts } from "./evidence-facts";

export function resolveCitation(
  citation: Citation,
  evidence: Evidence,
): unknown {
  if ("path" in citation) {
    if (citation.collection_id !== evidence.collection_id) return null;
    const [field, index] = citation.path.slice(1).split("/");
    if (!["status", "scope", "queries", "gaps", "limitations"].includes(field))
      return null;
    const value = evidence[field as keyof Evidence];
    return index === undefined
      ? value
      : Array.isArray(value)
        ? value[Number(index)]
        : null;
  }
  return [evidence.alert, ...evidence.events].find(
    ({ reference }) =>
      reference.backend === citation.backend &&
      reference.index === citation.index &&
      reference.id === citation.id,
  );
}
export function CitationFacts({
  citation,
  evidence,
}: {
  citation: Citation;
  evidence: Evidence;
}) {
  const value = resolveCitation(citation, evidence);
  if (!value)
    return <p>Reference unavailable in the saved selected evidence.</p>;
  return "path" in citation ? (
    <EvidenceFacts value={value} />
  ) : (
    <DocumentFacts document={value as Evidence["alert"]} />
  );
}
export function citationLabel(citation: Citation) {
  return "path" in citation
    ? `Collection ${citation.path}`
    : `${citation.backend} · ${citation.id}`;
}
export function EvidenceMap({
  report,
  evidence,
}: {
  report: Report;
  evidence: Evidence;
}) {
  const [index, setIndex] = useState(0);
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const finding = report.findings[index];
  const citations = finding.citations.slice(page * 6, page * 6 + 6);
  const height = Math.max(200, citations.length * 90);
  return (
    <section className="evidence-map" aria-label="Interactive evidence map">
      <div className="map-heading">
        <div>
          <h3>Evidence map</h3>
          <p>
            Explore a finding and its exact citations. Connections mean “cited
            by”, not causation or proven entailment.
          </p>
        </div>
        <span className="plain-tag">{report.findings.length} findings</span>
      </div>
      <div className="finding-tabs" role="group" aria-label="Choose finding">
        {report.findings.map((item, i) => (
          <button
            key={item.id}
            aria-pressed={i === index}
            onClick={() => {
              setIndex(i);
              setPage(0);
              setSelected(null);
            }}
          >
            {item.id}
            <small>{item.kind}</small>
          </button>
        ))}
      </div>
      <div className="evidence-canvas" style={{ height }}>
        <svg aria-hidden="true" width="100%" height={height}>
          {citations.map((_, i) => (
            <line
              key={i}
              x1="40%"
              y1={height / 2}
              x2="60%"
              y2={i * 90 + 45}
              className={selected === i ? "selected" : ""}
            />
          ))}
        </svg>
        <button
          className={`graph-node finding-node ${finding.kind}`}
          style={{ top: height / 2 - 36 }}
          aria-label={`Finding ${finding.id}`}
          onClick={() => setSelected(null)}
        >
          <strong>
            {finding.id} · {finding.kind}
          </strong>
          <span>{finding.statement}</span>
        </button>
        {citations.map((citation, i) => (
          <button
            key={i}
            className={`graph-node evidence-node ${selected === i ? "selected" : ""}`}
            style={{ top: i * 90 + 9 }}
            aria-label={`Open evidence ${citationLabel(citation)}`}
            onClick={() => setSelected(i)}
          >
            <strong>
              {"path" in citation ? "Collection fact" : "Source event"}
            </strong>
            <span>{citationLabel(citation)}</span>
          </button>
        ))}
      </div>
      {finding.citations.length > 6 && (
        <div className="map-pagination">
          <button
            className="button secondary"
            disabled={!page}
            onClick={() => {
              setPage(page - 1);
              setSelected(null);
            }}
          >
            Previous citations
          </button>
          <span>
            {page * 6 + 1}–{page * 6 + citations.length} of{" "}
            {finding.citations.length}
          </span>
          <button
            className="button secondary"
            disabled={(page + 1) * 6 >= finding.citations.length}
            onClick={() => {
              setPage(page + 1);
              setSelected(null);
            }}
          >
            Next citations
          </button>
        </div>
      )}
      <div className="map-inspector" aria-live="polite">
        {selected === null ? (
          <>
            <h4>
              {finding.id} ·{" "}
              {finding.kind === "observation"
                ? "Direct observation"
                : "Analyst interpretation"}
            </h4>
            <p>{finding.statement}</p>
            <p className="muted">
              Select a connected evidence node to inspect its source facts.
            </p>
          </>
        ) : (
          <CitationFacts citation={citations[selected]} evidence={evidence} />
        )}
      </div>
    </section>
  );
}
