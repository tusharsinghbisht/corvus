"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, ApiError, time } from "@/lib/api";
import { statusLabels } from "@/lib/investigations";
import type { AnalystSettings } from "@/lib/policies";

type Overview = AnalystSettings & {
  stats: { total: number; active: number; reports: number; attention: number };
  attempts: {
    id: string;
    alert_id: string;
    title: string;
    number: number;
    mode: string;
    status: string;
    created_at: string;
    disposition: string | null;
  }[];
};
export function AnalystAgent() {
  const router = useRouter();
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const result = await api<Overview>("/agents/analyst", {
          signal: controller.signal,
        });
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
  }, [router]);
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
          <span>Reports ready for review</span>
          <strong>{data?.stats.reports ?? "—"}</strong>
          <small>Passed integrity checks, not human acceptance</small>
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
              Latest 50 attempts. Open an alert for its report, evidence map,
              and complete history.
            </p>
          </div>
          <Link href="/soc">Open alert queue →</Link>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Alert</th>
                <th>Mode</th>
                <th>Attempt</th>
                <th>Outcome</th>
                <th>Requested</th>
              </tr>
            </thead>
            <tbody>
              {data?.attempts.map((a) => (
                <tr key={a.id}>
                  <td>
                    <Link
                      className="alert-title"
                      href={`/soc/alerts/${a.alert_id}`}
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
                  <td className="time-cell">{time(a.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data?.attempts.length === 0 && (
          <div className="table-empty">
            <h3>No investigations yet</h3>
            <p>Open an alert and choose Investigate with Analyst to begin.</p>
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
