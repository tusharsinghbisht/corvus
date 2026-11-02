import { reviewLabels } from "@/lib/reviews";
import type { ReviewStatus } from "@/lib/reviews";

export function ReviewBadge({
  status,
  stale = false,
}: {
  status: ReviewStatus;
  stale?: boolean;
}) {
  return (
    <span className={`review-badge review-${stale ? "pending" : status}`}>
      {stale ? "Review stale · recheck" : reviewLabels[status]}
    </span>
  );
}
