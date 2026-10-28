"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Check,
  Database,
  Pause,
  Play,
  Plus,
  ShieldCheck,
} from "lucide-react";
import { api, ApiError, time } from "@/lib/api";
import type { Connection, ConnectionData } from "@/lib/types";

function health(connection: Connection) {
  if (!connection.enabled) return "Paused";
  if (connection.last_error) return "Needs attention";
  if (!connection.last_sync_at) return "Starting";
  if (Date.now() - new Date(connection.last_sync_at).getTime() > 60000)
    return "Sync stale";
  if (Date.now() - new Date(connection.checkpoint).getTime() > 600000)
    return "Catching up";
  return "Polling";
}

export function Connections() {
  const router = useRouter();
  const [data, setData] = useState<ConnectionData | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const load = useCallback(async () => {
    try {
      setData(await api<ConnectionData>("/connections"));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401)
        router.replace("/login");
      else
        setError(
          err instanceof Error ? err.message : "Could not load connections",
        );
    }
  }, [router]);
  useEffect(() => {
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, [load]);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setSuccess("");
    const form = new FormData(event.currentTarget);
    try {
      await api("/connections", {
        method: "POST",
        body: JSON.stringify({
          name: form.get("name"),
          indexer_url: form.get("url"),
          username: form.get("username"),
          password: form.get("password"),
          backfill_hours: Number(form.get("backfill")),
        }),
      });
      setShowForm(false);
      setSuccess(
        "Wazuh connected. The worker will backfill the selected window, then poll new alerts.",
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Connection failed");
    } finally {
      setBusy(false);
    }
  }
  async function toggle(connection: Connection) {
    setError("");
    setBusy(true);
    try {
      await api(`/connections/${connection.id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: !connection.enabled }),
      });
      await load();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not update connection",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">TELEMETRY SOURCES</div>
          <h1>Connections</h1>
          <p>Your security infrastructure. Read-only access.</p>
        </div>
        <button
          className="button primary"
          onClick={() => {
            setShowForm(!showForm);
            setError("");
          }}
        >
          <Plus size={16} />
          {showForm ? "Close setup" : "Connect Wazuh"}
        </button>
      </div>
      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}
      {success && (
        <div className="notice success" role="status">
          <Check size={16} />
          {success}
        </div>
      )}
      {data && (showForm || !data.connections.length) && (
        <section className="panel connection-setup">
          <div className="panel-heading">
            <div>
              <h2>Connect a Wazuh indexer</h2>
              <p>Connectivity and TLS are checked before saving credentials.</p>
            </div>
            <ShieldCheck size={22} />
          </div>
          <form onSubmit={submit} className="connection-form">
            <div className="form-grid">
              <label>
                Connection name
                <input
                  name="name"
                  required
                  maxLength={80}
                  placeholder="Production Wazuh"
                />
              </label>
              <label>
                Indexer URL
                <input
                  name="url"
                  type="url"
                  required
                  defaultValue={`https://${data.indexer_hosts[0]}:9200`}
                  maxLength={256}
                />
              </label>
              <label>
                Read-only username
                <input
                  name="username"
                  required
                  defaultValue="corvus-reader"
                  autoComplete="off"
                  maxLength={128}
                />
              </label>
              <label>
                Read-only password
                <input
                  name="password"
                  type="password"
                  required
                  autoComplete="new-password"
                  maxLength={2048}
                />
              </label>
              <label>
                Initial backfill
                <select name="backfill" defaultValue="24">
                  <option value="1">Last hour</option>
                  <option value="6">Last 6 hours</option>
                  <option value="24">Last 24 hours</option>
                </select>
              </label>
            </div>
            <p className="form-hint">
              Allowed indexers: {data.indexer_hosts.join(", ")}. The CA is
              installed by the server operator. Passwords are encrypted
              server-side and never returned to the browser.
            </p>
            <button disabled={busy} className="button primary">
              {busy ? "Checking connection…" : "Verify & connect"}
              <ArrowRight size={16} />
            </button>
          </form>
        </section>
      )}
      <div className="connection-list">
        {data?.connections.map((connection) => (
          <section className="panel connection-card" key={connection.id}>
            <div className="connection-card-top">
              <div className="connection-symbol">
                <Database size={22} />
              </div>
              <div>
                <h2>{connection.name}</h2>
                <p>Wazuh indexer · {connection.indexer_url}</p>
              </div>
              <span
                className={`connection-status ${connection.last_error ? "status-error" : ""}`}
              >
                <span className="dot" />
                {health(connection)}
              </span>
            </div>
            {connection.last_error && (
              <div className="notice error">
                Sync error: {connection.last_error}. The checkpoint has not
                advanced past incomplete results.
              </div>
            )}
            <dl className="connection-details">
              <div>
                <dt>Last successful sync</dt>
                <dd>{time(connection.last_sync_at)}</dd>
              </div>
              <div>
                <dt>Checkpoint</dt>
                <dd>{time(connection.checkpoint)}</dd>
              </div>
              <div>
                <dt>Backfill starts</dt>
                <dd>{time(connection.backfill_start)}</dd>
              </div>
              <div>
                <dt>Reader</dt>
                <dd>{connection.username}</dd>
              </div>
            </dl>
            <div className="connection-card-bottom">
              <span>All agents · all rule levels · 5-second polling</span>
              <button
                className="button subtle"
                disabled={busy}
                onClick={() => toggle(connection)}
              >
                {connection.enabled ? <Pause size={14} /> : <Play size={14} />}{" "}
                {connection.enabled ? "Pause ingestion" : "Resume ingestion"}
              </button>
            </div>
          </section>
        ))}
      </div>
      {!data && <p role="status">Loading connections…</p>}
      <div className="security-note">
        <ShieldCheck size={18} />
        <p>
          Pausing does not delete alerts or reset the checkpoint. Corvus uses
          this connection only for reads. Use a dedicated read-only account; do
          not supply administrator credentials.
        </p>
      </div>
    </>
  );
}
