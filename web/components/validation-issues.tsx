import type { AttemptDetail } from "@/lib/investigations";

export function ValidationIssues({ attempt }: { attempt: AttemptDetail }) {
  const errors = attempt.result?.validation.errors ?? [];
  const timestampIssue = errors.some(
    (error) =>
      error.code === "schema_violation" &&
      /\/timeline\/\d+\/timestamp/.test(error.path ?? ""),
  );
  return (
    <section className="validation-issues" aria-label="Report integrity issues">
      <h3>Why this candidate was rejected</h3>
      <p>
        The original response is preserved, but it is not presented as findings
        or accepted knowledge. Nothing is repaired or retried automatically.
      </p>
      {timestampIssue && (
        <p className="notice">
          Timeline values did not meet the timestamp contract. New context
          selection canonicalizes indexed timestamps before approval; this saved
          response remains unchanged. A new model request still requires fresh
          approval and may incur a charge.
        </p>
      )}
      <ul>
        {errors.map((error, index) => (
          <li key={index}>
            <strong>{error.code.replaceAll("_", " ")}</strong>
            <span className="evidence-reference">{error.path || "/"}</span>
            <p>{error.message}</p>
          </li>
        ))}
      </ul>
      {!errors.length && (
        <p>
          Inspect the preserved response and technical record for the
          operational failure details.
        </p>
      )}
      <p className="muted">
        Passing these checks would establish integrity, not prove that the
        narrative follows from evidence.
      </p>
    </section>
  );
}
