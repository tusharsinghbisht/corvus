import type { AttemptDetail } from "@/lib/investigations";

export function InvestigationFailure({ attempt }: { attempt: AttemptDetail }) {
  const response = attempt.provenance?.response;
  const reason = response?.finish_reason ?? attempt.model_reply?.finish_reason;
  const tokens =
    response?.usage.completion_tokens ??
    attempt.model_reply?.usage.completion_tokens;
  const limit = attempt.provenance?.max_tokens;
  const incomplete = attempt.error_code === "incomplete_model_response";
  let explanation =
    "This attempt could not complete. Inspect its preserved evidence and provenance before requesting another attempt.";
  if (incomplete) {
    if (reason === "length") {
      explanation =
        "The model reached the configured output-token limit before finishing. No report was accepted.";
    } else if (reason === "content_filter") {
      explanation =
        "The provider stopped the response through content filtering. No report was accepted; increasing the token limit is not a remedy for filtering.";
    } else if (
      !reason &&
      typeof tokens === "number" &&
      typeof limit === "number" &&
      tokens >= limit
    ) {
      // Older attempts did not save finish_reason. Do not invent it retroactively.
      explanation =
        "The reply used the full output-token budget and did not finish normally. No report was accepted; the original finish reason was not recorded.";
    } else {
      explanation =
        "The provider returned a response without normal completion. No report was accepted.";
    }
  }
  return (
    <div className="notice error" role="alert">
      <div>
        <strong>
          {incomplete
            ? "Incomplete Analyst response"
            : "Investigation attempt failed"}
        </strong>
        <p>{explanation}</p>
        {typeof tokens === "number" && (
          <p>
            Output tokens used: {tokens.toLocaleString()}
            {typeof limit === "number"
              ? ` / ${limit.toLocaleString()} allowed for this attempt`
              : ""}
            .
          </p>
        )}
        {incomplete && attempt.model_reply && (
          <p>
            The partial model reply is preserved below. It is not a validated
            assessment.
          </p>
        )}
        <p>
          {attempt.request_started_at
            ? "This request may have incurred a charge. No automatic retry is made; a new attempt requires fresh evidence approval."
            : "No model request was started. A new attempt must be requested explicitly."}
        </p>
        <small>
          Failure code: {attempt.error_code}
          {reason ? ` · Finish reason: ${reason}` : ""}
        </small>
      </div>
    </div>
  );
}
