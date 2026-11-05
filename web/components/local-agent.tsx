"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, ApiError, time } from "@/lib/api";

type Overview = {
  available_inputs: number;
  attempts: {
    attempt_id: string;
    alert_id: string;
    number: number;
    title: string;
    agent_name: string | null;
    status: string;
    profile: string | null;
    created_at: string;
  }[];
};
export function LocalAgent({ kind }: { kind: "correlation" | "intel" }) {
  const router = useRouter();
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    api<Overview>(`/agents/local/${kind}`, { signal: controller.signal })
      .then((value) => {
        if (!controller.signal.aborted) setData(value);
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        if (err instanceof ApiError && err.status === 401)
          router.replace("/login");
        else
          setError(
            err instanceof Error ? err.message : "Saved inputs unavailable",
          );
      });
    return () => controller.abort();
  }, [kind, router]);
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">LOCAL READ-ONLY AGENT</div>
          <h1>{kind === "correlation" ? "Correlation" : "Intel"}</h1>
          <p>
            {kind === "correlation"
              ? "Narrow the evidence before the Analyst sees it."
              : "Inspect observed indicators without sending evidence to external services."}
          </p>
        </div>
        <Link className="button secondary" href="/soc">
          Open alert queue
        </Link>
      </div>
      <section className="panel local-agent-intro">
        <h2>
          {kind === "correlation"
            ? "Focused selection, not a context dump"
            : "Local indicator facts, not a reputation verdict"}
        </h2>
        <p>
          {kind === "correlation"
            ? "The preparation stage ranks exact process GUID and command-line matches, deduplicates mirrored Windows events, and avoids time-only filler in focused mode. It selects up to four supporting events within 16 KiB. Broader context requires an explicit pre-approval choice."
            : "The inspection stage extracts structured IP addresses, DNS query names, and hashes from a saved selected input. It reports address classes and syntax with exact source references. It performs no network lookups and cannot declare an indicator malicious or safe."}
        </p>
        <p className="muted">
          These are bounded deterministic agents, not autonomous LLM roles.
          Opening this page makes no model request. Choose a saved attempt, then
          expand Correlation & Intel · local inspection. Historical context
          remains immutable.
        </p>
      </section>
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Saved inputs available for inspection</h2>
            <p>
              {data
                ? `${data.available_inputs} saved inputs · latest 20 shown. This is not a count of completed Intel investigations.`
                : "Loading saved inputs…"}
            </p>
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Alert / exact attempt</th>
                <th>Context profile</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {data?.attempts.map((attempt) => (
                <tr key={attempt.attempt_id}>
                  <td>
                    <Link
                      className="alert-title"
                      href={`/soc/alerts/${attempt.alert_id}?attempt=${attempt.attempt_id}`}
                    >
                      {attempt.title}
                    </Link>
                    <div className="table-sub">
                      Attempt #{attempt.number} · {attempt.status} ·{" "}
                      {attempt.agent_name || "Manager"}
                    </div>
                  </td>
                  <td>{attempt.profile || "Legacy saved input"}</td>
                  <td>{time(attempt.created_at)}</td>
                </tr>
              ))}
              {data && !data.attempts.length && (
                <tr>
                  <td colSpan={3} className="table-empty">
                    No prepared evidence yet. Open an alert and prepare its
                    context locally; model approval is separate.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
