"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, time } from "@/lib/api";
import { activeStatuses, statusLabels } from "@/lib/investigations";
import type { Attempt, AttemptDetail, Report } from "@/lib/investigations";
import { InvestigationReport } from "./investigation-report";
import { InvestigationFailure } from "./investigation-failure";

export function Investigation({ alertId }: { alertId: string }) {
  const router = useRouter();
  const [attempts, setAttempts] = useState<Attempt[] | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState<AttemptDetail | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [approved, setApproved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const base = `/alerts/${alertId}/investigations`;
  const selected = attempts?.find((a) => a.id === selectedId) ?? attempts?.[0];
  const selectedStatus = selected?.status;
  const currentId = selected?.id;

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const data = await api<{ attempts: Attempt[] }>(base, {
          signal: controller.signal,
        });
        if (!controller.signal.aborted) setAttempts(data.attempts);
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

  async function act(action: "collect" | "approve" | "cancel") {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      if (action === "collect") {
        const data = await api<{ id: string }>(base, { method: "POST" });
        setSelectedId(data.id);
      } else {
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
      }
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

  const visible =
    detail?.id === currentId && detail?.status === selectedStatus
      ? detail
      : null;
  const active = attempts?.some((a) => activeStatuses.includes(a.status));
  const report =
    visible?.result?.status === "validated" && visible.result.validation.valid
      ? (visible.result.report as Report)
      : null;

  return (
    <section
      className="panel investigation-panel"
      aria-label="Manual Analyst investigation"
    >
      <div className="panel-heading">
        <div>
          <h2>Analyst investigation</h2>
          <p>
            Manual, read-only triage. Collection stays local until you
            explicitly approve external processing.
          </p>
        </div>
        <button
          className="button secondary"
          disabled={busy || attempts === null || active}
          onClick={() => void act("collect")}
        >
          {attempts?.length ? "Collect new attempt" : "Collect evidence"}
        </button>
      </div>
      <div className="investigation-body">
        <p className="muted">
          Collection scope: the alert’s agent, ±5 minutes, up to 100 events per
          query, with a six-hour process-GUID ancestry pivot when available. No
          tools or response execution. This does not mirror telemetry archives.
        </p>
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
        {attempts === null ? (
          <p role="status">Loading investigation history…</p>
        ) : attempts.length === 0 ? (
          <p>
            No attempts yet. Collect evidence to inspect the exact input before
            approving a model request.
          </p>
        ) : (
          <>
            <label className="attempt-picker">
              Attempt history
              <select
                aria-label="Attempt history"
                value={currentId}
                onChange={(event) => {
                  setSelectedId(event.target.value);
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
            <p role="status" className="attempt-status">
              {statusLabels[selectedStatus ?? ""] ?? selectedStatus}
            </p>
            {visible ? (
              <>
                {visible.error_code && (
                  <InvestigationFailure attempt={visible} />
                )}
                {visible.status === "requesting" && (
                  <p>
                    A single request is in flight. Closing this page does not
                    cancel it.
                  </p>
                )}
                {visible.evidence && (
                  <>
                    <h3>Saved evidence · {visible.evidence.status}</h3>
                    <p>
                      {visible.evidence.events.length} context events, plus the
                      alert. Collection gaps: {visible.evidence.gaps.length}.
                    </p>
                    {visible.evidence.gaps.map((gap, i) => (
                      <p key={i} className="collection-gap">
                        <strong>{gap.code}</strong> · {gap.message}
                      </p>
                    ))}
                    <details className="saved-evidence">
                      <summary>
                        Inspect exact evidence selected for external processing
                      </summary>
                      <p className="muted">
                        This is evidence selection, not redaction. Source logs
                        may contain personal data or secrets. Only this saved
                        bundle’s selected fields are used; no later recollection
                        occurs on approval.
                      </p>
                      <pre>
                        {JSON.stringify(visible.prepared_input, null, 2)}
                      </pre>
                    </details>
                    <p className="evidence-digest">
                      Evidence SHA-256: {visible.evidence_digest}
                    </p>
                  </>
                )}
                {visible.status === "awaiting_approval" && (
                  <div className="approval-box">
                    <label>
                      <input
                        type="checkbox"
                        checked={approved}
                        onChange={(event) => setApproved(event.target.checked)}
                      />
                      I have inspected this evidence and approve sending this
                      exact bundle to the configured external analysis service
                      for one request. It may contain sensitive data and incur a
                      charge.
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
                {report && visible.evidence && (
                  <InvestigationReport
                    report={report}
                    evidence={visible.evidence}
                  />
                )}
                {visible.status === "rejected" && (
                  <div className="notice error">
                    The candidate failed report-integrity checks. It is retained
                    below, not presented as an accepted assessment.
                  </div>
                )}
                {visible.result && (
                  <details>
                    <summary>Preserved candidate and validation</summary>
                    <pre>{JSON.stringify(visible.result, null, 2)}</pre>
                  </details>
                )}
                {visible.model_reply && (
                  <details>
                    <summary>Original model reply · untrusted text</summary>
                    <pre>{visible.model_reply.content}</pre>
                  </details>
                )}
                <details>
                  <summary>Attempt provenance and approval record</summary>
                  <pre>
                    {JSON.stringify(
                      {
                        ...selected,
                        provenance: visible.provenance,
                        response_usage: visible.model_reply?.usage,
                        human_review_required: true,
                        response_executed: false,
                      },
                      null,
                      2,
                    )}
                  </pre>
                </details>
              </>
            ) : (
              <p>Loading saved attempt…</p>
            )}
          </>
        )}
      </div>
    </section>
  );
}
