"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export function InvestigationExport({
  alertId,
  attemptId,
}: {
  alertId: string;
  attemptId: string;
}) {
  const router = useRouter();
  const [acknowledged, setAcknowledged] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function download(format: "zip" | "markdown") {
    if (!acknowledged || busy) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(
        `/api/alerts/${alertId}/investigations/${attemptId}/export?format=${format}`,
        { credentials: "same-origin", cache: "no-store" },
      );
      if (response.status === 401) {
        router.replace("/login");
        return;
      }
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? "Export unavailable");
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = `corvus-investigation-${attemptId}.${format === "zip" ? "zip" : "md"}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export unavailable");
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="investigation-export">
      <summary>Download investigation handoff</summary>
      <p>
        Downloads stay in your browser; Corvus does not publish a share link or
        send them to a model. Evidence and notes may contain personal data or
        secrets. Keep files private.
      </p>
      <label>
        <input
          type="checkbox"
          checked={acknowledged}
          onChange={(event) => setAcknowledged(event.target.checked)}
        />
        I understand this download may contain sensitive investigation data.
      </label>
      <div className="export-actions">
        <button
          className="button secondary"
          disabled={!acknowledged || busy}
          onClick={() => void download("markdown")}
        >
          Download report summary
        </button>
        <button
          className="button secondary"
          disabled={!acknowledged || busy}
          onClick={() => void download("zip")}
        >
          Download evidence package
        </button>
      </div>
      <p className="muted">
        The ZIP preserves evidence, candidate, provenance, reviews, and
        checksums. Rejected/incomplete output is not an accepted assessment.
        Neither export authorizes response.
      </p>
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
    </details>
  );
}
