"""Tool schemas — same call pattern; buyer-side wording.

Property order on propose_price is load-bearing: reasoning must be
generated before the number so the model commits to a read first.
"""

propose_price_tool = {
    "name": "propose_price",
    "description": (
        "Propose the unit price we are willing to pay. Must be called before stating any rupee figure. "
        "Fill reasoning first (internal only — never shown to the vendor), then interpreted_intent, "
        "then tactic, then price."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "reasoning": {
                "type": "string",
                "description": (
                    "Internal read of what the vendor meant and why this number. "
                    "Never shown to the vendor."
                ),
            },
            "interpreted_intent": {
                "type": "string",
                "description": "Intent from the interpretation step, e.g. objection_leadtime, counter_offer.",
            },
            "tactic": {
                "type": "string",
                "description": (
                    "e.g. competitive_bid, volume_commitment, payment_terms_trade, lead_time_trade, "
                    "package_trade, warranty_trade, anchoring_hold, calibrated_question"
                ),
            },
            "price": {"type": "integer"},
        },
        "required": ["reasoning", "interpreted_intent", "tactic", "price"],
    },
}

escalate_to_human_tool = {
    "name": "escalate_to_human",
    "description": (
        "Unused during live negotiation. The deal engine decides accept vs continue vs handoff; "
        "do not call this because a vendor number feels high or you think you are at a limit."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "reason": {"type": "string"}
        },
        "required": ["reason"],
    },
}

TOOLS = [propose_price_tool, escalate_to_human_tool]


def openai_tools() -> list[dict]:
    converted = []
    for tool in TOOLS:
        converted.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["input_schema"],
                },
            }
        )
    return converted
