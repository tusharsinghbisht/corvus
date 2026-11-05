"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, ApiError, time } from "@/lib/api";
import { activeStatuses, statusLabels } from "@/lib/investigations";
import type { Attempt, AttemptDetail, Report } from "@/lib/investigations";
import { InvestigationReport } from "./investigation-report";
import { InvestigationFailure } from "./investigation-failure";
import { SelectedEvidence } from "./selected-evidence";
import { AlertAnalystMode } from "./analyst-policy";
import { EvidenceFacts } from "./evidence-facts";
import { ReportReviewPanel } from "./report-review";
import { ReviewBadge } from "./review-badge";
import { InvestigationExport } from "./investigation-export";
import { ValidationIssues } from "./validation-issues";

export function Investigation({
  alertId,
  connectionId,
  requestedAttemptId,
}: {
  alertId: string;
  connectionId: string;
  requestedAttemptId?: string;
}) {
  const router = useRouter();
  const [attempts, setAttempts] = useState<Attempt[] | null>(null);
  const [selectedId, setSelectedId] = useState(requestedAttemptId ?? "");
  const [detail, setDetail] = useState<AttemptDetail | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [approved, setApproved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const base = `/alerts/${alertId}/investigations`;
  const latestReport = attempts?.find((a) => a.status === "validated");
  const selected =
    attempts?.find((a) => a.id === selectedId) ?? latestReport ?? attempts?.[0];
  const currentId = selected?.id;
  const selectedStatus = selected?.status;
  const activeAttempt = attempts?.find((a) =>
    activeStatuses.includes(a.status),
  );
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const data = await api<{ attempts: Attempt[] }>(base, {
          signal: controller.signal,
        });
        if (!controller.signal.aborted) {
          setAttempts(data.attempts);
          // Pin the viewed assessment while someone is reviewing it.
          setSelectedId(
            (previous) =>
              previous ||
              data.attempts.find((a) => a.status === "validated")?.id ||
              data.attempts[0]?.id ||
              "",
          );
        }
      } catch (err) {
        if (controller.signal.aborted) return;
        if (err instanceof ApiError && err.status === 401)
          router.replace("/login");
        else
          setError(
            err instanceof Error
              ? err.message
              : "Investigation history unavailable",
          );
      }
      if (!controller.signal.aborted) timer = setTimeout(poll, 5000);
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [base, refresh, router]);
  useEffect(() => {
    if (!currentId) return;
    const controller = new AbortController();
    api<AttemptDetail>(`${base}/${currentId}`, { signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted) {
          setDetail(data);
          setApproved(false);
        }
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        if (err instanceof ApiError && err.status === 401)
          router.replace("/login");
        else
          setError(err instanceof Error ? err.message : "Attempt unavailable");
      });
    return () => controller.abort();
  }, [base, currentId, selectedStatus, refresh, router]);
  function selectAttempt(identifier: string, pinInUrl = true) {
    setSelectedId(identifier);
    const url = new URL(window.location.href);
    if (pinInUrl) url.searchParams.set("attempt", identifier);
    else url.searchParams.delete("attempt");
    window.history.replaceState(null, "", url);
  }
  async function act(action: "collect" | "approve" | "cancel") {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      if (action === "collect") {
        const data = await api<{ id: string }>(base, { method: "POST" });
        selectAttempt(data.id, false);
      } else
        await api(`${base}/${currentId}/${action}`, {
          method: "POST",
          ...(action === "approve"
            ? {
                body: JSON.stringify({
                  allow_external: approved,
                  evidence_digest: detail?.evidence_digest,
                }),
              }
            : {}),
        });
      setApproved(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401)
        router.replace("/login");
      else
        setError(
          err instanceof Error
            ? err.message
            : "Request failed. Refresh before trying again.",
        );
    } finally {
      setBusy(false);
      setRefresh((n) => n + 1);
    }
  }
  async function chooseContext(profile: "focused" | "expanded") {
    if (busy || !detail) return;
    setBusy(true);
    setApproved(false);
    setError("");
    try {
      const next = await api<AttemptDetail>(`${base}/${detail.id}/context`, {
        method: "POST",
        body: JSON.stringify({
          profile,
          expected_evidence_digest: detail.evidence_digest ?? null,
        }),
      });
      setDetail(next);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401)
        router.replace("/login");
      else
        setError(
          err instanceof Error ? err.message : "Context selection failed",
        );
    } finally {
      setBusy(false);
      setRefresh((value) => value + 1);
    }
  }
  const visible =
    detail?.id === currentId && detail?.status === selectedStatus
      ? detail
      : null;
  const evidence =
    visible?.error_code === "context_budget_exceeded"
      ? null
      : (visible?.analysis_evidence ?? visible?.evidence);
  const report =
    visible?.result?.status === "validated" && visible.result.validation.valid
      ? (visible.result.report as Report)
      : null;
  const humanReview = visible?.human_review;
  const reviewStatus = humanReview?.latest_matches_report
    ? (humanReview.latest?.decision ?? "pending")
    : "pending";
  return (
    <section
      className="panel investigation-panel"
      aria-label="Analyst investigation"
    >
      <div className="panel-heading investigation-heading">
        <div>
          <div className="eyebrow">READ-ONLY INVESTIGATION AGENT</div>
          <h2>Analyst investigation</h2>
          <p>
            {latestReport
              ? "An advisory report is available. Explore its evidence, interpretation, and uncertainty below."
              : "Turn this detection into an evidence-linked assessment. Context is prepared locally before any manual approval."}
          </p>
        </div>
        <button
          className="button primary"
          disabled={busy || attempts === null || !!activeAttempt}
          onClick={() => void act("collect")}
        >
          Investigate with Analyst
        </button>
      </div>
      <div className="investigation-body">
        <AlertAnalystMode connectionId={connectionId} />
        <div
          className="investigation-steps"
          aria-label="Investigation workflow"
        >
          <span>01 · Review focused evidence</span>
          <span>02 · Approve one request</span>
          <span>03 · Read report & review</span>
        </div>
        {error && (
          <div role="alert" className="notice error">
            {error}
            <button
              className="button secondary"
              onClick={() => {
                setError("");
                setRefresh((n) => n + 1);
              }}
            >
              Refresh state
            </button>
          </div>
        )}
        {activeAttempt && activeAttempt.id !== currentId && (
          <div className="notice">
            Attempt #{activeAttempt.number}:{" "}
            {statusLabels[activeAttempt.status]}.{" "}
            <button
              className="button secondary"
              onClick={() => selectAttempt(activeAttempt.id)}
            >
              Open active attempt
            </button>
          </div>
        )}
        {attempts === null ? (
          <p role="status">Loading investigation history…</p>
        ) : attempts.length === 0 ? (
          <div className="investigation-empty">
            <h3>Not investigated yet</h3>
            <p>
              Choose Investigate with Analyst to collect scoped evidence. A
              manual request will not leave Corvus until you review and approve
              its selected input.
            </p>
            <p className="muted">
              Collection: this agent, ±5 minutes, six-hour process-GUID pivot
              when available, kept locally. By default the Analyst receives only
              the trigger and up to four directly matched supporting events
              within 16 KiB. No nearby-event filler. Broader input is an
              explicit choice before approval.
            </p>
          </div>
        ) : (
          <>
            <p role="status" className="attempt-status">
              {statusLabels[selectedStatus ?? ""] ?? selectedStatus} · attempt #
              {selected?.number}
            </p>
            {visible ? (
              <>
                {visible.error_code && (
                  <InvestigationFailure attempt={visible} />
                )}
                {latestReport && currentId !== latestReport.id && (
                  <button
                    className="button secondary"
                    onClick={() => selectAttempt(latestReport.id, false)}
                  >
                    Show latest report
                  </button>
                )}
                {visible.mode === "automatic" && (
                  <p className="muted">
                    Authorized by connection policy, not a per-alert manual
                    click. <Link href="/soc/settings">Review policy →</Link>
                  </p>
                )}
                {report && evidence && (
                  <>
                    <div className="report-label">
                      <span className="plain-tag">
                        Report passed integrity checks
                      </span>
                      <span>Generated {time(visible.completed_at)}</span>
                      <ReviewBadge
                        status={reviewStatus}
                        stale={
                          !!humanReview?.latest &&
                          !humanReview.latest_matches_report
                        }
                      />
                      {humanReview?.target && (
                        <button
                          className="review-jump"
                          onClick={() =>
                            document
                              .getElementById(`human-review-${visible.id}`)
                              ?.scrollIntoView({
                                block: "start",
                                behavior: "smooth",
                              })
                          }
                        >
                          Review assessment ↓
                        </button>
                      )}
                    </div>
                    <InvestigationReport
                      key={`report-${currentId}`}
                      report={report}
                      evidence={evidence}
                    />
                    {humanReview && (
                      <ReportReviewPanel
                        key={`review-${visible.id}`}
                        alertId={alertId}
                        attemptId={visible.id}
                        data={humanReview}
                        onSaved={(page) =>
                          setDetail((previous) =>
                            previous?.id === visible.id
                              ? { ...previous, human_review: page }
                              : previous,
                          )
                        }
                        onReload={() => setRefresh((n) => n + 1)}
                      />
                    )}
                  </>
                )}
                {visible.status === "requesting" && (
                  <p>
                    A single Analyst request is in flight. Closing this page
                    does not cancel it.
                  </p>
                )}
                {visible.status === "rejected" && (
                  <div className="notice error">
                    This candidate failed integrity checks. It is not an
                    accepted assessment; its original output remains in the
                    technical record.
                  </div>
                )}
                {visible.status === "rejected" && (
                  <ValidationIssues attempt={visible} />
                )}
                {visible.mode === "manual" &&
                  (visible.status === "awaiting_approval" ||
                    (visible.status === "failed" &&
                      visible.error_code === "context_budget_exceeded")) && (
                    <div
                      className="context-choice"
                      aria-label="Analyst context size"
                    >
                      <h3>Start small</h3>
                      <p>
                        Use focused evidence for a simple investigation. Only
                        broaden it if the selected facts leave a specific
                        question unanswered. This changes local input only,
                        makes no model call, and clears processing consent.
                      </p>
                      <div>
                        <button
                          className="button secondary"
                          disabled={busy}
                          aria-pressed={
                            (
                              evidence?.scope.context_selection as
                                { profile?: string } | undefined
                            )?.profile === "focused"
                          }
                          onClick={() => void chooseContext("focused")}
                        >
                          Focused · up to 4 events / 16 KiB
                        </button>
                        <button
                          className="button secondary"
                          disabled={busy}
                          aria-pressed={
                            (
                              evidence?.scope.context_selection as
                                { profile?: string } | undefined
                            )?.profile === "expanded"
                          }
                          onClick={() => void chooseContext("expanded")}
                        >
                          Broader · up to 12 events / 48 KiB
                        </button>
                      </div>
                    </div>
                  )}
                {visible.error_code === "context_budget_exceeded" && (
                  <p className="notice">
                    Collection is saved locally, but no selected input fits this
                    profile yet. Choose broader context or inspect the technical
                    record. Nothing has been sent to a model.
                  </p>
                )}
                {evidence &&
                  (report ? (
                    <details>
                      <summary>Selected context and collection gaps</summary>
                      <SelectedEvidence attempt={visible} evidence={evidence} />
                    </details>
                  ) : (
                    <SelectedEvidence attempt={visible} evidence={evidence} />
                  ))}
                {visible.status === "awaiting_approval" &&
                  visible.mode !== "automatic" && (
                    <div className="approval-box">
                      <h3>Approve this selected evidence</h3>
                      <p>
                        Review the source facts above. Selection is not
                        redaction; logs can contain personal data or secrets.
                      </p>
                      <label>
                        <input
                          type="checkbox"
                          checked={approved}
                          onChange={(e) => setApproved(e.target.checked)}
                        />
                        I have inspected this evidence and approve sending this
                        exact selected input to the configured external analysis
                        service for one advisory request. It may incur a charge.
                      </label>
                      <button
                        className="button primary"
                        disabled={!approved || busy}
                        onClick={() => void act("approve")}
                      >
                        Approve one Analyst request
                      </button>
                    </div>
                  )}
                {["pending_collection", "awaiting_approval", "queued"].includes(
                  visible.status,
                ) && (
                  <button
                    className="button secondary"
                    disabled={busy}
                    onClick={() => void act("cancel")}
                  >
                    Cancel unstarted work
                  </button>
                )}
                <InvestigationExport
                  key={`export-${visible.id}`}
                  alertId={alertId}
                  attemptId={visible.id}
                />
                <details className="technical-record">
                  <summary>
                    Technical record · provenance, original replies, and JSON
                  </summary>
                  <p className="evidence-digest">
                    Selected evidence SHA-256: {visible.evidence_digest}
                  </p>
                  <h4>Attempt provenance and approval record</h4>
                  <EvidenceFacts
                    value={{
                      ...selected,
                      provenance: visible.provenance,
                      response_usage: visible.model_reply?.usage,
                      generation_human_review_required: true,
                      response_executed: false,
                    }}
                  />
                  {visible.result && (
                    <details>
                      <summary>
                        Preserved candidate and validation · JSON
                      </summary>
                      <pre>{JSON.stringify(visible.result, null, 2)}</pre>
                    </details>
                  )}
                  {visible.model_reply && (
                    <details>
                      <summary>Original model reply · untrusted text</summary>
                      <pre>{visible.model_reply.content}</pre>
                    </details>
                  )}
                  {visible.evidence && (
                    <details>
                      <summary>Original collected evidence · JSON</summary>
                      <pre>{JSON.stringify(visible.evidence, null, 2)}</pre>
                    </details>
                  )}
                </details>
              </>
            ) : (
              <p>Loading saved attempt…</p>
            )}
            <label className="attempt-picker">
              Attempt history
              <select
                aria-label="Attempt history"
                value={currentId}
                onChange={(e) => {
                  selectAttempt(e.target.value);
                  setApproved(false);
                }}
              >
                {attempts.map((a) => (
                  <option key={a.id} value={a.id}>
                    #{a.number} · {time(a.created_at)} ·{" "}
                    {statusLabels[a.status] ?? a.status}
                  </option>
                ))}
              </select>
            </label>
          </>
        )}
      </div>
    </section>
  );
}
