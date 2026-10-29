CREATE TABLE triage_jobs (
    id uuid PRIMARY KEY,
    alert_id uuid NOT NULL UNIQUE REFERENCES alerts(id),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE triage_attempts (
    id uuid PRIMARY KEY,
    job_id uuid NOT NULL REFERENCES triage_jobs(id),
    number integer NOT NULL CHECK (number > 0),
    requested_by uuid NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    status text NOT NULL CHECK (status IN (
        'pending_collection','collecting','awaiting_approval','queued','requesting',
        'validated','rejected','failed','unknown','cancelled'
    )),
    collection_started_at timestamptz,
    evidence jsonb,
    evidence_digest text,
    approved_by uuid REFERENCES users(id),
    approved_at timestamptz,
    approved_digest text,
    request_started_at timestamptz,
    completed_at timestamptz,
    provenance jsonb,
    model_reply jsonb,
    result jsonb,
    error_code text,
    UNIQUE(job_id, number),
    CHECK (status NOT IN ('queued','requesting','validated','rejected') OR (
        evidence IS NOT NULL AND evidence_digest IS NOT NULL AND approved_by IS NOT NULL
        AND approved_at IS NOT NULL AND approved_digest = evidence_digest
    ))
);
CREATE UNIQUE INDEX triage_one_active ON triage_attempts(job_id)
    WHERE status IN ('pending_collection','collecting','awaiting_approval','queued','requesting');
CREATE INDEX triage_queue ON triage_attempts(created_at)
    WHERE status IN ('pending_collection','queued');
INSERT INTO schema_versions(version) VALUES (2);
