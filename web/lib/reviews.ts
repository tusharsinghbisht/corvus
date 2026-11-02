export type ReviewDecision = "accepted" | "rejected" | "follow_up";
export type ReviewStatus = ReviewDecision | "pending";
export type ReportReview = {
  id: string;
  sequence: number;
  created_at: string;
  reviewer: string;
  reviewer_id: string;
  decision: ReviewDecision;
  note: string;
  evidence_checked: boolean;
  analysis_id: string;
  evidence_digest: string;
  report_digest: string;
  generation_validator_version: string;
  revalidation: { valid: boolean; validation_version: string };
};
export type ReviewPage = {
  target: {
    analysis_id: string;
    evidence_digest: string;
    report_digest: string;
    validator_version: string;
  } | null;
  current_sequence: number;
  latest: ReportReview | null;
  latest_matches_report: boolean;
  reviews: ReportReview[];
  total: number;
  next_before: number | null;
};
export const reviewLabels: Record<ReviewStatus, string> = {
  pending: "Human review required",
  accepted: "Assessment accepted",
  rejected: "Assessment rejected",
  follow_up: "Follow-up needed",
};
