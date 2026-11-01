ALTER TABLE triage_attempts ADD COLUMN analysis_evidence jsonb;
ALTER TABLE triage_attempts ADD COLUMN input_snapshot jsonb;
ALTER TABLE triage_attempts ADD COLUMN mode text NOT NULL DEFAULT 'manual' CHECK (mode IN ('manual','automatic'));
ALTER TABLE triage_attempts ADD COLUMN policy_version integer;
CREATE UNIQUE INDEX triage_one_automatic ON triage_attempts(job_id) WHERE mode='automatic';
CREATE TABLE analyst_policies (
    connection_id uuid PRIMARY KEY REFERENCES connections(id),
    enabled boolean NOT NULL DEFAULT false,
    minimum_level integer NOT NULL DEFAULT 12 CHECK (minimum_level IN (7,12,15)),
    hourly_limit integer NOT NULL DEFAULT 2 CHECK (hourly_limit BETWEEN 1 AND 20),
    daily_limit integer NOT NULL DEFAULT 10 CHECK (daily_limit BETWEEN 1 AND 100),
    version integer NOT NULL DEFAULT 1,
    activated_at timestamptz,
    consent_by uuid REFERENCES users(id),
    consent_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (NOT enabled OR (activated_at IS NOT NULL AND consent_by IS NOT NULL AND consent_at IS NOT NULL))
);
CREATE TABLE analyst_settings (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    daily_limit integer NOT NULL DEFAULT 20 CHECK (daily_limit BETWEEN 1 AND 200)
);
INSERT INTO analyst_settings(singleton) VALUES(true);
CREATE INDEX triage_auto_budget ON triage_attempts(created_at) WHERE mode='automatic';
INSERT INTO schema_versions(version) VALUES (3);
