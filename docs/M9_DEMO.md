# M9 — V1 业务演示与工程收尾

**状态：BASE 与真实 Qwen LIVE 均已于 2026-10-15 通过本机功能验收。** Grafana 和最新镜像的正式构建仍待验证。

本阶段只集成冻结 V1 的已有能力，不增加新的公网 API、新模型和未经验证的功能。

## 使用方法：已有本地验收通过；正式更新镜像构建待网络恢复

在 Windows CMD：

```cmd
cd /d E:\project\DocMind-Agent
git pull
docker compose up -d --build api
scripts\check_m9.bat
```

以上是网络恢复后验证正式镜像的标准命令。**当前 M9 已通过本地运行功能验收，不必为证明同一结果而再次调用 Docker Hub。** 本次是在原有 API 容器内复制 Python 修复文件完成 LIVE 复验；最新镜像的构建仍受 Docker 镜像代理/DNS 故障阻碍。

### BASE：无需 Qwen（2026-10-15 已验收通过）

自动执行真实 Docker API 流程：

1. 健康检查并上传、索引模拟合同 TXT、两页 PDF 和 DOCX。
2. LangGraph 经 MCP Client/Server 顺序调用 `get_document` 和 `find_clause`，核实来源与引用编号。
3. 直接提取合同甲乙方及付款期限，要求字段值与来源对应。
4. 从 PDF 第二页和 DOCX 检索真实页码/片段来源。
5. 在同一 Redis Session 中追问，验证文档上下文与 PostgreSQL Checkpoint。
6. 保存明确的合同输出偏好，在新 Session 中从长期记忆重新检索。
7. 测试 HITL 审核备注：未批准不能写；批准后写一次；重复批准不重复写；冲突决定返回 409。
8. 检查 PostgreSQL 的 Agent Trace 和现有 `GET /metrics` 指标。

最终预期：

```text
M9 DEMO BASE PASS
M9 base demo validation passed.
```

脚本仅使用合成数据。运行时会在已有 Docker 文档卷中保存
`/app/data/uploads/.m9_demo_state.json` 和
`/app/data/uploads/.m9_demo_report.json`，用于保存合成文档 UUID、各阶段状态与 Trace UUID。报告不包含合同内容或模型回答；不会上传到 GitHub。

### LIVE：真实 Qwen，已完成本机验收

运行 BASE 后，保证独立 `llm-serving-ops` 的 Qwen/vLLM 服务在 Windows 主机 8000 端口可访问，然后执行：

```cmd
scripts\check_m9_live.bat
```

LIVE 复用 BASE 已索引的合同，通过 `POST /v1/chat` 验证
`search_documents` → Dense+BM25+RRF → BGE Rerank → Qwen 生成
→ 有效文档引用，同时检查 M8 Trace 中存在真实 LLM 调用。

2026-10-15 实测输出：

```text
PASS real Qwen hybrid-RAG answer with factual deadline/citation
PASS Qwen request and token observations in Agent telemetry
M9 DEMO LIVE PASS
M9 live demo validation passed.
```

此前 CPU BGE Rerank 的独立测量约为 172–259 秒；这与 Docker 构建耗时不同。LIVE 可能较慢，无需反复运行。

**已诊断的 M9 LIVE 问题：** 原 `search_documents` 在 90 秒后超时，最多重复三次，总计耗时约 270 秒，`llm_calls=0`。新策略对包含 CPU Rerank 的 `search_documents` 和 `summarize_document` 采用 420 秒（可配置 300–600 秒）的整工具预算，超时不重试，避免已经启动的 CPU 工作线程被重复触发；ONNX 重排串行执行。

以上超时缺陷已修复，且经当前本机 LIVE 复验通过。下列操作仅用于未来在**网络恢复后**重建正式镜像，并非当前必须再做的验收步骤：

```cmd
git pull
docker compose up -d --build api
scripts\check_m9_live.bat
```

新镜像构建后的额外环境验证尚未进行。若未来 CPU 延迟高于 420 秒，先检查 `tool_events.error_type` 再调整 `RAG_CPU_TIMEOUT_SECONDS`，不要无证据地持续增加超时或重复运行昂贵推理。

## 分项评测，不需要重建镜像

```cmd
scripts\run_eval.bat rag
scripts\run_eval.bat agent
scripts\run_eval.bat system
scripts\run_eval.bat system-live
scripts\run_eval.bat trace
scripts\run_eval.bat demo
scripts\run_eval.bat demo-live
```

以上均使用已运行的 API 镜像。除非需要重新测量，不建议再次执行昂贵的 M7c Rerank 评测。

## 可选 Grafana 验收

严格的冻结 V1 检查项包含 Grafana。M8 核心 Metrics/Trace 已通过，
但 Grafana Dashboard 仍未得到你的本机验收证据。
这一步需要首次拉取 Prometheus/Grafana 镜像，但不需要重建 API：

```cmd
set DOCMIND_GRAFANA_ADMIN_PASSWORD=choose-a-local-password
docker compose -f compose.yaml -f compose.observability.yaml up -d prometheus grafana
scripts\check_m8_dashboards.bat
```

还应人工确认 `http://127.0.0.1:3091` 的 DocMind Dashboard 可见、
`http://127.0.0.1:9091/targets` 中 `docmind-agent` 为 UP。
不要将演示 API 暴露给不受信任的用户。

## 演示边界

M9 是固定合成场景下的 API/CLI Demo，不是已经实现的 Web 前端。
它不证明真实合同的总体准确率、引用语义蕴含、吞吐量、生产鉴权或不限场景自主规划。简历描述见 [RESUME_PROJECT.md](RESUME_PROJECT.md)，正式验收见 [M9_ACCEPTANCE.md](M9_ACCEPTANCE.md)。


## Docker 镜像源不可用时的旧版导入路径问题

若使用 `docker compose cp` 向旧 API 容器临时更新了 Python 文件，
`python scripts/check_m9.py live` 可能优先导入原来安装在
`site-packages` 的旧版 `app`，而不是 `/app/app` 中的新代码。
新版本的 BASE/LIVE BAT 已统一设置 `PYTHONPATH=/app`，并以
`python -m scripts.check_m9` 启动。先检查：

```cmd
git pull
docker compose exec -T -e PYTHONPATH=/app api python -c "import app.core.config as c; print(c.__file__); print(c.get_settings().rag_cpu_timeout_seconds)"
scripts\check_m9_live.bat
```

正常应输出 `/app/app/core/config.py` 和 `420.0`，无需重建镜像，
也不需要重新运行已通过验收的 BASE。若上述检查仍缺失新字段，
单独复制 `app/core/config.py` 到旧容器，按需重启 API。

## 最终功能验收结论

2026-10-15：M9 BASE（多格式文档、MCP、记忆、HITL、Trace）与
M9 LIVE（`search_documents` → CPU BGE 重排 → 真实 Qwen 回答与文档引用）
均已通过。本次 LIVE 使用 Docker 容器内的修复源码及
`PYTHONPATH=/app` 模块入口，`rag_cpu_timeout_seconds=420.0`。
仍待独立完成 Grafana 面板验证、镜像源网络修复及正式镜像重建。
