"""Tactic choice from interpretation — not from graph stage."""

from __future__ import annotations

from app.deal_engine import HOLD_PRICE_TACTICS, best_alternate_unit_price
from app.models import Interpretation, NegotiationSession, PartListing
from app.playbook.situations import adapt_tactic, classify_situation

__all__ = ["HOLD_PRICE_TACTICS", "select_tactic"]


def _base_tactic(
    interpretation: Interpretation,
    session: NegotiationSession,
    listing: PartListing,
) -> str:
    intent = interpretation.intent
    facts = interpretation.extracted_facts or {}
    confidence = interpretation.signal_confidence

    if intent == "objection_leadtime":
        return "lead_time_trade"
    if intent == "objection_quality":
        return "warranty_trade"
    if intent == "stalling":
        return "calibrated_question"
    if intent == "clarifying_question":
        return "clarify_hold"
    if intent == "small_talk":
        return "redirect"
    if intent == "acceptance":
        return "close"
    if intent == "rejection":
        return "value_trade"
    if intent == "objection_price":
        if confidence == "low":
            return "anchoring_hold"
        if best_alternate_unit_price(listing) is not None:
            return "competitive_bid"
        return "payment_terms_trade"
    if intent == "counter_offer":
        extras = any(
            facts.get(key)
            for key in ("payment_terms_requested", "moq_requested", "lead_time_requested")
        )
        if extras:
            return "package_trade"
        if confidence == "low" and session.round_count == 0:
            return "anchoring_hold"
        if best_alternate_unit_price(listing) is not None:
            return "competitive_bid"
        return "volume_commitment"
    return "volume_commitment"


def select_tactic(
    interpretation: Interpretation,
    session: NegotiationSession,
    listing: PartListing,
) -> str:
    base = _base_tactic(interpretation, session, listing)
    situation = classify_situation(interpretation, session, listing)
    return adapt_tactic(base, interpretation, session, listing, situation)
