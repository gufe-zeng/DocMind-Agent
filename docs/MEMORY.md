# Memory Design

Status: **interface frozen; implementation scheduled for M4**.

V1 separates four concepts:

```text
Working Memory   → Agent State
Session Memory   → Redis
Long-term Memory → PostgreSQL + Qdrant memories_v1
Checkpoint       → PostgreSQL
```

The project does not equate raw chat history with a complete memory system.

## Policy

- Current tool intermediates remain in Working Memory.
- Recent conversation and summaries are session-scoped.
- Explicit reusable preferences and confirmed facts may become long-term memory.
- Temporary retrieval candidates are not promoted to durable memory.
- Sensitive temporary content is not written to long-term memory.
- Session data is TTL-managed.

Detailed schemas, retrieval and consolidation logic are implemented only in M4.
