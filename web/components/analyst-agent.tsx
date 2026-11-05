"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, ApiError, time } from "@/lib/api";
import type { ReviewStatus } from "@/lib/reviews";
import { ReviewBadge } from "./review-badge";
import { AgentTabs } from "./agent-tabs";

type Overview = {
  stats: { active: number; attention: number; pending_review: number };
  attempts: {
    id: string;
    alert_id: string;
    title: string;
    number: number;
    status: string;
    workflow: string;
    current_step: string | null;
    created_at: string;
    agent_name: string | null;
    rule_level: number;
    review_status: ReviewStatus | null;
    review_stale: boolean;
    error_code: string | null;
  }[];
};
function nextAction(a: Overview["attempts"][number]) {
  if (a.status === "awaiting_approval") return "Approve input";
  if (a.status === "validated")
    return a.review_status === "pending" ? "Review assessment" : "Open report";
  if (["failed", "rejected", "unknown"].includes(a.status))
    return "Inspect failure";
  if (a.status === "cancelled") return "Open attempt";
  return "View progress";
}
export function AnalystAgent() {
  const router = useRouter();
  const [data, setData] = useState<Overview | null>(null),
    [error, setError] = useState(""),
    [reviewFilter, setReviewFilter] = useState("all");
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    setData(null);
    async function poll() {
      try {
        const result = await api<Overview>(
          `/agents/analyst?review=${reviewFilter}`,
          { signal: controller.signal },
        );
        if (!controller.signal.aborted) {
          setData(result);
          setError("");
        }
      } catch (err) {
        if (controller.signal.aborted) return;
        if (err instanceof ApiError && err.status === 401)
          router.replace("/login");
        else setError("Could not refresh investigations.");
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
          <h1>Analyst</h1>
          <p>Plan → delegated checks → assessment → human review.</p>
        </div>
        <Link className="button secondary" href="/soc">
          Investigate an alert
        </Link>
      </div>
      <AgentTabs current="analyst" />
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
      <div className="agent-counters">
        <span>
          <strong>{data?.stats.active ?? "—"}</strong> active
        </span>
        <span>
          <strong>{data?.stats.pending_review ?? "—"}</strong> need review
        </span>
        <span>
          <strong>{data?.stats.attention ?? "—"}</strong> need attention
        </span>
        <Link href="/soc/settings">Settings ↗</Link>
      </div>
      <section className="panel">
        <div className="panel-heading">
          <h2>Recent investigations</h2>
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
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Investigation</th>
                <th>Current step</th>
                <th>Review</th>
                <th>Next action</th>
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
                    <div className="table-sub">
                      {a.agent_name || "Manager"} · #{a.number} ·{" "}
                      {a.workflow === "agentic" ? "Guided" : "Direct"} ·{" "}
                      {time(a.created_at)}
                    </div>
                  </td>
                  <td>
                    {a.status === "requesting"
                      ? a.current_step || "Starting"
                      : a.status.replaceAll("_", " ")}
                    {a.error_code && (
                      <div className="table-sub">
                        {a.error_code.replaceAll("_", " ")}
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
                      <span className="muted">—</span>
                    )}
                  </td>
                  <td>
                    <Link href={`/soc/alerts/${a.alert_id}?attempt=${a.id}`}>
                      {nextAction(a)} →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!data && (
          <p className="table-empty" role="status">
            Loading investigations…
          </p>
        )}
        {data?.attempts.length === 0 && (
          <p className="table-empty">
            No matching investigations. Open an alert to prepare one.
          </p>
        )}
      </section>
      <p className="context-note">
        Assessments are advisory. Response authorization and post-action
        verification are not implemented.
      </p>
    </>
  );
}
