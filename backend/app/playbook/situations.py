"""Name the desk situation, then pick a tactic that has not already failed."""

from __future__ import annotations

from app.deal_engine import HOLD_PRICE_TACTICS, best_alternate_unit_price, near_target_price
from app.models import Interpretation, NegotiationSession, PartListing

_PACKAGE_KEYS = ("payment_terms_requested", "moq_requested", "lead_time_requested")

PLAYBOOK: dict[str, dict[str, object]] = {
    "ceiling_probe": {
        "label": "Ceiling probe",
        "coaching": (
            "They are fishing for a max, ceiling, or walk-away. Do not name one. Do not invent a limit.",
            "Hold the current bid. Ask what number they can actually do, or what constraint is real.",
        ),
    },
    "firm_floor": {
        "label": "Vendor floor named",
        "coaching": (
            "They named a cost or floor. Use their words. Do not repeat the same bid.",
            "Make one visible move or a terms trade, and ask what they give back.",
        ),
    },
    "stalling": {
        "label": "Stall / check with manager",
        "coaching": (
            "Do not cut price while they check. Ask one concrete question that forces a number or a date.",
            "If they stall a second time, put a package on the table instead of another question.",
        ),
    },
    "leadtime_gate": {
        "label": "Lead-time objection",
        "coaching": (
            "The constraint is the calendar, not the rupee figure. Trade lead time. Hold unit price.",
        ),
    },
    "quality_gate": {
        "label": "Quality / warranty objection",
        "coaching": (
            "Trade warranty or PPAP. Do not grind unit price because they mentioned quality.",
        ),
    },
    "package_ask": {
        "label": "Package counter",
        "coaching": (
            "Answer every constraint they named — terms, MOQ, lead time — not only the rupee figure.",
            "Tie the authorized bid to that package. One ask: does this close it?",
        ),
    },
    "stuck_repeat": {
        "label": "Same move, no movement",
        "coaching": (
            "The last tactic did not move them. Do not repeat it.",
            "Change the lever: terms, volume, competitive quote (only if a real alternate is in ENGINE), or a fresh question.",
        ),
    },
    "in_range_push": {
        "label": "Payable, one push left",
        "coaching": (
            "Their number is in play. Push once with a trade, then be ready to close. Do not grind.",
        ),
    },
    "cooperative_move": {
        "label": "Cooperative counter",
        "coaching": (
            "They moved. Name the move in their words, then counter with the authorized bid.",
            "Ask what would close it. Do not ignore the concession.",
        ),
    },
    "ready_to_close": {
        "label": "Ready to close",
        "coaching": (
            "The engine accepted. Confirm the line. Do not reopen price.",
        ),
    },
    "opening": {
        "label": "Opening position",
        "coaching": (
            "Treat their first number as an opening, not a floor. Hold the anchor. Ask what would land it.",
        ),
    },
    "price_fight": {
        "label": "Price negotiation",
        "coaching": (
            "One new move. Reciprocity on every rupee. Close the moment they land in range.",
        ),
    },
}


def _has_package(facts: dict) -> bool:
    return any(facts.get(key) for key in _PACKAGE_KEYS)


def _used_tactics(session: NegotiationSession) -> set[str]:
    return {event.justification_tactic for event in session.concession_history if event.justification_tactic}


def _intent_count(session: NegotiationSession, intent: str) -> int:
    return sum(1 for item in session.insight_log if item.intent == intent)


def is_stuck(session: NegotiationSession) -> bool:
    history = session.concession_history
    if len(history) < 2:
        return False
    prior, last = history[-2], history[-1]
    if prior.justification_tactic != last.justification_tactic:
        return False
    if prior.justification_tactic in HOLD_PRICE_TACTICS:
        return True
    return bool(prior.vendor_offer and prior.vendor_offer == last.vendor_offer)


