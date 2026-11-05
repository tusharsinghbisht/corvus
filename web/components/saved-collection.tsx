"use client";

import { useState } from "react";
import Link from "next/link";
import type {
  AttemptDetail,
  CollectionReuse,
  SavedCollection,
} from "@/lib/investigations";

function collectedTime(value: string | null) {
  return value
    ? new Date(value).toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "Not recorded";
}

export function HistoricalCollectionNotice({
  reuse,
  alertId,
}: {
  reuse: CollectionReuse;
  alertId: string;
}) {
  return (
    <div
      className="notice historical-collection"
      aria-label="Historical saved collection"
    >
      <strong>Historical saved collection · no fresh backend query</strong>
      <p>
        Original collected/as-of time:{" "}
        {collectedTime(reuse.original_collected_at)}. Preparing this attempt did
        not update the observations or establish current endpoint state.
      </p>
      <Link
        href={`/soc/alerts/${alertId}?attempt=${encodeURIComponent(reuse.source_attempt_id)}`}
      >
        Source attempt #{reuse.source_attempt_number} →
      </Link>
    </div>
  );
}

export function SavedCollectionReuse({
  attempt,
  disabled,
  onPrepare,
}: {
  attempt: AttemptDetail;
  disabled: boolean;
  onPrepare: (
    profile: "focused" | "expanded",
    binding: SavedCollection,
    acknowledged: boolean,
  ) => void;
}) {
  const [acknowledged, setAcknowledged] = useState(false);
  const [profile, setProfile] = useState<"focused" | "expanded">("focused");
  const binding = attempt.saved_collection;
  if (!binding) return null;
  return (
    <details id={`reuse-${attempt.id}`} className="saved-collection-reuse">
      <summary>Reuse saved evidence · no recollection</summary>
      <div aria-label="Reuse saved collection">
        <h3>Prepare a separate manual attempt</h3>
        <p>
          Use the original local collection when the endpoint or retained
          archives are no longer available. The previous report, reply,
          evidence, and human reviews remain unchanged. This does not repair or
          resume the previous request.
        </p>
        <p>
          <strong>Original collected/as-of time:</strong>{" "}
          {collectedTime(binding.collected_at)} · {binding.supporting_events}{" "}
          supporting events stored locally. Unknown age is not fresh evidence.
        </p>
        {(attempt.request_started_at || attempt.status === "unknown") && (
          <p className="notice">
            The previous request may already have been billed. A new approval
            can incur another charge.
          </p>
        )}
        <label>
          New input profile
          <select
            aria-label="Saved evidence context profile"
            value={profile}
            disabled={disabled}
            onChange={(event) => {
              setProfile(event.target.value as "focused" | "expanded");
              setAcknowledged(false);
            }}
          >
            <option value="focused">Focused · up to 4 events / 16 KiB</option>
            <option value="expanded">Broader · up to 12 events / 48 KiB</option>
          </select>
        </label>
        <label className="saved-collection-ack">
          <input
            type="checkbox"
            checked={acknowledged}
            disabled={disabled}
            onChange={(event) => setAcknowledged(event.target.checked)}
          />
          I understand this is historical evidence, not a fresh collection or
          proof of current endpoint state. Preparing it does not approve
          external processing.
        </label>
        <button
          type="button"
          className="button secondary"
          disabled={disabled || !acknowledged}
          onClick={() => onPrepare(profile, binding, acknowledged)}
        >
          Prepare from saved evidence
        </button>
        <p className="muted">
          This step stays local and makes no model call. The new selected input
          requires its own processing approval. Finish or explicitly cancel any
          active attempt first.
        </p>
      </div>
    </details>
  );
}
