"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import type { AnalystSettings as Settings } from "@/lib/policies";
import { AnalystPolicyCard } from "./analyst-policy";

export function AnalystSettings() {
  const router = useRouter();
  const [data, setData] = useState<Settings | null>(null);
  const [limit, setLimit] = useState(20);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    api<Settings>("/settings/analyst", { signal: controller.signal })
      .then((value) => {
        setData(value);
        setLimit(value.global_daily_limit);
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        if (err instanceof ApiError && err.status === 401)
          router.replace("/login");
        else
          setError(err instanceof Error ? err.message : "Settings unavailable");
      });
    return () => controller.abort();
  }, [router]);
  async function saveBudget() {
    setBusy(true);
    setError("");
    try {
      setData(
        await api<Settings>("/settings/analyst/budget", {
          method: "PUT",
          body: JSON.stringify({ daily_limit: limit }),
        }),
      );
    } catch (err) {
      if (err instanceof ApiError && err.status === 401)
        router.replace("/login");
      else
        setError(err instanceof Error ? err.message : "Budget update failed");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">WORKSPACE CONFIGURATION</div>
          <h1>Settings</h1>
          <p>
            Analyst eligibility, external-processing consent, and automatic
            request budgets.
          </p>
        </div>
      </div>
      {error && (
        <div role="alert" className="notice error">
          {error}
        </div>
      )}
      <section className="panel policy-card">
        <div className="panel-heading">
          <div>
            <h2>Automatic triage policy</h2>
            <p>
              Off by default. Ingestion and external processing are independent
              permissions.
            </p>
          </div>
        </div>
        <div className="policy-body">
          <p>
            Automatic triage waits five minutes for context, accepts only
            5–15-minute-old alerts timestamped and received after policy
            activation, and runs at most once per alert. Previously investigated
            alerts and historical backfill are excluded. Policy changes
            invalidate unstarted automatic work.
          </p>
          <p>
            Reservations count against budgets even if collection fails or work
            is cancelled. Limits are rolling, not reset by editing policy. No
            automatic retries, alternate-model fallback, containment, or
            incident closure.
          </p>
          <div className="budget-form">
            <label>
              Global automatic reservations per rolling 24h
              <input
                aria-label="Global automatic daily limit"
                type="number"
                min={1}
                max={200}
                value={limit}
                onChange={(e) => setLimit(Number(e.target.value))}
              />
            </label>
            <button
              className="button secondary"
              disabled={
                !data ||
                busy ||
                data.global_daily_limit === limit ||
                !Number.isInteger(limit) ||
                limit < 1 ||
                limit > 200
              }
              onClick={() => void saveBudget()}
            >
              Save global budget
            </button>
          </div>
          <p className="muted">
            Used across connections: {data?.global_used_day ?? "—"}/
            {data?.global_daily_limit ?? "—"}. Manual requests still require
            individual evidence approval.
          </p>
        </div>
      </section>
      <div className="policy-list">
        {data ? (
          data.policies.length ? (
            data.policies.map((policy) => (
              <AnalystPolicyCard
                key={`${policy.connection_id}-${policy.version}`}
                policy={policy}
                onSaved={setData}
              />
            ))
          ) : (
            <p>
              No connections configured. Connect a source before defining its
              processing policy.
            </p>
          )
        ) : (
          <p role="status">Loading policies…</p>
        )}
      </div>
    </>
  );
}
