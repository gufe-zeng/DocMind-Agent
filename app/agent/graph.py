"""Compiled LangGraph graph with an optional durable checkpointer.

M4a binds PostgreSQL AsyncPostgresSaver in the FastAPI lifespan.
Tests may compile a transient graph without persistence.
"""

from langgraph.graph import END, START, StateGraph

from app.agent.nodes import (
    call_tool_node,
    decide_node,
    next_edge,
    route_node,
    synthesize_node,
)
from app.agent.state import AgentState


def build_agent_graph(checkpointer=None):
    flow = StateGraph(AgentState)
    flow.add_node("route", route_node)
    flow.add_node("decide", decide_node)
    flow.add_node("call_tool", call_tool_node)
    flow.add_node("synthesize", synthesize_node)

    flow.add_edge(START, "route")
    flow.add_edge("route", "decide")
    flow.add_conditional_edges(
        "decide",
        next_edge,
        {"call_tool": "call_tool", "synthesize": "synthesize"},
    )
    flow.add_edge("call_tool", "decide")
    flow.add_edge("synthesize", END)
    return flow.compile(checkpointer=checkpointer)


agent_graph = build_agent_graph()
