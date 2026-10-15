-- M8: minimal, source-redacted per-attempt trace metadata.
-- No document text, user question, model output or secrets are persisted.
CREATE TABLE IF NOT EXISTS agent_traces (
    trace_id UUID PRIMARY KEY,
    request_id UUID NOT NULL UNIQUE,
    session_id UUID,
    operation TEXT NOT NULL CHECK (operation IN ('chat', 'approval')),
    status TEXT NOT NULL,
    http_status SMALLINT NOT NULL,
    intent TEXT,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ NOT NULL,
    duration_ms DOUBLE PRECISION NOT NULL CHECK (duration_ms >= 0),
    steps INTEGER CHECK (steps >= 0),
    tool_names JSONB NOT NULL DEFAULT '[]'::jsonb,
    node_events JSONB NOT NULL DEFAULT '[]'::jsonb,
    tool_events JSONB NOT NULL DEFAULT '[]'::jsonb,
    llm_calls INTEGER NOT NULL DEFAULT 0 CHECK (llm_calls >= 0),
    prompt_tokens INTEGER CHECK (prompt_tokens >= 0),
    completion_tokens INTEGER CHECK (completion_tokens >= 0),
    error_type TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS agent_traces_session_idx
    ON agent_traces (session_id, created_at DESC);
