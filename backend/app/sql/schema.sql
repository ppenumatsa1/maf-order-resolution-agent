CREATE TABLE IF NOT EXISTS workflow_runs (
    thread_id TEXT PRIMARY KEY,
    session_id TEXT,
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

CREATE TABLE IF NOT EXISTS idempotency_keys (
    idempotency_key TEXT PRIMARY KEY,
    workflow_run_id TEXT NOT NULL,
    step_name TEXT NOT NULL,
    business_id TEXT NOT NULL,
    status TEXT NOT NULL,
    result JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_idempotency_keys_run_step
    ON idempotency_keys (workflow_run_id, step_name);

CREATE TABLE IF NOT EXISTS responses_dispatches (
    idempotency_key TEXT PRIMARY KEY,
    request_hash TEXT NOT NULL,
    run_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_responses_dispatches_thread_id
    ON responses_dispatches (thread_id);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    customer_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_updated_at
    ON sessions (updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_session_id
    ON workflow_runs (session_id);

ALTER TABLE workflow_runs
    ADD COLUMN IF NOT EXISTS session_id TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'workflow_runs_session_id_fkey'
    ) THEN
        ALTER TABLE workflow_runs
            ADD CONSTRAINT workflow_runs_session_id_fkey
            FOREIGN KEY (session_id)
            REFERENCES sessions(session_id)
            ON DELETE SET NULL;
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS eval_runs (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    summary JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_eval_runs_started_at
    ON eval_runs (started_at DESC);

CREATE TABLE IF NOT EXISTS eval_results (
    id UUID PRIMARY KEY,
    eval_run_id UUID NOT NULL REFERENCES eval_runs(id) ON DELETE CASCADE,
    case_id TEXT NOT NULL,
    passed BOOLEAN NOT NULL,
    score DOUBLE PRECISION,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_eval_results_eval_run_case
    ON eval_results (eval_run_id, case_id);
