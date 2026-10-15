"""M3b: a typed allowlisted registry of real document business tools.

The planning model never has direct access to arbitrary Python functions.
Every call is validated through a dedicated Pydantic argument schema.
M6 introduces the separate approval-protected write tool.
"""

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SearchDocumentsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    query: str = Field(min_length=1, max_length=2000)
    document_id: str | None = None
    format_hint: str | None = Field(default=None, max_length=30)


class DocumentMetadataArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: str | None = None
    limit: int = Field(default=10, ge=1, le=20)


class ExtractEntitiesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    query: str = Field(min_length=1, max_length=2000)
    document_id: UUID


class SummarizeDocumentArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    query: str = Field(min_length=1, max_length=2000)
    document_id: UUID
    format_hint: str | None = Field(default=None, max_length=30)


ToolHandler = Callable[[BaseModel], Awaitable[dict[str, Any]]]


async def invoke_tool(name: str, *, arguments: dict[str, Any]) -> dict[str, Any]:
    from app.tools.extraction import extract_entities
    from app.tools.metadata import query_document_metadata
    from app.tools.retrieval import search_documents
    from app.tools.summary import summarize_document

    tools: dict[str, tuple[type[BaseModel], ToolHandler]] = {
        "search_documents": (SearchDocumentsArgs, search_documents),
        "query_document_metadata": (DocumentMetadataArgs, query_document_metadata),
        "extract_entities": (ExtractEntitiesArgs, extract_entities),
        "summarize_document": (SummarizeDocumentArgs, summarize_document),
    }
    selected = tools.get(name)
    if selected is None:
        raise ValueError(f"Tool not registered in M3b: {name}")
    arg_schema, handler = selected
    validated = arg_schema.model_validate(arguments)
    return await handler(validated)


def available_tools() -> tuple[str, ...]:
    return (
        "search_documents",
        "query_document_metadata",
        "extract_entities",
        "summarize_document",
    )
