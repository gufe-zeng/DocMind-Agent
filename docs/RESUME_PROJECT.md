# DocMind-Agent 简历项目与面试讲述（证据版）

> **源码学习入口**：[完整中文项目学习手册](LEARNING_GUIDE_CN.md)（21 章、58 道 Agent/RAG 高频问答、代码跟踪、实战练习与排障）。
>
> **高频追问补充**：[2026 Agent 开发面试精选 28 题](AGENT_INTERVIEW_HIGH_FREQUENCY_SUPPLEMENT_CN.md)——以公开面经与官方资料核对，优先练习 Context Engineering、工具路由、评测和系统设计。

> 适用于 Agent / LLM 应用 / RAG 工程岗位。M0–M9 已完成本地合成任务功能验收，包括真实 Qwen 的 M9 LIVE 问答；但 Grafana 面板与正式镜像重建仍待独立核查。不要写“产品上线”“生产级”“大规模部署”或编造收益。

## 一页简历可用的项目描述

**DocMind-Agent｜复杂合同文档知识 Agent（个人工程项目）**  
**技术栈：** Python、FastAPI、LangGraph、Qdrant、PostgreSQL、Redis、
BGE Embedding、BM25/RRF、BGE Reranker、MCP、Qwen/vLLM、
Prometheus、Docker Compose。

- **业务与系统架构：** 针对合同等复杂文档难以定位原始条款、答案缺乏来源及多轮分析状态难维护的问题，构建从 PDF/DOCX/TXT 解析、分块、向量索引到可引用问答的完整 RAG-Agent 链路；保留 Chunk、文档及页码来源元数据。
- **检索与 Agent：** 使用 BGE Dense + 字符级 BM25，经 RRF 融合、Cross-Encoder 重排形成证据；基于 LangGraph 实现有限步工具调用、结构化抽取、文档摘要与 MCP Server/Client 四类文档工具，支持多工具执行及跨工具引用编号归一。
- **记忆与安全写入：** 设计 Redis 会话记忆、PostgreSQL Checkpoint 与 PostgreSQL/Qdrant 长期偏好检索；对审核备注写入使用 LangGraph Interrupt/Resume + 人工审批，批准前不写入、拒绝无写入、重复批准幂等。
- **可靠性与可观测性：** 为只读工具设置超时、最多两次重试与无事实编造的 Fallback；接入 PostgreSQL 持久化 Trace、Prometheus 请求/工具/检索耗时及真实模型 Token 指标，并通过 Docker 自动化回归验收。

**可追问的测试证据：** M7a 三个合成文档查询 Recall@3=100%、MRR@3=1.0；M7b 七个合成 Agent 任务成功率 100%、工具选择准确率 100%（共八次工具调用）；M9 BASE 完成七项跨组件业务检查，LIVE 通过一次真实 Qwen 的合同付款期限问答与来源引用。以上均为**本地合成任务**，不能写成实际合同场景的总体准确率或收益改善。

## 面试中的 30 秒版本

“我独立实现了一个面向合同类复杂文档的 RAG Agent。用户上传 PDF、DOCX 或 TXT 后，系统保留文档和页码来源，通过 Dense/BM25/RRF 混合检索与重排提供可引用证据。LangGraph 负责有界工具调度，并通过真正的 MCP Client/Server 调用文档工具；Redis、PostgreSQL 和 Qdrant 分别支持会话、检查点和长期偏好。对于审核备注这类写操作，我设计了审批中断、状态持久化和幂等恢复。项目有自动化评测和 PostgreSQL Trace/Prometheus 指标，并完成了本地 Docker 验收。”

## 技术面试常见追问

**1. 为什么使用混合检索而不是只用向量检索？**  
BGE Dense 提供语义近似，中文 BM25 提供明确词面约束，RRF 在不假设分数可比的情况下融合排序；随后用 Cross-Encoder 对候选证据重排。文档 ID 过滤和 Chunk 来源贯穿全链路。

**2. 这是自主 Agent 吗？**  
是受约束的工具型 Agent，而非开放式自主智能体。简单任务是显式规则路由；包含抽取和摘要的复杂任务可使用 Qwen 规划必要工具的顺序，但执行工具必须在允许集合内，最多八步。

**3. MCP 带来什么工程价值？**  
将文档查询能力隔离为独立的 stdio MCP Server。LangGraph 通过真实 MCP Client 调用，而不是在 Agent 中直接 import 对应 Python 方法；通过协议层验证工具名称、参数和来源数据。

**4. Human-in-the-Loop 的幂等怎么保证？**  
写入前暂停 LangGraph，并创建 PostgreSQL pending 审批记录；批准后恢复图，再由数据库受保护的写入路径落库。同一 approval ID 关联唯一 review_note，重复批准不会重复写，冲突决定返回 409。

**5. 故障发生时能否安全降级？**  
普通只读工具针对临时性故障最多重试两次，超出预算返回无证据的 fallback；长耗时 CPU BGE 重排对应的 RAG/摘要工具采用单次有界执行（默认 420 秒），避免取消协程后重复启动仍在工作的 ONNX 线程。成功工具的来源引用会保留，受审批保护的写入不参与自动重试。

**6. 项目是否做过性能测试？**  
做过少量串行本机测量，没有并发压测。M7c 的 BGE CPU Rerank 两次耗时约 172–259 秒，检索约 0.42–0.49 秒；目前正视重排瓶颈，不夸大吞吐指标。Dockerfile 通过缓存第三方依赖层降低后续源码迭代的重复构建成本，但没有测得具体加速比例。

**7. 上线前还缺什么？**  
真实鉴权与 RBAC、敏感文档权限隔离、Trace 数据保留策略、真实语义事实准确性评估、并发容量测试以及更高效的重排推理部署。简历描述仅陈述当前已实现和验收的功能。

## 演示与证据文件

- `docs/M9_DEMO.md`：演示命令与固定场景；
- `docs/M7A_ACCEPTANCE.md`、`docs/M7B_ACCEPTANCE.md`、
  `docs/M7C_ACCEPTANCE.md`：量化评测证据；
- `docs/M6B_ACCEPTANCE.md`：人工审批恢复与幂等；
- `docs/M8_ACCEPTANCE.md`：真实 Trace 与 Prometheus；
- `docs/M9_ACCEPTANCE.md`：BASE/LIVE 真实本机验收证据；
- `docs/RELEASE_CHECKLIST.md`：V1 完成条件和未完成项。
