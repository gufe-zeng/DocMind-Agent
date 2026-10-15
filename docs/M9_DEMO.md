# M9 — V1 业务演示与工程收尾

**状态：代码已准备，等待本机 BASE/LIVE 验收。**

本阶段只集成冻结 V1 的已有能力，不增加新的公网 API、新模型和未经验证的功能。

## 使用方法：只构建一次

在 Windows CMD：

```cmd
cd /d E:\project\DocMind-Agent
git pull
docker compose up -d --build api
scripts\check_m9.bat
```

本次 API 构建一次后，`check_m9.bat` 不再触发构建。M8 已将第三方依赖安装移到源码 COPY 之前；源码发生普通改动时通常可复用 BuildKit 依赖缓存。

### BASE：无需 Qwen

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

### LIVE：真实 Qwen，只增加一次问答

运行 BASE 后，保证独立 `llm-serving-ops` 的 Qwen/vLLM 服务在 Windows 主机 8000 端口可访问，然后执行：

```cmd
scripts\check_m9_live.bat
```

LIVE 复用 BASE 已索引的合同，通过 `POST /v1/chat` 验证
`search_documents` → Dense+BM25+RRF → BGE Rerank → Qwen 生成
→ 有效文档引用，同时检查 M8 Trace 中存在真实 LLM 调用。

预期：

```text
M9 DEMO LIVE PASS
M9 live demo validation passed.
```

此前 CPU BGE Rerank 的独立测量约为 172–259 秒；这与 Docker 构建耗时不同。LIVE 可能较慢，无需反复运行。

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
