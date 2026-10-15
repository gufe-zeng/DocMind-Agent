# M4a Acceptance Record — 2026-10-15

**Decision: M4a Completed (live Docker, Redis, PostgreSQL, Qwen3).**

User ran `scripts\check_m4a.bat` in Windows CMD after rebuilding API.

## Observed outcome

- `docker compose up -d --build api` succeeded after installing Psycopg binary.
- `/health` returned `status=ok` with postgres, redis and qdrant all `up`.
- The `/health` field `stage=M1` was a stale display label; corrected in code to M4a.
- Uploaded and indexed synthetic contract document ID:
  `a22f519f-32e0-4732-845d-67886a018ee4`.
- First question: `根据合同，验收合格后付款期限是多少天？`
- First response: `付款期限是三十天 [S1]。`; context_applied=False.
- Session ID: `77213311-846e-4fe6-acc3-1ac79c7b7b23`.
- Second question (same session, no document_id): `如果逾期呢？`.
- Second response: `根据合同条款，如果逾期未支付款项，甲方应按照合同约定承担违约责任，每日按逾期未支付金额的千分之一支付违约金。[S1]`.
- context_applied=True, correct inherited document ID.
- `PASS same-session document resolution and follow-up expansion`.
- `PASS Redis persisted two bounded session turns`.
- `PASS Redis session TTL: 3600`.
- `PASS independent PostgreSQL checkpoint load`.
- Final: **`M4a PASS`** / **`M4a validation passed.`**.

## Limits

This is an actual functional multi-turn acceptance, not a general
dialogue-coreference benchmark. The query-rewriting logic is conservative
and deterministic. Persistent cross-session semantic memory and interrupted
graph continuation remain M4b tasks.

No production authentication or per-user authorization is implemented.

Next: M4b structured/semantic long-term memory and resume testing.