def classify_situation(
    interpretation: Interpretation,
    session: NegotiationSession,
    listing: PartListing | None = None,
) -> str:
    facts = interpretation.extracted_facts or {}
    intent = interpretation.intent
    counter = facts.get("counter_price")
    extras = _has_package(facts)

    if facts.get("ceiling_probe") and counter is None:
        return "ceiling_probe"
    if intent == "acceptance":
        return "ready_to_close"
    if intent == "objection_leadtime":
        return "leadtime_gate"
    if intent == "objection_quality":
        return "quality_gate"
    if intent == "stalling":
        return "stalling"
    if extras and (intent == "counter_offer" or counter is not None):
        return "package_ask"
    if session.vendor_justified_floor or (
        interpretation.signal_confidence == "high" and session.round_count >= 1 and counter is not None
    ):
        return "firm_floor"
    if is_stuck(session):
        return "stuck_repeat"
    if (
        listing is not None
        and isinstance(counter, int)
        and counter <= listing.max_acceptable_unit_price
        and not near_target_price(counter, listing)
        and not session.in_range_push_done
        and session.round_count < max(0, session.max_rounds - 1)
    ):
        return "in_range_push"
    if interpretation.sentiment == "cooperative" and counter is not None:
        return "cooperative_move"
    if session.round_count == 0 and intent in {"counter_offer", "objection_price"}:
        return "opening"
    return "price_fight"


def escalate_tactic(
    session: NegotiationSession,
    listing: PartListing,
    interpretation: Interpretation,
) -> str:
    used = _used_tactics(session)
    facts = interpretation.extracted_facts or {}
    if _has_package(facts):
        return "package_trade"
    if "competitive_bid" not in used and best_alternate_unit_price(listing) is not None:
        return "competitive_bid"
    if "value_trade" not in used:
        return "value_trade"
    if "payment_terms_trade" not in used:
        return "payment_terms_trade"
    return "volume_commitment"


def adapt_tactic(
    base: str,
    interpretation: Interpretation,
    session: NegotiationSession,
    listing: PartListing,
    situation: str | None = None,
) -> str:
    situation = situation or classify_situation(interpretation, session, listing)
    facts = interpretation.extracted_facts or {}
    used = _used_tactics(session)

    if situation == "ceiling_probe" and facts.get("counter_price") is None:
        return "clarify_hold"
    if situation == "leadtime_gate":
        return "lead_time_trade"
    if situation == "quality_gate":
        return "warranty_trade"
    if situation == "ready_to_close":
        return "close"
    if situation == "stalling" and _intent_count(session, "stalling") >= 1:
        return escalate_tactic(session, listing, interpretation)
    if situation in {"firm_floor", "stuck_repeat"} and (
        base in HOLD_PRICE_TACTICS or is_stuck(session)
    ):
        return escalate_tactic(session, listing, interpretation)
    if base == "competitive_bid" and "competitive_bid" in used:
        return escalate_tactic(session, listing, interpretation)
    if (
        facts.get("moq_requested") is not None
        and facts.get("counter_price") is None
        and interpretation.intent not in {"objection_leadtime", "objection_quality"}
    ):
        return "moq_trade"
    return base


def render_playbook_block(
    *,
    situation: str,
    tactic: str,
    lessons: str = "",
) -> str:
    card = PLAYBOOK.get(situation) or PLAYBOOK["price_fight"]
    label = card["label"]
    lines = "\n".join(f"- {line}" for line in card["coaching"])
    block = (
        "\n[SITUATION]\n"
        f"name={situation}\n"
        f"label={label}\n"
        f"selected_tactic={tactic}\n"
        "[/SITUATION]\n"
        "[PLAYBOOK]\n"
        f"{lines}\n"
        "Follow this playbook this turn. Do not repeat the previous sentence.\n"
        "[/PLAYBOOK]\n"
    )
    if lessons:
        block += (
            "[LESSONS FROM PRIOR DESKS]\n"
            f"{lessons}\n"
            "Use the tactic pattern. Never invent a walk-away or authorization limit.\n"
            "[/LESSONS]\n"
        )
    return block
