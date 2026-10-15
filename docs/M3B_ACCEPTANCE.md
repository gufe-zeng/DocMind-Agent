# M3b Live Acceptance — 2026-10-15

**Decision: M3b COMPLETED; M3 COMPLETE (functional acceptance).**

The developer ran `scripts\check_m3b.bat` inside Windows Docker Desktop using
the actual PostgreSQL/Qdrant services, cached ModelScope CPU ONNX models and
live Qwen3 served by `llm-serving-ops`.

## Document

- Uploaded and indexed `m3b_contract.txt`.
- Document ID: `d8f0fcca-0a13-428e-97f7-fdaa1c123d61`.

## Test 1 — Source-anchored field extraction

- Query: `提取甲乙方及付款期限`.
- `plan_source=rules`, `tools_called=['extract_entities']`, status `answered`.
- Extracted `甲方示例科技有限公司` [S1], `乙方示例服务有限公司` [S2],
  and a payment deadline of `三十日` [S3].
- Terminal check: `PASS cited deterministic entity extraction`.

## Test 2 — Evidence-scoped summary using live Qwen

- Query: `总结合同付款条款和违约责任`.
- `plan_source=rules`, `tools_called=['summarize_document']`, status `answered`.
- Generated a summary of parties, acceptance-conditioned 30-day payment and
  contractual breach liability, with [S1] and an explicit retrieved-excerpts
  coverage limitation.
- Terminal check: `PASS evidence-scoped live Qwen summary`.

## Test 3 — Model-assisted multi-tool planning

- Query: `提取甲乙方并总结合同付款和违约责任`.
- `plan_source=llm_validated`.
- Tools: `['extract_entities', 'summarize_document']`; status `answered`.
- The extraction cited [S1]–[S3]; Qwen summary cited [S4], showing that
  independently assigned tool IDs were unified correctly.
- Terminal check: `PASS multi-tool LangGraph plan + unique citations`.

## Final console gate

`M3b PASS` / `M3b validation passed.`

**The full M3 functional acceptance is complete.** This is an actual
end-to-end demonstration, not a benchmark of entity recall, task success
across unseen tasks, or citation entailment. Rule fallback exists but this
particular run used valid Qwen planning, not fallback.

Next milestone: M4 working/session/long-term/checkpoint memory.