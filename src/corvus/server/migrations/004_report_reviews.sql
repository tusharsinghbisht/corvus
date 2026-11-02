CREATE TABLE report_reviews (
    id uuid PRIMARY KEY,
    attempt_id uuid NOT NULL REFERENCES triage_attempts(id),
    sequence integer NOT NULL CHECK (sequence > 0),
    reviewer_id uuid NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    decision text NOT NULL CHECK (decision IN ('accepted','rejected','follow_up')),
    note text NOT NULL CHECK (length(btrim(note)) BETWEEN 10 AND 2000),
    evidence_checked boolean NOT NULL,
    analysis_id uuid NOT NULL,
    evidence_digest text NOT NULL CHECK (evidence_digest ~ '^[a-f0-9]{64}$'),
    report_digest text NOT NULL CHECK (report_digest ~ '^[a-f0-9]{64}$'),
    generation_validator_version text NOT NULL,
    revalidation jsonb NOT NULL,
    UNIQUE(attempt_id,sequence),
    CHECK (decision <> 'accepted' OR evidence_checked)
);
INSERT INTO schema_versions(version) VALUES (4);
