"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, ApiError, time } from "@/lib/api";
import type { AnalystPolicy, AnalystSettings } from "@/lib/policies";

export function AnalystPolicyCard({
  policy,
  onSaved,
  compact = false,
}: {
  policy: AnalystPolicy;
  onSaved: (data: AnalystSettings) => void;
  compact?: boolean;
}) {
  const router = useRouter();
  const [enabled, setEnabled] = useState(policy.enabled);
  const [minimum, setMinimum] = useState(policy.minimum_level);
  const [hourly, setHourly] = useState(policy.hourly_limit);
  const [daily, setDaily] = useState(policy.daily_limit);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function save() {
    setBusy(true);
    setError("");
    try {
      const data = await api<AnalystSettings>(
        `/settings/analyst/connections/${policy.connection_id}`,
        {
          method: "PUT",
          body: JSON.stringify({
            enabled,
            allow_external: consent,
            minimum_level: minimum,
            hourly_limit: hourly,
            daily_limit: daily,
            version: policy.version,
          }),
        },
      );
      onSaved(data);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401)
        router.replace("/login");
      else
        setError(err instanceof Error ? err.message : "Policy update failed");
    } finally {
      setBusy(false);
    }
  }
  const changed =
    enabled !== policy.enabled ||
    minimum !== policy.minimum_level ||
    hourly !== policy.hourly_limit ||
    daily !== policy.daily_limit;
  return (
    <section
      className={compact ? "policy-inline" : "panel policy-card"}
      aria-label={`Analyst policy for ${policy.name}`}
    >
      {!compact && (
        <div className="panel-heading">
          <div>
            <h2>{policy.name}</h2>
            <p>
              {policy.ingestion_enabled
                ? "Ingestion enabled"
                : "Ingestion paused · automatic triage will not run"}
            </p>
          </div>
          <span className="plain-tag">
            {policy.enabled ? "Automatic" : "Manual"}
          </span>
        </div>
      )}
      <div className="policy-body">
        <div
          className="mode-toggle"
          role="group"
          aria-label={`Triage mode for ${policy.name}`}
        >
          <button
            aria-pressed={!enabled}
            onClick={() => {
              setEnabled(false);
              setConsent(false);
            }}
          >
            Manual
          </button>
          <button
            aria-pressed={enabled}
            onClick={() => {
              setEnabled(true);
              setConsent(false);
            }}
          >
            Automatic
          </button>
        </div>
        <p className="muted">
          Connection-level policy · {policy.name}. Manual investigation is
          always available. Switching modes never analyzes this historical alert
          or a backlog.
        </p>
        {compact ? (
          <p>
            Policy: level {minimum}+ · {hourly} reservations/hour · {daily}/24h.{" "}
            <Link href="/soc/settings">Edit severity and budgets →</Link>
          </p>
        ) : (
          <div className="policy-fields">
            <label>
              Minimum severity
              <select
                aria-label={`Minimum severity for ${policy.name}`}
                value={minimum}
                onChange={(e) => {
                  setMinimum(Number(e.target.value) as 7 | 12 | 15);
                  setConsent(false);
                }}
              >
                <option value={7}>Medium and above · levels 7–16</option>
                <option value={12}>High and critical · levels 12–16</option>
                <option value={15}>Critical only · levels 15–16</option>
              </select>
            </label>
            <label>
              Maximum per rolling hour
              <input
                aria-label={`Hourly request limit for ${policy.name}`}
                type="number"
                min={1}
                max={20}
                value={hourly}
                onChange={(e) => {
                  setHourly(Number(e.target.value));
                  setConsent(false);
                }}
              />
            </label>
            <label>
              Maximum per rolling 24 hours
              <input
                aria-label={`Daily request limit for ${policy.name}`}
                type="number"
                min={1}
                max={100}
                value={daily}
                onChange={(e) => {
                  setDaily(Number(e.target.value));
                  setConsent(false);
                }}
              />
            </label>
          </div>
        )}
        <p className="muted">
          Reserved: {policy.used_hour}/{policy.hourly_limit} this hour ·{" "}
          {policy.used_day}/{policy.daily_limit} in 24h.{" "}
          {policy.consent_at
            ? `Last consent: ${time(policy.consent_at)}.`
            : "No standing external-processing consent."}
        </p>
        {enabled && changed && (
          <div className="approval-box">
            <label>
              <input
                type="checkbox"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
              />
              I explicitly authorize external processing of selected evidence
              from NEW alerts on this connection matching this policy. Requests
              may incur charges. This is separate from ingestion and manual
              per-alert approval.
            </label>
            <p>
              Only alerts timestamped and received after this save qualify,
              after a five-minute evidence window and before they are 15 minutes
              old. Failures are not retried. Policy edits cancel unstarted
              automatic work and establish a fresh eligibility boundary.
            </p>
          </div>
        )}
        {error && (
          <p role="alert" className="notice error">
            {error}
          </p>
        )}
        <button
          className="button secondary"
          disabled={busy || !changed || (enabled && !consent)}
          onClick={() => void save()}
        >
          {busy
            ? "Saving…"
            : enabled
              ? "Save automatic policy"
              : "Use manual mode"}
        </button>
      </div>
    </section>
  );
}

export function AlertAnalystMode({ connectionId }: { connectionId: string }) {
  const [data, setData] = useState<AnalystSettings | null>(null);
  const [error, setError] = useState("");
  const router = useRouter();
  useEffect(() => {
    const controller = new AbortController();
    api<AnalystSettings>("/settings/analyst", { signal: controller.signal })
      .then(setData)
      .catch((err) => {
        if (controller.signal.aborted) return;
        if (err instanceof ApiError && err.status === 401)
          router.replace("/login");
        else
          setError(
            "Policy status unavailable. Manual investigation remains available.",
          );
      });
    return () => controller.abort();
  }, [router]);
  const policy = data?.policies.find((p) => p.connection_id === connectionId);
  return (
    <details className="alert-mode">
      <summary>
        Analyst mode{" "}
        <span className="plain-tag">
          {policy
            ? policy.enabled
              ? "Automatic"
              : "Manual"
            : "Loading policy…"}
        </span>
      </summary>
      {error && <p role="alert">{error}</p>}
      {policy && (
        <>
          <AnalystPolicyCard
            key={`${policy.connection_id}-${policy.version}`}
            policy={policy}
            onSaved={setData}
            compact
          />
          <p className="muted">
            Global automatic cap: {data?.global_used_day}/
            {data?.global_daily_limit} reservations per rolling 24h. No
            containment or response execution.
          </p>
        </>
      )}
    </details>
  );
}
