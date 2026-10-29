export type Citation =
  | { backend: string; index: string; id: string }
  | { collection_id: string; path: string };

export type Report = {
  disposition: "malicious" | "likely_benign" | "inconclusive";
  summary: string;
  summary_finding_ids: string[];
  findings: {
    id: string;
    kind: string;
    statement: string;
    citations: Citation[];
  }[];
  timeline: { timestamp: string; description: string; citations: Citation[] }[];
  entities: { kind: string; value: string; citations: Citation[] }[];
  alternative_explanations: {
    explanation: string;
    assessment: string;
    citations: Citation[];
  }[];
  uncertainties: { code: string; description: string; next_step: string }[];
  recommendations: {
    category: string;
    description: string;
    rationale: string;
    finding_ids: string[];
  }[];
  limitations: string[];
};

export type EvidenceDocument = {
  reference: { backend: string; index: string; id: string };
  context: Record<string, unknown>;
  source: Record<string, unknown>;
};
export type Evidence = {
  collection_id: string;
  status: string;
  scope: Record<string, unknown>;
  alert: EvidenceDocument;
  events: EvidenceDocument[];
  queries: Record<string, unknown>[];
  gaps: { code: string; message?: string }[];
  limitations: string[];
};
export type ResponseDiagnostics = {
  finish_reason: string | null;
  served_model?: string | null;
  usage: Record<string, number>;
};
export type Attempt = {
  id: string;
  number: number;
  status: string;
  created_at: string;
  requested_by: string;
  collection_started_at: string | null;
  evidence_digest: string | null;
  approved_digest: string | null;
  approved_by: string | null;
  approved_at: string | null;
  request_started_at: string | null;
  completed_at: string | null;
  provenance:
    | (Record<string, unknown> & {
        max_tokens?: number;
        response?: ResponseDiagnostics;
      })
    | null;
  error_code: string | null;
};
export type AttemptDetail = Attempt & {
  evidence: Evidence | null;
  prepared_input: Record<string, unknown> | null;
  model_reply: {
    content: string;
    model: string;
    usage: Record<string, number>;
    finish_reason?: string | null;
  } | null;
  result: {
    status: string;
    report: unknown;
    validation: {
      valid: boolean;
      errors: { code: string; message: string }[];
      [key: string]: unknown;
    };
    [key: string]: unknown;
  } | null;
};
export const activeStatuses = [
  "pending_collection",
  "collecting",
  "awaiting_approval",
  "queued",
  "requesting",
];
export const statusLabels: Record<string, string> = {
  pending_collection: "Collection queued",
  collecting: "Collecting evidence",
  awaiting_approval: "Awaiting your approval",
  queued: "Analyst request queued",
  requesting: "Analyst request in progress",
  validated: "Report passed integrity checks · human review required",
  rejected: "Candidate rejected by validation",
  failed: "Attempt failed",
  unknown: "Request outcome unknown · no automatic retry",
  cancelled: "Cancelled before request",
};
