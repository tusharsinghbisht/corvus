import type { Citation, Evidence, Report } from "@/lib/investigations";

function resolve(citation: Citation, evidence: Evidence) {
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

function Citations({
  citations,
  evidence,
}: {
  citations: Citation[];
  evidence: Evidence;
}) {
  return (
    <div className="citations">
      {citations.map((citation, i) => (
        <details key={i}>
          <summary>
            {"path" in citation
              ? `Collection ${citation.path}`
              : `${citation.backend} / ${citation.index} / ${citation.id}`}
          </summary>
          <pre>
            {JSON.stringify(
              resolve(citation, evidence) ??
                "Reference unavailable in saved evidence",
              null,
              2,
            )}
          </pre>
        </details>
      ))}
    </div>
  );
}

export function InvestigationReport({
  report,
  evidence,
}: {
  report: Report;
  evidence: Evidence;
}) {
  return (
    <div className="investigation-report">
      <div className="notice">
        Advisory model disposition: {report.disposition.replaceAll("_", " ")}.
        Not a human verdict, incident resolution, or authorization to act. Valid
        citations do not prove the claims follow from evidence.
      </div>
      <h3>Assessment</h3>
      <p>{report.summary}</p>
      <p className="muted">
        Summary findings: {report.summary_finding_ids.join(", ")}
      </p>
      <h3>Findings</h3>
      {report.findings.map((finding) => (
        <article className="finding" key={finding.id}>
          <h4>
            {finding.id} · {finding.kind}
          </h4>
          <p>{finding.statement}</p>
          <Citations citations={finding.citations} evidence={evidence} />
        </article>
      ))}
      <h3>Uncertainty and evidence gaps</h3>
      {report.uncertainties.length === 0 ? (
        <p>
          No uncertainty recorded by the model. Review collection gaps
          independently.
        </p>
      ) : (
        report.uncertainties.map((gap, i) => (
          <article className="finding" key={i}>
            <h4>{gap.code}</h4>
            <p>{gap.description}</p>
            <p className="muted">Next step: {gap.next_step}</p>
          </article>
        ))
      )}
      <h3>Alternative explanations</h3>
      {report.alternative_explanations.map((alternative, i) => (
        <article className="finding" key={i}>
          <p>{alternative.explanation}</p>
          <p className="muted">{alternative.assessment}</p>
          <Citations citations={alternative.citations} evidence={evidence} />
        </article>
      ))}
      <h3>Advisory recommendations</h3>
      {report.recommendations.map((item, i) => (
        <article className="finding" key={i}>
          <h4>
            {item.category.replaceAll("_", " ")} · {item.finding_ids.join(", ")}
          </h4>
          <p>{item.description}</p>
          <p className="muted">{item.rationale}</p>
        </article>
      ))}
      <details>
        <summary>Timeline and entities</summary>
        {report.timeline.map((item, i) => (
          <article className="finding" key={`t${i}`}>
            <h4>{item.timestamp}</h4>
            <p>{item.description}</p>
            <Citations citations={item.citations} evidence={evidence} />
          </article>
        ))}
        {report.entities.map((item, i) => (
          <article className="finding" key={`e${i}`}>
            <h4>{item.kind}</h4>
            <p>{item.value}</p>
            <Citations citations={item.citations} evidence={evidence} />
          </article>
        ))}
      </details>
      <h3>Limitations</h3>
      <ul>
        {report.limitations.map((text, i) => (
          <li key={i}>{text}</li>
        ))}
      </ul>
    </div>
  );
}
