import type { AttemptDetail } from "@/lib/investigations";

const names = {
  plan: "Analyst planning",
  correlation: "Correlation",
  intel: "Intel",
  assessment: "Analyst assessment",
};
export function InvestigationActivity({ attempt }: { attempt: AttemptDetail }) {
  if (attempt.workflow !== "agentic") return null;
  return (
    <section
      className="investigation-activity"
      aria-label="Investigation activity"
    >
      <div className="activity-heading">
        <strong>Investigation activity</strong>
        <span>
          {attempt.steps?.filter((step) => step.model_request).length ?? 0} / 3
          requests started
        </span>
      </div>
      {attempt.steps?.length ? (
        <ol>
          {attempt.steps.map((step) => (
            <li key={step.id}>
              <span>{names[step.phase]}</span>
              <strong>{step.state}</strong>
              {step.error_code && (
                <small>{step.error_code.replaceAll("_", " ")}</small>
              )}
              {!step.model_request && step.state === "completed" && (
                <small>
                  {step.phase === "correlation"
                    ? Array.isArray(step.output?.matches)
                      ? step.output.matches.length
                      : 0
                    : Array.isArray(step.output?.indicators)
                      ? step.output.indicators.length
                      : 0}{" "}
                  {step.phase === "correlation"
                    ? "relationship hints"
                    : "indicators"}
                </small>
              )}
            </li>
          ))}
        </ol>
      ) : (
        <p className="muted">
          Waiting for approval. No planning or model request has started.
        </p>
      )}
      <p className="muted">
        Selected evidence only. No tool can fetch new evidence or authorize a
        response.
      </p>
    </section>
  );
}
