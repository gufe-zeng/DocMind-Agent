# M6b Acceptance — 2026-10-15

**Decision: M6b Completed; therefore M6 Completed and M0–M6 have passed local functional acceptance.**

## Execution environment and gate

The developer ran `docker compose up -d --build api` followed by `scripts\check_m6b.bat` from Windows CMD. Docker rebuilt the FastAPI image successfully; PostgreSQL and Redis were healthy, Qdrant was running, and the API container started. The two-phase smoke test deliberately restarted **only the API container**, leaving database and cache volumes intact.

The script executed a real FastAPI / LangGraph / PostgreSQL approval flow using a **synthetic contract and review-note content**. Qwen was not needed for this deterministic protected-write validation.

## Verified results

| Acceptance condition | Observed console evidence | Outcome |
|---|---|---|
| Durable pending approval | `PASS pending approval persisted and no pre-approval write` | PASS |
| No write before human decision | Same assertion checked an empty `review_notes` result | PASS |
| Official LangGraph interruption | `PASS LangGraph interrupted before save_review_note` | PASS |
| Scope mismatch and paused thread protection | `PASS mismatched scope denied and paused thread protected` | PASS |
| Durable state through API restart | `PASS approval + paused graph survive API container restart` | PASS |
| Approval resumes checkpoint and writes once | `PASS approved note saved once after LangGraph resume` | PASS |
| Same decision replay is idempotent; conflicting decision denied | `PASS approval replay idempotent; conflicting decision rejected` | PASS |
| Rejection and replay forbid writes and subsequent approval | `PASS reject/replay never writes and later approval blocked` | PASS |
| Malformed write request is rejected before pending creation | `PASS malformed write request rejected before creating approval` | PASS |

## Terminal success

```text
M6b PREPARE PASS — restart API and resume the checkpoint
M6b HITL PASS
M6b HITL validation passed.
```

## Implementation boundary

- Frozen endpoints: `POST /v1/chat` to prepare an explicit `save_review_note` command, and `POST /v1/approvals/{approval_id}` for the human approve/reject decision.
- PostgreSQL stores the durable pending decision and committed `review_notes`; the LangGraph PostgreSQL Checkpointer stores the interrupted workflow.
- The approval record is persisted **before** the protected note write, and approved/rejected paths and repeated decisions were tested.
- Real API restart and continuation were verified. This **does not** demonstrate recovery from arbitrary worker crashes or guarantee exactly-once behavior for general external side effects.
- `user_id` and `session_id` are caller-supplied local-demo UUIDs, **not verified identities or authorization**. The service must remain local-only until authentication, access control and retention policies are implemented.
- No claims are made about production concurrency, broad workload evaluation or claim-level semantic citation accuracy.

**Follow-on:** prioritize one end-to-end demonstrable document-analysis scenario that combines real Qwen, source citations, Agent tool selection and HITL review-note approval. V1 M7 (RAG/Agent/System Eval), M8 (Agent Metrics + Trace), and M9 (Engineering wrap-up + Demo + Resume) remain planned, not completed.