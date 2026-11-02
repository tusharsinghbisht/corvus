"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, time } from "@/lib/api";
import type { ReviewDecision, ReviewPage, ReportReview } from "@/lib/reviews";
import { ReviewBadge } from "./review-badge";

function ReviewEntry({ review }: { review: ReportReview }) {
  return (
    <article className="review-entry">
      <div className="review-entry-heading">
        <ReviewBadge status={review.decision} />
        <span>
          {review.reviewer} · {time(review.created_at)} · #{review.sequence}
        </span>
      </div>
      <p className="review-note">{review.note}</p>
      <p className="muted">
        Evidence attestation:{" "}
        {review.evidence_checked
          ? "cited evidence and gaps checked"
          : "not attested"}
        . Integrity revalidation {review.revalidation.validation_version}:{" "}
        {review.revalidation.valid ? "passed" : "failed"}. This does not prove
        narrative accuracy.
      </p>
    </article>
  );
}
function ReviewHistory({
  endpoint,
  initial,
}: {
  endpoint: string;
  initial: ReviewPage;
}) {
  const [rows, setRows] = useState<ReportReview[]>(initial.reviews);
  const [cursor, setCursor] = useState(initial.next_before);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function more() {
    if (cursor === null || busy) return;
    setBusy(true);
    setError("");
    try {
      const page = await api<ReviewPage>(`${endpoint}?before=${cursor}`);
      setRows((previous) => [...previous, ...page.reviews]);
      setCursor(page.next_before);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Review history unavailable",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="review-history">
      <summary>
        Review history · {initial.total}{" "}
        {initial.total === 1 ? "decision" : "decisions"}
      </summary>
      {rows.map((row) => (
        <ReviewEntry key={row.id} review={row} />
      ))}
      {!rows.length && <p>No human assessment decision has been recorded.</p>}
      {error && <p role="alert">{error}</p>}
      {cursor !== null && (
        <button
          className="button secondary"
          disabled={busy}
          onClick={() => void more()}
        >
          Load earlier reviews
        </button>
      )}
    </details>
  );
}
export function ReportReviewPanel({
  alertId,
  attemptId,
  data,
  onSaved,
  onReload,
}: {
  alertId: string;
  attemptId: string;
  data: ReviewPage;
  onSaved: (page: ReviewPage) => void;
  onReload: () => void;
}) {
  const router = useRouter();
  const [decision, setDecision] = useState<ReviewDecision | "">("");
  const [note, setNote] = useState("");
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const endpoint = `/alerts/${alertId}/investigations/${attemptId}/reviews`;
  const latest = data.latest_matches_report ? data.latest : null;
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!decision || !data.target || busy) return;
    setBusy(true);
    setError("");
    setSaved(false);
    try {
      const page = await api<ReviewPage>(endpoint, {
        method: "POST",
        body: JSON.stringify({
          analysis_id: data.target.analysis_id,
          evidence_digest: data.target.evidence_digest,
          report_digest: data.target.report_digest,
          decision,
          note,
          evidence_checked: checked,
          expected_sequence: data.current_sequence,
        }),
      });
      onSaved(page);
      setDecision("");
      setNote("");
      setChecked(false);
      setSaved(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401)
        router.replace("/login");
      else
        setError(
          err instanceof Error
            ? err.message
            : "Review save could not be confirmed. Reload history before trying again.",
        );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section
      id={`human-review-${attemptId}`}
      className="human-review"
      aria-label="Human assessment review"
    >
      <div className="review-heading">
        <div>
          <h3>Human review</h3>
          <p>
            Decide whether this assessment is supported—not whether the incident
            is resolved.
          </p>
        </div>
        <ReviewBadge
          status={latest?.decision ?? "pending"}
          stale={!!data.latest && !data.latest_matches_report}
        />
      </div>
      {data.latest && !data.latest_matches_report && (
        <p className="notice error">
          The earlier decision belongs to a different report snapshot. It does
          not accept this assessment.
        </p>
      )}
      {latest ? (
        <ReviewEntry review={latest} />
      ) : (
        <p className="muted">
          This model report has not received a current human assessment
          decision.
        </p>
      )}
      {saved && (
        <p role="status" className="notice success">
          Human review recorded. No model call, incident closure, or response
          action was triggered.
        </p>
      )}
      {error && (
        <div role="alert" className="notice error">
          {error}
          <button
            className="button secondary"
            onClick={() => {
              setChecked(false);
              setError("");
              onReload();
            }}
          >
            Reload report and review history
          </button>
        </div>
      )}
      {data.target && (
        <form className="review-form" onSubmit={(event) => void submit(event)}>
          <fieldset>
            <legend>
              {data.latest
                ? "Record a superseding decision"
                : "Review this assessment"}
            </legend>
            <div className="review-decisions">
              {(["accepted", "rejected", "follow_up"] as ReviewDecision[]).map(
                (value) => (
                  <label key={value}>
                    <input
                      type="radio"
                      name={`review-${attemptId}`}
                      checked={decision === value}
                      onChange={() => {
                        setDecision(value);
                        setSaved(false);
                      }}
                    />
                    {value === "accepted"
                      ? "Accept assessment"
                      : value === "rejected"
                        ? "Reject assessment"
                        : "Needs follow-up"}
                  </label>
                ),
              )}
            </div>
          </fieldset>
          <label>
            Review rationale
            <textarea
              aria-label="Review rationale"
              rows={4}
              minLength={10}
              maxLength={2000}
              value={note}
              onChange={(event) => {
                setNote(event.target.value);
                setSaved(false);
              }}
              placeholder="Which claims are supported or incorrect? What follow-up is needed?"
              required
            />
          </label>
          <p className="form-hint">
            {note.trim().length}/2000 characters · minimum 10. Check PID vs
            GUID, attempted vs completed actions, network/persistence claims,
            and legitimate alternatives. Notes stay in Corvus and are not sent
            to the Analyst.
          </p>
          <label className="review-attestation">
            <input
              type="checkbox"
              checked={checked}
              onChange={(event) => setChecked(event.target.checked)}
            />
            I checked the cited evidence, uncertainties, and alternative
            explanations. Required to accept an assessment.
          </label>
          <div className="review-submit">
            <button
              className="button secondary"
              disabled={
                busy ||
                !decision ||
                note.trim().length < 10 ||
                (decision === "accepted" && !checked)
              }
              type="submit"
            >
              {busy ? "Saving review…" : "Save human review"}
            </button>
            <p>
              Every decision is preserved. Acceptance does not authorize
              containment or mark an incident resolved.
            </p>
          </div>
        </form>
      )}
      <ReviewHistory
        key={`${attemptId}-${data.current_sequence}-${data.target?.report_digest}`}
        endpoint={endpoint}
        initial={data}
      />
      <details>
        <summary>Review binding · exact assessment and evidence</summary>
        <dl className="evidence-facts">
          <div>
            <dt>Analysis ID</dt>
            <dd>{data.target?.analysis_id ?? "Unavailable"}</dd>
          </div>
          <div>
            <dt>Report SHA-256</dt>
            <dd>{data.target?.report_digest ?? "Unavailable"}</dd>
          </div>
          <div>
            <dt>Evidence SHA-256</dt>
            <dd>{data.target?.evidence_digest ?? "Unavailable"}</dd>
          </div>
          <div>
            <dt>Generation validator</dt>
            <dd>{data.target?.validator_version ?? "Unavailable"}</dd>
          </div>
        </dl>
      </details>
    </section>
  );
}
