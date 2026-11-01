import type { EvidenceDocument } from "@/lib/investigations";

function label(value: string) {
  return value.replaceAll("_", " ").replace(/([a-z])([A-Z])/g, "$1 $2");
}
function rows(value: unknown, path = "", depth = 0): [string, string][] {
  if (value == null || value === "") return [];
  if (typeof value !== "object") return [[label(path), String(value)]];
  if (depth > 8)
    return [[label(path), "Nested detail available in the technical record"]];
  return Object.entries(value).flatMap(([key, item]) =>
    rows(item, path ? `${path} › ${key}` : key, depth + 1),
  );
}
export function EvidenceFacts({ value }: { value: unknown }) {
  const fields = rows(value);
  return fields.length ? (
    <dl className="evidence-facts">
      {fields.map(([name, text], i) => (
        <div key={i}>
          <dt>{name}</dt>
          <dd>{text}</dd>
        </div>
      ))}
    </dl>
  ) : (
    <p className="muted">No additional facts were recorded.</p>
  );
}
export function DocumentFacts({ document }: { document: EvidenceDocument }) {
  return (
    <div className="document-facts">
      <p className="evidence-reference">
        {document.reference.backend} / {document.reference.index} /{" "}
        {document.reference.id}
      </p>
      <h4>Event facts</h4>
      <EvidenceFacts value={document.context} />
      <details>
        <summary>Supporting source fields · untrusted evidence</summary>
        <EvidenceFacts value={document.source} />
      </details>
    </div>
  );
}
