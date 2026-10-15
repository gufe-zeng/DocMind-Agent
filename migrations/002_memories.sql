-- M4b long-term preference memory (local demonstration, unauthenticated).
-- Never automatically promote raw document content or chat logs.
CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    memory_type TEXT NOT NULL CHECK (memory_type IN ('preference')),
    memory_key TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding_model TEXT,
    is_indexed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, memory_key)
);
CREATE INDEX IF NOT EXISTS memories_user_idx ON memories (user_id, memory_type);
