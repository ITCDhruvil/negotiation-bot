from app.deal_engine import authorized_price_for_tactic, validate_trade
from app.llm.persona_prompt import PERSONA_PROMPT
from app.llm.tools import propose_price_tool
from app.models import to_public_listing
from app.orchestrator.interpret import extract_facts, interpret_message
from app.orchestrator.tactics import select_tactic

from tests.test_deal_engine import make_listing, make_session


def test_extracts_price_terms_and_moq_from_multipart_message():
    facts = extract_facts("₹17,800 works but only at Net 60 and MOQ 50")
    assert facts["counter_price"] == 17_800
    assert facts["payment_terms_requested"] == "Net 60"
    assert facts["moq_requested"] == 50
    assert facts["lead_time_requested"] is None


def test_lead_time_objection_extracts_requested_days_not_the_rfq_window():
    facts = extract_facts("We can't hit 21 days — we need 45")
    assert facts["lead_time_requested"] == 45
    assert facts["counter_price"] is None


def test_interpret_classifies_lead_time_objection():
    session = make_session()
    interp = interpret_message("We can't hit 21 days — we need 45", session)
    assert interp.intent == "objection_leadtime"
    assert interp.extracted_facts["lead_time_requested"] == 45


def test_interpret_classifies_multipart_as_counter_offer():
    session = make_session()
    interp = interpret_message("₹17,800 works but only at Net 60 and MOQ 50", session)
    assert interp.intent == "counter_offer"
    assert interp.extracted_facts["payment_terms_requested"] == "Net 60"
    assert interp.extracted_facts["moq_requested"] == 50


def test_rejecting_arias_bid_is_not_a_counter_at_that_number():
    session = make_session(current_bot_offer=14_904)
    interp = interpret_message(
        "Unfortunately, ₹14,904 isn't feasible. However, we can extend payment terms to Net 45 "
        "while maintaining the current unit price.",
        session,
    )
    assert interp.extracted_facts["counter_price"] is None
    assert interp.intent in {"rejection", "objection_price"}


def test_below_what_we_can_accept_is_not_an_offer_at_arias_bid():
    session = make_session(current_bot_offer=14_904)
    interp = interpret_message(
        "While ₹14,904 is below what we can accept due to production costs, I'm open to negotiating.",
        session,
    )
    assert interp.extracted_facts["counter_price"] is None
    assert interp.intent in {"rejection", "objection_price"}


def test_vendor_restates_bid_then_gives_their_number():
    session = make_session(current_bot_offer=15_544)
    interp = interpret_message(
        "Can't align to ₹15,544. Could we reconsider at ₹17,500 if we package it with Net 60 and MOQ 50?",
        session,
    )
    assert interp.extracted_facts["counter_price"] == 17_500
    assert interp.intent == "counter_offer"
    assert interp.extracted_facts["payment_terms_requested"] == "Net 60"
    assert interp.extracted_facts["moq_requested"] == 50


def test_first_counter_is_low_confidence_opening():
    session = make_session(round_count=0, concession_history=[])
    interp = interpret_message("Starting at ₹18,000", session)
    assert interp.signal_confidence == "low"


def test_disclosed_cost_floor_is_high_confidence():
    session = make_session(round_count=0, concession_history=[])
    interp = interpret_message(
        "We cannot go below ₹17,500 per unit due to the resin index.",
        session,
    )
    assert session.vendor_justified_floor is True
    assert interp.signal_confidence == "high"
    assert interp.extracted_facts["counter_price"] == 17_500


def test_repeated_number_is_high_confidence():
    from datetime import datetime, timezone

    from app.models import ConcessionEvent

    session = make_session(
        concession_history=[
            ConcessionEvent(
                round_number=1,
                vendor_offer=18_000,
                bot_offer=15_544,
                justification_tactic="competitive_bid",
                timestamp=datetime.now(timezone.utc),
            )
        ]
    )
    interp = interpret_message("Still ₹18,000", session)
    assert interp.extracted_facts["counter_price"] == 18_000
    assert interp.signal_confidence == "high"


def test_lead_time_intent_selects_lead_time_trade_not_a_price_cut():
    listing = make_listing()
    session = make_session()
    interp = interpret_message("Lead time is the problem — we need 45 days", session, listing)
    tactic = select_tactic(interp, session, listing)
    assert tactic == "lead_time_trade"
    assert interp.intent == "objection_leadtime"
    held = authorized_price_for_tactic(session, listing, tactic)
    assert held == session.current_bot_offer


def test_price_objection_with_alternate_uses_competitive_bid():
    listing = make_listing()
    session = make_session(round_count=1)
    interp = interpret_message("That price is too low, we can't meet that number", session, listing)
    assert interp.intent == "objection_price"
    assert select_tactic(interp, session, listing) == "competitive_bid"


def test_propose_price_schema_requires_reasoning_before_the_number():
    props = list(propose_price_tool["input_schema"]["properties"].keys())
    assert props == ["reasoning", "interpreted_intent", "tactic", "price"]
    required = propose_price_tool["input_schema"]["required"]
    assert required == ["reasoning", "interpreted_intent", "tactic", "price"]


def test_persona_keeps_ai_disclosure_line():
    assert "You are not a human, and you say so once, plainly, near the start of the conversation." in PERSONA_PROMPT


def test_public_listing_never_includes_trade_envelopes():
    listing = make_listing(
        max_acceptable_lead_time_days=35,
        max_acceptable_moq=50,
        preferred_payment_terms="Net 60",
        fastest_payment_terms="Net 30",
    )
    public = to_public_listing(listing).model_dump()
    for key in (
        "max_acceptable_unit_price",
        "target_unit_price",
        "max_acceptable_lead_time_days",
        "max_acceptable_moq",
        "preferred_payment_terms",
        "fastest_payment_terms",
        "min_warranty_months",
        "target_lead_time_days",
        "alternate_vendor_quotes",
    ):
        assert key not in public


def test_validate_trade_rejects_moq_and_lead_time_outside_envelope():
    listing = make_listing(max_acceptable_moq=50, max_acceptable_lead_time_days=35)
    ok, reason = validate_trade(listing, moq=80)
    assert ok is False
    assert reason == "moq_above_max"
    ok, reason = validate_trade(listing, lead_time_days=45)
    assert ok is False
    assert reason == "lead_time_above_max"
    ok, reason = validate_trade(listing, payment_terms="Net 15")
    assert ok is False
    assert reason == "payment_terms_too_fast"
    ok, reason = validate_trade(listing, moq=50, lead_time_days=28, payment_terms="Net 60")
    assert ok is True
    assert reason is None
