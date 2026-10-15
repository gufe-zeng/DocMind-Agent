"""M4b: a real interrupted LangGraph resumed by a new PG connection.

Interruption occurs immediately before invoking a real read-only tool.
A separately compiled graph on a fresh AsyncPostgresSaver connection
continues from that state without re-planning the original request.
"""

import asyncio
from uuid import uuid4

from app.agent.graph import build_agent_graph
from app.api.chat import _initial_state
from app.core.config import get_settings
from app.memory.checkpoint import open_checkpointer, thread_config


async def main() -> None:
    settings = get_settings()
    sid = str(uuid4())
    cfg = thread_config(sid)
    print("CHECKPOINT_THREAD_ID=" + sid, flush=True)

    async with open_checkpointer(settings.postgres_dsn) as saver:
        graph = build_agent_graph(checkpointer=saver, interrupt_before=["call_tool"])
        await graph.ainvoke(
            _initial_state(
                sid, query="列出已上传的文档", document_id=None
            ),
            config=cfg,
        )
        state = await graph.aget_state(cfg)
        print("Before resume, next nodes:", state.next, flush=True)
        assert "call_tool" in state.next, state.next
        assert state.values["plan"] == ["query_document_metadata"]
        assert state.values["current_step"] == 0
        checkpoint_before = state.config["configurable"]["checkpoint_id"]
        print("PASS PostgreSQL saved pre-tool interruption", flush=True)

    # New PG connection + new compiled graph models process restart.
    async with open_checkpointer(settings.postgres_dsn) as saver:
        graph = build_agent_graph(checkpointer=saver)
        state = await graph.aget_state(cfg)
        assert "call_tool" in state.next, state.next
        resumed = await graph.ainvoke(None, config=cfg)
        assert resumed["tools_called"] == ["query_document_metadata"], resumed
        assert resumed["current_step"] == 1, resumed
        assert resumed["final_answer"], resumed
        end_state = await graph.aget_state(cfg)
        assert not end_state.next, end_state.next
        checkpoint_after = end_state.config["configurable"]["checkpoint_id"]
        assert checkpoint_after != checkpoint_before
        print(
            "PASS independent graph resumed only pending tool and completed",
            flush=True,
        )
        print("Resumed answer:", resumed["final_answer"], flush=True)

    print("M4b CHECKPOINT PASS", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
