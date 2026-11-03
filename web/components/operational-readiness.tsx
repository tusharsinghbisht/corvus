"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, time } from "@/lib/api";

type Readiness = {
  database: string;
  worker: {
    heartbeat_at: string | null;
    ready: boolean;
    analysis_configured: boolean;
  };
  backup: {
    configured: boolean;
    encrypted: boolean;
    recent: boolean;
    restore_recent: boolean;
    in_progress?: boolean;
    last_success_at?: string;
    last_restore_verified_at?: string;
    last_error?: string | null;
    archive_bytes?: number;
    retained_snapshots?: number;
    schedule?: string;
  };
};
export function OperationalReadiness() {
  const router = useRouter();
  const [data, setData] = useState<Readiness | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const value = await api<Readiness>("/operations", {
          signal: controller.signal,
        });
        if (!controller.signal.aborted) {
          setData(value);
          setError("");
        }
      } catch (err) {
        if (controller.signal.aborted) return;
        if (err instanceof ApiError && err.status === 401)
          router.replace("/login");
        else
          setError(
            err instanceof Error ? err.message : "Readiness unavailable",
          );
      }
      if (!controller.signal.aborted) timer = setTimeout(poll, 15000);
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [router]);
  return (
    <section
      className="panel operational-readiness"
      aria-label="Operational readiness"
    >
      <div className="panel-heading">
        <div>
          <h2>Operational readiness</h2>
          <p>
            Runtime heartbeat and backup recovery status. No provider test
            requests or response execution.
          </p>
        </div>
      </div>
      <div className="policy-body">
        {error && (
          <p className="notice error" role="alert">
            {error}
          </p>
        )}
        {data ? (
          <>
            <dl className="readiness-grid">
              <div>
                <dt>Database</dt>
                <dd>
                  {data.database === "ready" ? "Available" : "Unavailable"}
                </dd>
              </div>
              <div>
                <dt>Worker heartbeat</dt>
                <dd>
                  {data.worker.ready ? "Recent" : "Needs attention"}
                  <small>{time(data.worker.heartbeat_at)}</small>
                </dd>
              </div>
              <div>
                <dt>Analysis configuration</dt>
                <dd>
                  {data.worker.analysis_configured
                    ? "Configured in worker"
                    : "Not configured"}
                  <small>
                    Configuration is not proof of provider availability.
                  </small>
                </dd>
              </div>
              <div>
                <dt>Encrypted backup</dt>
                <dd>
                  {!data.backup.configured
                    ? "Not configured"
                    : data.backup.last_error
                      ? "Needs attention"
                      : data.backup.in_progress
                        ? "In progress"
                        : data.backup.recent && data.backup.encrypted
                          ? "Recent encrypted snapshot"
                          : "No recent successful snapshot"}
                  <small>{time(data.backup.last_success_at ?? null)}</small>
                </dd>
              </div>
              <div>
                <dt>Isolated restore verification</dt>
                <dd>
                  {data.backup.restore_recent
                    ? "Verified recently"
                    : "Not verified recently"}
                  <small>
                    {time(data.backup.last_restore_verified_at ?? null)}
                  </small>
                </dd>
              </div>
              <div>
                <dt>Scheduled snapshots</dt>
                <dd>
                  {data.backup.configured
                    ? data.backup.schedule
                    : "Operator setup required"}
                  <small>
                    {data.backup.retained_snapshots ?? 0} retained ·{" "}
                    {data.backup.archive_bytes
                      ? `${Math.ceil(data.backup.archive_bytes / 1024 / 1024)} MiB latest encrypted archive`
                      : "No snapshot metadata"}
                  </small>
                </dd>
              </div>
            </dl>
            {data.backup.last_error && (
              <p className="notice error">
                Backup status: {data.backup.last_error.replaceAll("_", " ")}.
                Check the private operator runbook.
              </p>
            )}
            <p className="muted">
              Snapshots are local to this VM. Preserve the backup key and
              encrypted snapshots off-host separately for disaster recovery.
              Restore verification uses an isolated database with no application
              worker and tests queue disarming; it never restores over the live
              database.
            </p>
            <a
              href="https://github.com/tusharsinghbisht/corvus/blob/main/docs/operations.md"
              target="_blank"
              rel="noreferrer"
            >
              Operator backup and recovery runbook ↗
            </a>
          </>
        ) : (
          <p role="status">Loading operational status…</p>
        )}
      </div>
    </section>
  );
}
