# M8 Observability Acceptance

**Status: implementation submitted; local BASE and optional dashboard checks pending.**

The M8 GitHub change adds:
- request `trace_id` for chat and protected approval;
- bounded LangGraph node spans and M6 tool-event latency metrics;
- schema `004_agent_traces.sql` with PostgreSQL durability;
- Prometheus counters and histograms on the existing `/metrics` route;
- privacy-safe structured logs and model usage counters;
- faster Docker rebuild layering and optional Prometheus/Grafana configs.

**Do not mark M8 Completed until the actual Docker two-stage acceptance
prints `M8 OBSERVABILITY PASS`.** Unit tests and GitHub CI do not replace
the database/restart checks. The optional dashboard requires fetching
third-party container images and can be checked independently without
another API rebuild. See [M8 guide](OBSERVABILITY.md).
