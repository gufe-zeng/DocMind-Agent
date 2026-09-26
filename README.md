# DocMind-Agent

> 面向复杂文档的可追溯 RAG Agent 系统。

DocMind-Agent V1.0 的目标是面向法律、政务、合同等复杂文档，构建一条可解释、可评测、可恢复、可观测的 Agent 应用链路：

```text
Document Pipeline
→ Hybrid RAG
→ Rerank
→ Citation
→ LangGraph Agent
→ Tool Calling
→ Memory
→ MCP
→ HITL
→ Eval
→ Observability
```

当前开发阶段：**M0 — 项目骨架 + PostgreSQL + Redis + Qdrant + FastAPI Health Check**。

V1 范围已冻结，详见 [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) 和 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## M0 Quick Start

复制环境变量：

```cmd
copy .env.example .env
```

启动基础设施与 API：

```cmd
docker compose up -d --build
```

查看状态：

```cmd
docker compose ps
```

验证：

```cmd
curl http://127.0.0.1:8090/health
```

预期 PostgreSQL、Redis、Qdrant 均为 `up`。

Prometheus 格式指标：

```cmd
curl http://127.0.0.1:8090/metrics
```

停止：

```cmd
docker compose down
```

也可以直接运行：

```cmd
scripts\bootstrap.bat
scripts\smoke_test.bat
```

## Development Modules

| Module | Scope | Status |
|---|---|---|
| M0 | Skeleton + PostgreSQL/Redis/Qdrant + Health | In progress |
| M1 | Document Pipeline | Planned |
| M2 | Hybrid RAG + Rerank + Citation | Planned |
| M3 | LangGraph Agent + Tool Calling | Planned |
| M4 | Session/Long-term Memory + Checkpoint | Planned |
| M5 | MCP Server + Client | Planned |
| M6 | Retry + Timeout + Fallback + HITL | Planned |
| M7 | RAG/Agent/System Eval | Planned |
| M8 | Agent Metrics + Trace | Planned |
| M9 | Engineering wrap-up + Demo + Resume | Planned |

## Related Project

Inference serving and observability base:

https://github.com/gufe-zeng/llm-serving-ops

## V1 Non-goals

V1 does **not** implement Multi-Agent, fine-tuning, Kubernetes, OCR, multimodal parsing, browser agents, A2A, autoscaling, or unlimited reflection.
