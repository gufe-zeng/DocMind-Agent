"""M5b official MCP Client adapter for the local Document MCP stdio server.

A separate Python process speaks MCP JSON-RPC. Only the four frozen
read-only tools are allowed. Invalid MCP tool responses are never converted
into successful Agent answers. This module makes no HTTP REST shortcuts.
"""

import json
import os
import sys
from datetime import timedelta
from typing import Any

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


DOCUMENT_MCP_TOOLS = frozenset({
    "search_documents",
    "get_document",
    "get_document_page",
    "find_clause",
})


class DocumentMCPError(RuntimeError):
    """An MCP protocol/tool call failed or returned an unusable payload."""


def _extract_response(response: Any, name: str) -> dict[str, Any]:
    if response.isError:
        raise DocumentMCPError(f"MCP tool {name} returned an error.")

    payload = getattr(response, "structuredContent", None)
    if payload is None:
        blocks = getattr(response, "content", []) or []
        if not blocks or not isinstance(getattr(blocks[0], "text", None), str):
            raise DocumentMCPError(f"MCP tool {name} returned no structured data.")
        try:
            payload = json.loads(blocks[0].text)
        except (ValueError, TypeError) as exc:
            raise DocumentMCPError(f"MCP tool {name} returned invalid JSON.") from exc

    # FastMCP may wrap a dictionary result as {"result": {...}}.
    if isinstance(payload, dict) and set(payload) == {"result"}:
        payload = payload["result"]
    if not isinstance(payload, dict):
        raise DocumentMCPError(f"MCP tool {name} returned unexpected data type.")
    return payload


async def call_document_mcp(
    name: str,
    *,
    arguments: dict[str, Any],
    timeout_seconds: float = 90.0,
) -> dict[str, Any]:
    """Spawn the isolated stdio server and invoke one verified MCP tool.

    Includes the actual initialize/tools-list/tools-call handshake. The
    per-call deadline does not silently retry non-idempotent operations.
    """
    if name not in DOCUMENT_MCP_TOOLS:
        raise ValueError(f"Unregistered Document MCP tool: {name}")
    if not 1 <= timeout_seconds <= 180:
        raise ValueError("MCP deadline must be between 1 and 180 seconds.")

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.server"],
        env=dict(os.environ),
    )
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(
            reader,
            writer,
            read_timeout_seconds=timedelta(seconds=timeout_seconds),
        ) as session:
            with anyio.fail_after(min(timeout_seconds, 30.0)):
                await session.initialize()
                discovered = await session.list_tools()
            discovered_names = {item.name for item in discovered.tools}
            if name not in discovered_names:
                raise DocumentMCPError(f"Required MCP tool unavailable: {name}")
            with anyio.fail_after(timeout_seconds):
                result = await session.call_tool(name, arguments=arguments)
            return _extract_response(result, name)
