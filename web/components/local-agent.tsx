"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, ApiError, time } from "@/lib/api";
import { AgentTabs } from "./agent-tabs";

type Tasks = {
  tasks: {
    id: string;
    attempt_id: string;
    alert_id: string;
    number: number;
    title: string;
    agent_name: string | null;
    state: string;
    question: string | null;
    items: number;
    started_at: string;
    error_code: string | null;
  }[];
};
export function LocalAgent({ kind }: { kind: "correlation" | "intel" }) {
  const router = useRouter();
  const [data, setData] = useState<Tasks | null>(null),
    [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const next = await api<Tasks>(`/agents/local/${kind}`, {
          signal: controller.signal,
        });
        if (!controller.signal.aborted) {
          setData(next);
          setError("");
        }
      } catch (err) {
        if (controller.signal.aborted) return;
        if (err instanceof ApiError && err.status === 401)
          router.replace("/login");
        else setError("Could not refresh delegated checks.");
      }
      if (!controller.signal.aborted) timer = setTimeout(poll, 5000);
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [kind, router]);
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>{kind === "correlation" ? "Correlation" : "Intel"}</h1>
          <p>
            {kind === "correlation"
              ? "Relationship checks delegated by the Analyst."
              : "Indicator checks delegated by the Analyst."}
          </p>
        </div>
        <Link className="button secondary" href="/soc/agents/analyst">
          Open investigations
        </Link>
      </div>
      <AgentTabs current={kind} />
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
      <section className="panel">
        <div className="panel-heading">
          <h2>Delegated checks</h2>
          <span className="muted">
            Selected evidence only · no external lookup
          </span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Investigation / question</th>
                <th>Status</th>
                <th>Observed</th>
                <th>Next action</th>
              </tr>
            </thead>
            <tbody>
              {data?.tasks.map((task) => (
                <tr key={task.id}>
                  <td>
                    <Link
                      className="alert-title"
                      href={`/soc/alerts/${task.alert_id}?attempt=${task.attempt_id}`}
                    >
                      {task.title}
                    </Link>
                    <div className="table-sub">
                      {task.question || "Inspect selected evidence"} · #
                      {task.number} · {time(task.started_at)}
                    </div>
                  </td>
                  <td>
                    {task.state}
                    {task.error_code && (
                      <div className="table-sub">
                        {task.error_code.replaceAll("_", " ")}
                      </div>
                    )}
                  </td>
                  <td>
                    {task.state === "completed"
                      ? `${task.items} ${kind === "correlation" ? "relationship hints" : "indicators"}`
                      : "—"}
                  </td>
                  <td>
                    <Link
                      href={`/soc/alerts/${task.alert_id}?attempt=${task.attempt_id}`}
                    >
                      Inspect check →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!data && (
          <p className="table-empty" role="status">
            Loading delegated checks…
          </p>
        )}
        {data?.tasks.length === 0 && (
          <div className="table-empty">
            <h3>No delegated checks yet</h3>
            <p>
              Start a guided investigation. The Analyst chooses which checks are
              needed.
            </p>
            <Link href="/soc">Choose an alert →</Link>
          </div>
        )}
      </section>
    </>
  );
}
