# Evaluation fixtures (synthetic)

Only synthetic documents and explicit gold labels are committed here.
Do not place customer or private legal documents in this directory.

- `m7a_retrieval.json`: 3 synthetic document-level query/relevance cases
  for hybrid retrieval ranking. See `docs/M7A_ACCEPTANCE.md`.
- `m7b_agent.json`: 7 scoped Agent cases with expected tool sets,
  optional MCP tool sequence, literal answer/entity assertions, and
  citation provenance requirements. See `docs/EVALUATION.md`.

The scripts upload fresh documents on every run. Because Qdrant uses
persistent shared collections, global retrieval scores may vary over time.
All evaluation units and metric denominators must be reported.
