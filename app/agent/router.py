"""M3a: auditable rule-based tool selection, not LLM planning."""

METADATA_INTENTS = (
    "列出文档", "有哪些文档", "文档列表", "文件列表", "文档元数据",
    "文件信息", "已上传", "已经上传", "已索引", "有哪些文件",
    "列出文件", "文档信息",
)
CONTENT_INTENTS = (
    "付款", "违约", "条款", "期限", "主体", "责任", "问答",
    "告诉", "根据合同", "回答", "合同内容", "合同约定",
)


def select_tool_plan(query: str) -> list[str]:
    """Pick concrete business tools with a strict, bounded two-step plan."""
    if not query.strip():
        raise ValueError("Query cannot be empty.")
    metadata = any(term in query for term in METADATA_INTENTS)
    content = any(term in query for term in CONTENT_INTENTS)

    if metadata and content:
        return ["query_document_metadata", "search_documents"]
    if metadata:
        return ["query_document_metadata"]
    return ["search_documents"]
