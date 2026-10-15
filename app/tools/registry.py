"""M3a: bounded, validated tool registry.

This is structured application-side Tool Calling: a named tool is selected
from a whitelist, its argument model is validated, and a real service
function is invoked. M3b adds model-assisted decision making.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SearchDocumentsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=2000)
    document_id: str | None = None


class DocumentMetadataArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: str | None = None
    limit: int = Field(default=10, ge=1, le=20)


ToolHandler = Callable[[BaseModel], Awaitable[dict[str, Any]]]


async def invoke_tool(name: str, *, arguments: dict[str, Any]) -> dict[str, Any]:
    """Resolve an allowlisted tool and validate its typed arguments."""
    from app.tools.metadata import query_document_metadata
    from app.tools.retrieval import search_documents

    tools: dict[str, tuple[type[BaseModel], ToolHandler]] = {
        "search_documents": (SearchDocumentsArgs, search_documents),
        "query_document_metadata": (DocumentMetadataArgs, query_document_metadata),
    }
    target = tools.get(name)
    if target is None:
        raise ValueError(f"Tool not registered in M3a: {name}")
    arg_schema, handler = target
    parsed = arg_schema.model_validate(arguments)
    return await handler(parsed)


def available_tools() -> tuple[str, ...]:
    return ("search_documents", "query_document_metadata")
