# Application migrations

The API applies these idempotent PostgreSQL migration files at startup,
in order; LangGraph maintains its own checkpointer migrations.

- `001_documents.sql`: uploaded/indexed document metadata.
- `002_memories.sql`: explicit user preference persistence.
- `003_approvals.sql`: durable Human Approval and review notes.
- `004_agent_traces.sql`: redacted request/node/tool telemetry.

M8 trace rows are durable but **not** an audit-grade compliance log.
Do not store user questions, original documents, prompts, model replies
or secrets in telemetry. Retention/deletion and reader permissions must
be designed before non-local deployment.
