-- M6b local-demo Human Approval for a single protected write action.
-- Approved decisions and review notes have separate durable states so
-- LangGraph can resume after a recorded decision without double-writing.
CREATE TABLE IF NOT EXISTS approvals (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL,
    user_id UUID NOT NULL,
    document_id UUID NOT NULL REFERENCES documents(id),
    tool_name TEXT NOT NULL CHECK (tool_name = 'save_review_note'),
    note_text TEXT NOT NULL CHECK (char_length(note_text) BETWEEN 1 AND 500),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected')),
    review_note_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    decided_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS approvals_session_idx
    ON approvals (session_id, created_at);

CREATE TABLE IF NOT EXISTS review_notes (
    id UUID PRIMARY KEY,
    approval_id UUID NOT NULL UNIQUE REFERENCES approvals(id),
    document_id UUID NOT NULL REFERENCES documents(id),
    session_id UUID NOT NULL,
    user_id UUID NOT NULL,
    content TEXT NOT NULL CHECK (char_length(content) BETWEEN 1 AND 500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS review_notes_document_idx
    ON review_notes (document_id, created_at);
