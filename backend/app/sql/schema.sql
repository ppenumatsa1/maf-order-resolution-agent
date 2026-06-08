CREATE TABLE IF NOT EXISTS workflow_runs (
    thread_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    input TEXT NOT NULL,
    input_summary TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    latest_output JSONB,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER,
    current_stage TEXT
);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_status_created_at
    ON workflow_runs (status, created_at DESC);

CREATE TABLE IF NOT EXISTS workflow_events (
    id UUID PRIMARY KEY,
    thread_id TEXT NOT NULL REFERENCES workflow_runs(thread_id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_workflow_events_thread_timestamp
    ON workflow_events (thread_id, timestamp ASC);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id BIGSERIAL PRIMARY KEY,
    thread_id TEXT NOT NULL REFERENCES workflow_runs(thread_id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversation_messages_thread_id
    ON conversation_messages (thread_id, id ASC);

CREATE TABLE IF NOT EXISTS checkpoints (
    checkpoint_id UUID PRIMARY KEY,
    thread_id TEXT NOT NULL REFERENCES workflow_runs(thread_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL,
    state JSONB NOT NULL,
    reviewer TEXT,
    comments TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_thread_created_at
    ON checkpoints (thread_id, created_at DESC);

CREATE TABLE IF NOT EXISTS approvals (
    approval_id UUID PRIMARY KEY,
    thread_id TEXT NOT NULL REFERENCES workflow_runs(thread_id) ON DELETE CASCADE,
    checkpoint_id UUID NOT NULL REFERENCES checkpoints(checkpoint_id) ON DELETE CASCADE,
    action TEXT,
    order_id TEXT,
    amount DOUBLE PRECISION,
    question TEXT,
    reviewer TEXT,
    comments TEXT,
    status TEXT NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_approvals_thread_requested_at
    ON approvals (thread_id, requested_at DESC);

CREATE INDEX IF NOT EXISTS idx_approvals_checkpoint_status
    ON approvals (checkpoint_id, status);
