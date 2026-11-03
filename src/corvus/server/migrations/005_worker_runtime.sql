CREATE TABLE worker_runtime (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    heartbeat_at timestamptz,
    analysis_configured boolean NOT NULL DEFAULT false
);
INSERT INTO worker_runtime(singleton) VALUES(true);
INSERT INTO schema_versions(version) VALUES (5);
