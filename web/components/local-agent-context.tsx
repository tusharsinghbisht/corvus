import type { AttemptDetail, Evidence } from "@/lib/investigations";

export function LocalAgentContext({
  attempt,
  evidence,
}: {
  attempt: AttemptDetail;
  evidence: Evidence;
}) {
  const selection = evidence.scope.context_selection as
    | { matches?: { reference: Record<string, string>; reason: string }[] }
    | undefined;
  const intel = attempt.local_intel;
  return (
    <details className="local-agent-context" id="local-agent-context">
      <summary>Correlation & Intel · local inspection</summary>
      <p>
        Deterministic read-only stages, not additional model conversations. No
        external lookup or response action.
      </p>
      <section aria-label="Correlation selection">
        <h4>Correlation · why these events</h4>
        {selection?.matches ? (
          selection.matches.length ? (
            <ul>
              {selection.matches.map((match, index) => (
                <li key={index}>
                  <strong>{match.reason}</strong>
                  <span className="evidence-reference">
                    {match.reference.index} / {match.reference.id}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p>
              No supporting event met the focused criteria. The trigger is still
              retained; this does not establish an absence of activity.
            </p>
          )
        ) : (
          <p>
            This historical input predates recorded selection reasons. Its
            original context is preserved, not reinterpreted as a new
            correlation result.
          </p>
        )}
        <p className="muted">
          Matches are selection hints, not verified causation, process ancestry,
          or authorization.
        </p>
      </section>
      <section aria-label="Local indicator intelligence">
        <h4>Intel · structured indicators</h4>
        <p className="muted">
          Computed now from this saved selected input; not a generation-time
          artifact or extra Analyst input.
        </p>
        {intel?.observations.length ? (
          intel.observations.map((item, index) => (
            <article key={index}>
              <strong>
                {item.kind} ·{" "}
                <span className="indicator-value">{item.value}</span>
              </strong>
              <ul>
                {item.facts.map((fact, i) => (
                  <li key={i}>{fact}</li>
                ))}
              </ul>
              <details>
                <summary>
                  Observed source fields · {item.sources.length}
                </summary>
                {item.sources.map((source, i) => (
                  <p key={i} className="evidence-reference">
                    {source.reference.index} / {source.reference.id} ·{" "}
                    {source.path}
                  </p>
                ))}
              </details>
            </article>
          ))
        ) : (
          <p>
            No indicators were found in the inspected structured fields. This is
            not proof of no indicators or benign activity.
          </p>
        )}
        {intel?.truncated && (
          <p className="notice">
            Indicator inspection reached a local bound; results are incomplete.
          </p>
        )}
        <p className="muted">
          No DNS, threat-feed, geolocation, or sandbox request. Address class
          and hash syntax are not reputation verdicts.
        </p>
      </section>
    </details>
  );
}
