"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, ApiError, time } from "@/lib/api";
import { statusLabels } from "@/lib/investigations";
import type { AnalystSettings } from "@/lib/policies";
import type { ReviewStatus } from "@/lib/reviews";
import { ReviewBadge } from "./review-badge";

type Overview = AnalystSettings & {
  stats: {
    total: number;
    active: number;
    reports: number;
    attention: number;
    pending_review: number;
    accepted_assessments: number;
    rejected_assessments: number;
    follow_up: number;
  };
  attempts: {
    id: string;
    alert_id: string;
    title: string;
    number: number;
    mode: string;
    status: string;
    created_at: string;
    disposition: string | null;
    review_status: ReviewStatus | null;
    review_stale: boolean;
  }[];
};
export function AnalystAgent() {
  const router = useRouter();
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const [reviewFilter, setReviewFilter] = useState("all");
  useEffect(() => {
    setData(null);
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const result = await api<Overview>(
          `/agents/analyst?review=${reviewFilter}`,
          {
            signal: controller.signal,
          },
        );
        if (!controller.signal.aborted) {
          setData(result);
          setError("");
        }
      } catch (err) {
        if (controller.signal.aborted) return;
        if (err instanceof ApiError && err.status === 401)
          router.replace("/login");
        else
          setError(err instanceof Error ? err.message : "Analyst unavailable");
      }
      if (!controller.signal.aborted) timer = setTimeout(poll, 5000);
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [router, reviewFilter]);
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">AGENTS / ANALYST</div>
          <h1>Analyst</h1>
          <p>
            Evidence-linked, single-pass investigation. Advisory assessments,
            never response authority.
          </p>
        </div>
        <Link className="button secondary" href="/soc/settings">
          Configure policy
        </Link>
      </div>
      {error && (
        <p role="alert" className="notice error">
          {error}
        </p>
      )}
      <div className="metrics">
        <div>
          <span>Investigation attempts</span>
          <strong>{data?.stats.total ?? "—"}</strong>
          <small>Manual and automatic history</small>
        </div>
        <div>
          <span>Active / awaiting approval</span>
          <strong>{data?.stats.active ?? "—"}</strong>
          <small>Not incident count</small>
        </div>
        <div>
          <span>Reports awaiting human review</span>
          <strong>{data?.stats.pending_review ?? "—"}</strong>
          <small>
            {data?.stats.reports ?? "—"} total reports · counted per attempt,
            not incident
          </small>
        </div>
        <div>
          <span>Needs attention</span>
          <strong>{data?.stats.attention ?? "—"}</strong>
          <small>Failed, unknown, or rejected attempts</small>
        </div>
      </div>
      <div className="notice">
        <span>
          {data?.policies.filter((p) => p.enabled).length ?? 0} connections
          opted into automatic processing. Global reservations:{" "}
          {data?.global_used_day ?? 0}/{data?.global_daily_limit ?? "—"} per
          rolling 24h. New eligible alerts only; no automatic retries.
        </span>
      </div>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Recent investigations</h2>
            <p>
              Latest 50 matching attempts. Links open the exact report, evidence
              map, and review history.
            </p>
          </div>
          <Link href="/soc">Open alert queue →</Link>
        </div>
        <div className="toolbar review-toolbar">
          <label>
            Human assessment review
            <select
              aria-label="Human review filter"
              value={reviewFilter}
              onChange={(event) => setReviewFilter(event.target.value)}
            >
              <option value="all">All attempts</option>
              <option value="pending">Awaiting human review</option>
              <option value="follow_up">Follow-up needed</option>
              <option value="accepted">Assessment accepted</option>
              <option value="rejected">Assessment rejected</option>
            </select>
          </label>
          <p className="muted">
            {data?.stats.accepted_assessments ?? 0} accepted ·{" "}
            {data?.stats.rejected_assessments ?? 0} rejected ·{" "}
            {data?.stats.follow_up ?? 0} follow-up. Recorded human decisions,
            not incident outcomes.
          </p>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Alert</th>
                <th>Mode</th>
                <th>Attempt</th>
                <th>Outcome</th>
                <th>Human review</th>
                <th>Requested</th>
              </tr>
            </thead>
            <tbody>
              {data?.attempts.map((a) => (
                <tr key={a.id}>
                  <td>
                    <Link
                      className="alert-title"
                      href={`/soc/alerts/${a.alert_id}?attempt=${a.id}`}
                    >
                      {a.title}
                    </Link>
                  </td>
                  <td>{a.mode}</td>
                  <td>#{a.number}</td>
                  <td>
                    {statusLabels[a.status] ?? a.status}
                    {a.disposition && (
                      <div className="table-sub">
                        Advisory: {a.disposition.replaceAll("_", " ")}
                      </div>
                    )}
                  </td>
                  <td>
                    {a.review_status ? (
                      <ReviewBadge
                        status={a.review_status}
                        stale={a.review_stale}
                      />
                    ) : (
                      <span className="muted">No reviewable report</span>
                    )}
                  </td>
                  <td className="time-cell">{time(a.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data?.attempts.length === 0 && (
          <div className="table-empty">
            <h3>
              {reviewFilter === "all"
                ? "No investigations yet"
                : "No matching reviews"}
            </h3>
            <p>
              {reviewFilter === "all"
                ? "Open an alert and choose Investigate with Analyst to begin."
                : "Choose another review filter or return to all attempts."}
            </p>
          </div>
        )}
        {!data && (
          <p role="status" className="table-empty">
            Loading investigations…
          </p>
        )}
      </section>
      <p className="context-note">
        The Analyst uses a prepare → single request → validate LangGraph
        workflow. PostgreSQL owns approvals, policy budgets, and crash recovery.
        Other agent roles remain planned.
      </p>
    </>
  );
}
