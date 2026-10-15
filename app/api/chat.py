"""M3a POST /v1/chat: invoke a bounded LangGraph with real service tools.

M3a does not provide conversation/session memory; session_id is a correlation
value only. M4 will add persisted sessions and checkpoints.
"""

import logging
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agent.graph import agent_graph
from app.agent.state import AgentState

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["agent"])


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    document_id: UUID | None = None
    session_id: UUID | None = None


class ChatResponse(BaseModel):
    request_id: UUID
    session_id: UUID
    status: str
    intent: str
    answer: str
    tools_called: list[str]
    plan_source: str
    planner_fallback_reason: str | None = None
    steps: int
    entities: list[dict]
    sources: list[dict]


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    session_id = request.session_id or uuid4()
    request_id = uuid4()
    initial_state: AgentState = {
        "session_id": str(session_id),
        "query": request.query,
        "document_id": str(request.document_id) if request.document_id else None,
        "current_step": 0,
        "tool_results": [],
    }
    try:
        result: AgentState = await agent_graph.ainvoke(
            initial_state,
            config={"recursion_limit": 30},
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Agent execution failed: request_id=%s", request_id)
        raise HTTPException(
            status_code=503,
            detail="Agent tool or model service unavailable. Inspect API logs.",
        ) from exc

    return ChatResponse(
        request_id=request_id,
        session_id=session_id,
        status=result.get("status", "answered"),
        intent=result.get("intent", "unknown"),
        answer=result.get("final_answer", ""),
        tools_called=result.get("tools_called", []),
        plan_source=result.get("plan_source", "rules"),
        planner_fallback_reason=result.get("planner_fallback_reason"),
        entities=result.get("entities", []),
        steps=result.get("current_step", 0),
        sources=result.get("sources", []),
    )
