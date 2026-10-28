"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  ChevronLeft,
  ChevronRight,
  Radio,
  Search,
  SlidersHorizontal,
} from "lucide-react";
import { api, ApiError, levelName, time } from "@/lib/api";
import type { AlertPage, ConnectionData } from "@/lib/types";

export function AlertQueue() {
  const router = useRouter();
  const [data, setData] = useState<AlertPage | null>(null);
  const [sources, setSources] = useState<ConnectionData | null>(null);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [minimum, setMinimum] = useState("0");
  const [hours, setHours] = useState("24");
  const [connection, setConnection] = useState("");
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const [updated, setUpdated] = useState<string | null>(null);
  const [error, setError] = useState("");
  const cursor = cursors[cursors.length - 1];
  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(search);
      setCursors([null]);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);
  useEffect(() => {
    const controller = new AbortController();
    let sequence = 0;
    setData(null);
    setError("");
    let inFlight = false;
    async function load() {
      if (inFlight) return;
      inFlight = true;
      const current = ++sequence;
      try {
        const params = new URLSearchParams({ hours, minimum, q: query });
        if (connection) params.set("connection", connection);
        if (cursor) params.set("before", cursor);
        const [page, connections] = await Promise.all([
          api<AlertPage>(`/alerts?${params}`, { signal: controller.signal }),
          api<ConnectionData>("/connections", { signal: controller.signal }),
        ]);
        if (controller.signal.aborted || current !== sequence) return;
        setData(page);
        setSources(connections);
        setUpdated(new Date().toISOString());
        setError("");
      } catch (err) {
        if (controller.signal.aborted || current !== sequence) return;
        if (err instanceof ApiError && err.status === 401)
          router.replace("/login");
        else
          setError(
            err instanceof Error ? err.message : "Could not refresh alerts",
          );
      } finally {
        inFlight = false;
      }
    }
    load();
    const timer = cursor ? null : setInterval(load, 5000);
    return () => {
      controller.abort();
      if (timer) clearInterval(timer);
    };
  }, [hours, minimum, query, connection, cursor, router]);
  const connections = sources?.connections || [];
  const active = connections.filter(
    (c) =>
      c.enabled &&
      !c.last_error &&
      c.last_sync_at &&
      Date.now() - new Date(c.last_sync_at).getTime() < 60000,
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">SECURITY OPERATIONS</div>
          <h1>Alert queue</h1>
          <p>Real detections from your connected Wazuh indexer.</p>
        </div>
        <Link href="/soc/connections" className="button subtle">
          <SlidersHorizontal size={15} />
          Manage connections
        </Link>
      </div>
      {error && (
        <div role="alert" className="notice error">
          {error} {data && "Showing the last successful refresh."}
        </div>
      )}
      {sources && !connections.length ? (
        <section className="panel onboarding">
          <div className="empty-icon">
            <Radio size={27} />
          </div>
          <h2>Connect your first source.</h2>
          <p>
            Add your Wazuh indexer with read-only credentials.
            <br />
            Corvus will start collecting real alerts into this queue.
          </p>
          <Link href="/soc/connections" className="button primary">
            Connect Wazuh <ArrowRight size={16} />
          </Link>
        </section>
      ) : (
        <>
          <div className="metrics">
            <div>
              <span>Matching alerts</span>
              <strong>{data ? data.stats.total.toLocaleString() : "—"}</strong>
              <small>Within the selected time window</small>
            </div>
            <div>
              <span>High & critical</span>
              <strong>{data ? data.stats.high.toLocaleString() : "—"}</strong>
              <small>Native Wazuh levels 12–16</small>
            </div>
            <div>
              <span>Reporting agents</span>
              <strong>{data ? data.stats.agents : "—"}</strong>
              <small>Distinct agents in matching alerts</small>
            </div>
            <div>
              <span>Polling connections</span>
              <strong>
                {sources ? `${active.length} / ${connections.length}` : "—"}
              </strong>
              <small>Successful sync in the last minute</small>
            </div>
          </div>
          {connections.some(
            (c) =>
              c.last_error ||
              (c.enabled &&
                Date.now() - new Date(c.checkpoint).getTime() > 600000),
          ) && (
            <div className="notice">
              One or more connections are catching up or need attention.{" "}
              <Link href="/soc/connections">View sync health →</Link>
            </div>
          )}
          <section className="panel queue-panel">
            <div className="panel-heading">
              <div>
                <h2>Incoming alerts</h2>
                <p>Source severity, original identity, durable history.</p>
              </div>
              <span className="poll-label">
                <span className={`dot ${error ? "bad" : ""}`} />
                {cursor ? "Historical page" : "Refreshes every 5s"}
              </span>
            </div>
            <div className="toolbar">
              <div className="search-wrap">
                <Search size={16} />
                <input
                  aria-label="Search alerts"
                  type="search"
                  placeholder="Search alert, host, or rule…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </div>
              <select
                aria-label="Time window"
                value={hours}
                onChange={(e) => {
                  setHours(e.target.value);
                  setCursors([null]);
                }}
              >
                <option value="1">Last hour</option>
                <option value="6">Last 6 hours</option>
                <option value="24">Last 24 hours</option>
                <option value="168">Last 7 days</option>
                <option value="720">Last 30 days</option>
              </select>
              <select
                aria-label="Minimum severity"
                value={minimum}
                onChange={(e) => {
                  setMinimum(e.target.value);
                  setCursors([null]);
                }}
              >
                <option value="0">All severities</option>
                <option value="7">Medium and above</option>
                <option value="12">High and critical</option>
                <option value="15">Critical only</option>
              </select>
              {connections.length > 1 && (
                <select
                  aria-label="Connection"
                  value={connection}
                  onChange={(e) => {
                    setConnection(e.target.value);
                    setCursors([null]);
                  }}
                >
                  <option value="">All sources</option>
                  {connections.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              )}
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Detection</th>
                    <th>Agent</th>
                    <th>Severity</th>
                    <th>Indexed time</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {data?.alerts.map((alert) => (
                    <tr key={alert.id}>
                      <td>
                        <Link
                          className="alert-title"
                          href={`/soc/alerts/${alert.id}`}
                        >
                          {alert.title}
                        </Link>
                        <div className="table-sub">
                          Rule {alert.rule_id || "—"} · {alert.native_id}
                        </div>
                      </td>
                      <td>
                        {alert.agent_name || "Manager"}
                        <div className="table-sub">
                          {alert.agent_id
                            ? `Agent ${alert.agent_id}`
                            : "No agent ID"}
                        </div>
                      </td>
                      <td>
                        <span
                          className={`severity ${levelName(alert.rule_level).toLowerCase()}`}
                        >
                          {levelName(alert.rule_level)}
                          <small>{alert.rule_level}</small>
                        </span>
                      </td>
                      <td className="time-cell">{time(alert.timestamp)}</td>
                      <td>
                        <Link
                          href={`/soc/alerts/${alert.id}`}
                          aria-label={`Open alert ${alert.native_id}`}
                        >
                          <ArrowRight size={15} />
                        </Link>
                      </td>
                    </tr>
                  ))}
                  {!data && (
                    <tr>
                      <td colSpan={5} className="table-empty">
                        {error ? "Alerts unavailable" : "Loading alerts…"}
                      </td>
                    </tr>
                  )}
                  {data && !data.alerts.length && (
                    <tr>
                      <td colSpan={5} className="table-empty">
                        <h3>No matching alerts.</h3>
                        <p>
                          Try a wider time window or check your connection’s
                          sync progress.
                        </p>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="pagination">
              <span>
                {data
                  ? `${data.alerts.length} shown · ${data.stats.total.toLocaleString()} matching`
                  : "Loading"}
                {updated && ` · Updated ${time(updated)}`}
              </span>
              <div>
                <button
                  aria-label="Previous page"
                  disabled={cursors.length === 1}
                  onClick={() => setCursors((values) => values.slice(0, -1))}
                >
                  <ChevronLeft size={16} />
                </button>
                <button
                  aria-label="Next page"
                  disabled={!data?.next_cursor}
                  onClick={() => {
                    if (data?.next_cursor)
                      setCursors((values) => [...values, data.next_cursor]);
                  }}
                >
                  <ChevronRight size={16} />
                </button>
              </div>
            </div>
          </section>
        </>
      )}
      <p className="context-note">
        Severity comes from Wazuh’s rule level. It is a detection signal, not an
        independently verified verdict.
      </p>
    </>
  );
}
