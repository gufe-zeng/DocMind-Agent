"""M3b: conservative routing plus bounded optional LLM tool planning.

Simple intents follow deterministic rules (preserving M3a behavior).
Complex extraction/summary requests allow the LLM to order a finite allowlist.
Invalid JSON, missing tools, or an unavailable model triggers rule fallback.
"""

from dataclasses import dataclass
import json
import re

from app.core.config import get_settings
from app.llm.client import complete_chat


METADATA_INTENTS = (
    "列出文档", "有哪些文档", "文档列表", "文件列表", "文档元数据",
    "文件信息", "已上传", "已经上传", "已索引", "有哪些文件",
    "列出文件", "文档信息",
)
CONTENT_INTENTS = (
    "付款", "违约", "条款", "期限", "主体", "责任", "问答",
    "告诉", "根据合同", "回答", "合同内容", "合同约定",
)
EXTRACTION_INTENTS = ("提取", "抽取", "甲乙方", "甲乙双方", "识别主体", "实体", "要素")
SUMMARY_INTENTS = ("总结", "摘要", "概述", "归纳", "整体情况", "主要风险")
ALLOWED_TOOLS = frozenset({
    "search_documents",
    "query_document_metadata",
    "extract_entities",
    "summarize_document",
    "mcp_find_clause",
    "mcp_get_document",
    "mcp_get_document_page",
    "mcp_search_documents",
})
MAX_PLANNED_TOOLS = 4


@dataclass(frozen=True, slots=True)
class PlanDecision:
    tools: list[str]
    source: str
    reason: str | None = None


def select_tool_plan(query: str) -> list[str]:
    """Produce a safe default plan from explicitly recognized intents."""
    if not query.strip():
        raise ValueError("Query cannot be empty.")

    # Explicit "MCP" routing is opt-in: existing RAG/Agent queries are
    # untouched. This is deterministic, audited adapter selection.
    if "mcp" in query.lower():
        plan: list[str] = []
        if any(term in query for term in ("文档信息", "文件信息", "元数据", "文档状态")):
            plan.append("mcp_get_document")
        if re.search(r"第\s*\d{1,4}\s*页", query):
            plan.append("mcp_get_document_page")
        if any(term in query for term in ("查找", "定位", "条款", "关键词")) and not re.search(
            r"第\s*\d{1,4}\s*页", query
        ):
            plan.append("mcp_find_clause")
        if any(term in query for term in ("检索", "搜索", "查询证据")) or not plan:
            plan.append("mcp_search_documents")
        return plan[:MAX_PLANNED_TOOLS]

    metadata = any(term in query for term in METADATA_INTENTS)
    extraction = any(term in query for term in EXTRACTION_INTENTS)
    summary = any(term in query for term in SUMMARY_INTENTS)
    content = any(term in query for term in CONTENT_INTENTS)

    plan: list[str] = []
    if metadata:
        plan.append("query_document_metadata")
    if extraction:
        plan.append("extract_entities")
    if summary:
        plan.append("summarize_document")

    direct_question = any(mark in query for mark in ("告诉我", "是多少", "是什么", "多少", "回答"))
    if content and (not (extraction or summary) or direct_question):
        plan.append("search_documents")
    if not plan:
        plan.append("search_documents")
    return plan[:MAX_PLANNED_TOOLS]


def _validated_model_plan(raw_text: str, required: list[str]) -> list[str]:
    text = raw_text.strip()
    fence = chr(96) * 3
    if text.startswith(fence):
        text = re.sub(r"^" + re.escape(fence) + r"(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*" + re.escape(fence) + r"$", "", text)
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("Tool plan must be a JSON object.")
    names = payload.get("tools")
    if (
        not isinstance(names, list)
        or not names
        or len(names) > MAX_PLANNED_TOOLS
        or any(not isinstance(name, str) for name in names)
    ):
        raise ValueError("Tool plan must contain a bounded list of strings.")
    if (
        len(set(names)) != len(names)
        or not set(names).issubset(ALLOWED_TOOLS)
        or set(names) != set(required)
    ):
        raise ValueError("Model plan violates allowlist or intent coverage.")
    return names


async def plan_tools(query: str, document_id: str | None = None) -> PlanDecision:
    fallback = select_tool_plan(query)
    complex_task = len(fallback) >= 2 and bool(
        {"extract_entities", "summarize_document"} & set(fallback)
    )
    if not complex_task or document_id is None:
        return PlanDecision(tools=fallback, source="rules")

    settings = get_settings()
    system = (
        "你是文档智能体工具规划器。只输出一个合法 JSON 对象，例如 "
        '{"tools":["extract_entities","summarize_document"]}。'
        "只能从四个工具中选择：search_documents、query_document_metadata、"
        "extract_entities、summarize_document。不得输出解释或代码块。"
        "必须保留全部必要任务、不得增加工具。"
    )
    user = (
        f"用户任务：{query}\n"
        f"必要工具（允许调整顺序，不可增删）：{json.dumps(fallback, ensure_ascii=False)}"
    )
    try:
        completion = await complete_chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            max_tokens=100,
            timeout_seconds=60.0,
        )
        chosen = _validated_model_plan(completion.text, fallback)
        return PlanDecision(tools=chosen, source="llm_validated")
    except Exception as exc:
        return PlanDecision(
            tools=fallback,
            source="rule_fallback",
            reason=type(exc).__name__,
        )
