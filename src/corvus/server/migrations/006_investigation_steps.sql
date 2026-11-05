ALTER TABLE triage_attempts ADD COLUMN workflow text NOT NULL DEFAULT 'direct' CHECK(workflow IN ('direct','agentic'));
ALTER TABLE triage_attempts ADD CONSTRAINT automatic_single_request CHECK(mode<>'automatic' OR workflow='direct');
CREATE TABLE investigation_steps (
    id uuid PRIMARY KEY,
    attempt_id uuid NOT NULL REFERENCES triage_attempts(id),
    position integer NOT NULL CHECK(position BETWEEN 1 AND 5),
    phase text NOT NULL CHECK(phase IN ('plan','correlation','intel','assessment')),
    state text NOT NULL CHECK(state IN ('running','completed','failed','unknown')),
    model_request boolean NOT NULL,
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    completed_at timestamptz,
    input_snapshot jsonb NOT NULL,
    output jsonb,
    error_code text,
    UNIQUE(attempt_id,position),
    CHECK(model_request=(phase IN ('plan','assessment')))
);
CREATE INDEX investigation_step_tasks ON investigation_steps(phase,started_at DESC);
INSERT INTO schema_versions(version) VALUES(6);
