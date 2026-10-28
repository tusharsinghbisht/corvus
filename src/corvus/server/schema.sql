CREATE TABLE users (
    id uuid PRIMARY KEY,
    username text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE sessions (
    token_hash text PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES users(id),
    expires_at timestamptz NOT NULL
);
CREATE TABLE login_failures (at timestamptz NOT NULL DEFAULT now());
CREATE INDEX login_failures_at ON login_failures(at);

CREATE TABLE connections (
    id uuid PRIMARY KEY,
    name text NOT NULL UNIQUE,
    indexer_url text NOT NULL UNIQUE,
    username text NOT NULL,
    encrypted_password text NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    backfill_start timestamptz NOT NULL,
    checkpoint timestamptz NOT NULL,
    last_sync_at timestamptz,
    last_error text,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE alerts (
    id uuid PRIMARY KEY,
    connection_id uuid NOT NULL REFERENCES connections(id),
    native_index text NOT NULL,
    native_id text NOT NULL,
    timestamp timestamptz NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    agent_id text,
    agent_name text,
    rule_id text,
    rule_level integer NOT NULL CHECK (rule_level BETWEEN 0 AND 16),
    title text NOT NULL,
    document jsonb NOT NULL,
    UNIQUE (connection_id, native_index, native_id)
);
CREATE INDEX alerts_time ON alerts(timestamp DESC, id DESC);
CREATE INDEX alerts_connection ON alerts(connection_id, timestamp DESC);
CREATE INDEX alerts_severity ON alerts(rule_level, timestamp DESC);
CREATE INDEX alerts_agent ON alerts(agent_id, timestamp DESC);

CREATE TABLE audit_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    at timestamptz NOT NULL DEFAULT now(),
    user_id uuid REFERENCES users(id),
    action text NOT NULL,
    target text
);
INSERT INTO schema_versions(version) VALUES (1);
