from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.orchestrator.nodes import (
    TurnState,
    after_eligibility,
    after_interpret,
    after_negotiate,
    after_open,
    after_qualify,
    agreement_node,
    eligibility_node,
    greet_node,
    handoff_node,
    interpret_node,
    negotiate_node,
    open_offer_node,
    qualify_node,
)


async def closed_node(state: TurnState) -> dict:
    return {
        "assistant_message": (
            "This conversation is already closed — a sourcing colleague has the file and will follow up. "
            "If you need someone sooner, say so and I'll flag it."
        )
    }


def dispatch(state: TurnState) -> str:
    stage = state["session"]["stage"]
    return {
        "greet_and_disclose": "greet",
        "qualify": "interpret",
        "price_eligibility_check": "eligibility",
        "open_offer": "open_offer",
        "negotiate": "interpret",
        "agreement": "agreement",
        "handoff": "handoff",
        "closed": "closed",
    }.get(stage, "interpret")


def build_graph():
    workflow = StateGraph(TurnState)
    workflow.add_node("greet", greet_node)
    workflow.add_node("interpret", interpret_node)
    workflow.add_node("qualify", qualify_node)
    workflow.add_node("eligibility", eligibility_node)
    workflow.add_node("open_offer", open_offer_node)
    workflow.add_node("negotiate", negotiate_node)
    workflow.add_node("agreement", agreement_node)
    workflow.add_node("handoff", handoff_node)
    workflow.add_node("closed", closed_node)

    workflow.add_conditional_edges(
        START,
        dispatch,
        {
            "greet": "greet",
            "interpret": "interpret",
            "eligibility": "eligibility",
            "open_offer": "open_offer",
            "agreement": "agreement",
            "handoff": "handoff",
            "closed": "closed",
        },
    )
    workflow.add_edge("greet", END)
    workflow.add_conditional_edges(
        "interpret",
        after_interpret,
        {"qualify": "qualify", "negotiate": "negotiate", "end": END},
    )
    workflow.add_conditional_edges(
        "qualify",
        after_qualify,
        {"eligibility": "eligibility", "end": END},
    )
    workflow.add_conditional_edges(
        "eligibility",
        after_eligibility,
        {"handoff": "handoff", "open_offer": "open_offer"},
    )
    workflow.add_conditional_edges(
        "open_offer",
        after_open,
        {"handoff": "handoff", "agreement": "agreement", "end": END},
    )
    workflow.add_conditional_edges(
        "negotiate",
        after_negotiate,
        {"handoff": "handoff", "agreement": "agreement", "end": END},
    )
    workflow.add_edge("agreement", END)
    workflow.add_edge("handoff", END)
    workflow.add_edge("closed", END)
    return workflow.compile()
