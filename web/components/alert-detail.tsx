"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, FileJson, Fingerprint } from "lucide-react";
import { api, ApiError, levelName, time } from "@/lib/api";
import type { AlertDetail as Detail } from "@/lib/types";
import { Investigation } from "./investigation";

function value(item: unknown) {
  return item == null || item === ""
    ? "—"
    : typeof item === "object"
      ? JSON.stringify(item)
      : String(item);
}

export function AlertDetail({ id }: { id: string }) {
  const router = useRouter();
  const [alert, setAlert] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    api<Detail>(`/alerts/${id}`, { signal: controller.signal })
      .then(setAlert)
      .catch((err) => {
        if (controller.signal.aborted) return;
        if (err instanceof ApiError && err.status === 401)
          router.replace("/login");
        else setError(err instanceof Error ? err.message : "Alert unavailable");
      });
    return () => controller.abort();
  }, [id, router]);
  if (error)
    return (
      <div role="alert" className="notice error">
        {error}
        <Link href="/soc">Back to alerts →</Link>
      </div>
    );
  if (!alert) return <p role="status">Loading alert…</p>;
  const context = alert.document.context;
  const fields = [
    ["Host", alert.agent_name],
    ["Agent ID", alert.agent_id],
    ["Channel", context.channel],
    ["Event ID", context.event_id],
    ["User", context.user],
    ["PID", context.process_id],
    ["Process GUID", context.process_guid],
    ["Parent process GUID", context.parent_process_guid],
  ];
  return (
    <>
      <Link href="/soc" className="back-link">
        <ArrowLeft size={14} />
        Alert queue
      </Link>
      <div className="page-heading detail-heading">
        <div>
          <div className="eyebrow">WAZUH DETECTION · RULE {alert.rule_id}</div>
          <h1>{alert.title}</h1>
          <p>
            {alert.agent_name || "Manager"} · {time(alert.timestamp)}
          </p>
          <div className="detail-tags">
            <span
              className={`severity ${levelName(alert.rule_level).toLowerCase()}`}
            >
              {levelName(alert.rule_level)}
              <small>{alert.rule_level}</small>
            </span>
            <span className="plain-tag">Original source retained</span>
          </div>
        </div>
      </div>
      <div className="detail-grid">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Event context</h2>
              <p>Normalized from the original Wazuh document.</p>
            </div>
            <Fingerprint size={20} />
          </div>
          <dl className="event-fields">
            {fields.map(([label, content]) => (
              <div key={String(label)}>
                <dt>{String(label)}</dt>
                <dd>{value(content)}</dd>
              </div>
            ))}
          </dl>
        </section>
        <section className="panel">
          <div className="panel-heading">
            <h2>Provenance</h2>
          </div>
          <dl className="event-fields">
            <div>
              <dt>Native index</dt>
              <dd>{alert.native_index}</dd>
            </div>
            <div>
              <dt>Native document ID</dt>
              <dd>{alert.native_id}</dd>
            </div>
            <div>
              <dt>Indexed timestamp</dt>
              <dd>{alert.timestamp}</dd>
            </div>
            <div>
              <dt>Corvus received</dt>
              <dd>{alert.received_at}</dd>
            </div>
          </dl>
          <p className="provenance-note">
            Indexed time is not necessarily the original event time or the start
            of an attack.
          </p>
        </section>
      </div>
      <Investigation key={id} alertId={id} />
      <section className="panel source-panel">
        <details>
          <summary>
            <span>
              <FileJson size={17} />
              Original source document
            </span>
            <small>Untrusted event data · rendered as text</small>
          </summary>
          <pre>{JSON.stringify(alert.document.source, null, 2)}</pre>
        </details>
      </section>
      <p className="context-note">
        A detection is a lead, not a confirmed compromise. Source text is never
        executed by Corvus.
      </p>
    </>
  );
}
