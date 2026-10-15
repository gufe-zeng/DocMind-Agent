"""M3a StateGraph with explicit conditional edges and bounded tool loops.

No Memory/checkpointer yet: M4 implements session, long-term and durable
graph checkpoints. This graph is per-request and does not remember history.
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


def build_agent_graph():
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
    return flow.compile()


agent_graph = build_agent_graph()
