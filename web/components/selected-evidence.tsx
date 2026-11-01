import type { AttemptDetail, Evidence } from "@/lib/investigations";
import { DocumentFacts, EvidenceFacts } from "./evidence-facts";

export function SelectedEvidence({
  attempt,
  evidence,
}: {
  attempt: AttemptDetail;
  evidence: Evidence;
}) {
  const selection = evidence.scope.context_selection as
    | {
        collected_events: number;
        selected_events: number;
        omitted_events: number;
        excerpted_documents: number;
        original_bytes: number;
      }
    | undefined;
  const selectedBytes = new TextEncoder().encode(
    JSON.stringify(evidence),
  ).length;
  return (
    <div className="selected-evidence">
      <div className="context-summary">
        <div>
          <strong>{evidence.events.length + 1}</strong>
          <span>Selected documents</span>
        </div>
        <div>
          <strong>{Math.ceil(selectedBytes / 1024)} KiB</strong>
          <span>Selected evidence · not token count</span>
        </div>
        <div>
          <strong>{evidence.gaps.length}</strong>
          <span>Recorded evidence gaps</span>
        </div>
      </div>
      {selection && (
        <p className="muted">
          Collected {selection.collected_events} context events; selected{" "}
          {selection.selected_events}. Omitted {selection.omitted_events}{" "}
          events; {selection.excerpted_documents} documents contain explicit
          excerpts or field omissions. Original evidence retained locally (
          {Math.ceil(selection.original_bytes / 1024)} KiB). Selection is not
          redaction.
        </p>
      )}
      {evidence.gaps.map((gap, i) => (
        <p key={i} className="collection-gap">
          <strong>{gap.code}</strong> · {gap.message}
        </p>
      ))}
      <details className="saved-evidence">
        <summary>Review evidence selected for Analyst</summary>
        <h4>Triggering alert</h4>
        <DocumentFacts document={evidence.alert} />
        <h4>Supporting events</h4>
        {evidence.events.map((document, i) => (
          <details key={i}>
            <summary>
              {String(document.context.timestamp ?? "Timestamp unavailable")} ·{" "}
              {String(document.context.event_id ?? "Event")} ·{" "}
              {document.reference.id}
            </summary>
            <DocumentFacts document={document} />
          </details>
        ))}
        <details>
          <summary>Collection scope and limitations</summary>
          <EvidenceFacts value={evidence.scope} />
          <ul>
            {evidence.limitations.map((text, i) => (
              <li key={i}>{text}</li>
            ))}
          </ul>
        </details>
        <details>
          <summary>Technical input · selected JSON and prompt</summary>
          {attempt.prepared_input_reconstructed && (
            <p className="muted">
              Historical input reconstructed using the current prompt. The
              original attempt's prompt version is retained in provenance; its
              exact prompt text was not saved.
            </p>
          )}
          <pre>{JSON.stringify(attempt.prepared_input, null, 2)}</pre>
        </details>
      </details>
    </div>
  );
}
