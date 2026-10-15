# M7b Acceptance — 2026-10-15

**Decision: M7b Completed (real local Docker Agent/MCP acceptance).**

## Environment and evidence

The user ran `scripts\check_m7b.bat` with the existing Docker
PostgreSQL, Redis, Qdrant and cached BGE stack. This test did not require Qwen.
It indexed one synthetic TXT contract and a synthetic two-page PDF, then
sent seven independent `POST /v1/chat` requests through the real Agent.
All seven reported `status=answered`.

```text
PASS M7b API ready
CASE direct_metadata: status=answered tools=['query_document_metadata'] steps=1
CASE extract_supported_fields: status=answered tools=['extract_entities'] steps=1
CASE mcp_metadata: status=answered tools=['mcp_get_document'] steps=1
CASE mcp_clause: status=answered tools=['mcp_find_clause'] steps=1
CASE mcp_pdf_page: status=answered tools=['mcp_get_document_page'] steps=1
CASE mcp_search: status=answered tools=['mcp_search_documents'] steps=1
CASE mcp_multitool: status=answered tools=['mcp_get_document', 'mcp_find_clause'] steps=2
M7b AGENT EVAL PASS
M7b Agent evaluation validation passed.
```

## Observed metrics

| Metric | Observed |
|---|---:|
| Synthetic fixture cases | 7 |
| Task Success Rate | 1.0 (7/7) |
| Tool Selection Accuracy | 1.0 |
| MCP Tool Selection Accuracy | 1.0 |
| Tool Success Rate | 1.0 (8/8 tool calls) |
| Average Agent Steps | 1.1428571428571428 |
| Responses with step counts | 7 |
| Failure Rate | 0.0 |

The total of eight calls comprises six one-step requests and one
two-tool request. The gold fixture checks required literal content,
supported deterministic entity values, citation provenance,
document/page scope, reported steps and tool/MCP identities.

## Limits

This is a **synthetic, rule/MCP-backed** evaluation on only seven cases,
without an LLM judge, real legal dataset or Qwen planning/generation.
The 100% values must not be reported as an open-domain Agent effectiveness
estimate or as a legal-semantic citation faithfulness score.

Next: M7c system latency and token-usage evaluation, then M8
request/node traces and operational metrics.
