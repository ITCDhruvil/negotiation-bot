from datetime import datetime, timezone

import pytest

from app.catalog import get_part
from app.deal_engine import compute_anchor
from app.formatting import format_inr
from app.llm.provider import MockProvider
from app.models import ConcessionEvent, NegotiationSession, NegotiationStage
from app.orchestrator.graph import build_graph
from app.orchestrator.nodes import PROVIDER, TOKEN_SINK
from app.orchestrator.qualify import apply_qualification, is_qualified


def _session(part_id: str, stage: NegotiationStage) -> NegotiationSession:
    now = datetime.now(timezone.utc)
    listing = get_part(part_id)
    assert listing is not None
    return NegotiationSession(
        session_id="test-session",
        vendor_rep_name=None,
        vendor_rep_contact=None,
        part_id=part_id,
        request_id=listing.request_id,
        stage=stage,
        anchor_price=0,
        current_bot_offer=0,
        current_vendor_offer=listing.vendor_quoted_unit_price,
        created_at=now,
        updated_at=now,
    )


def test_qualify_extracts_name_contact_and_terms():
    session = _session("headlight-lh", NegotiationStage.QUALIFY)
    session = apply_qualification(
        session, "I'm Riya Sharma, riya.sharma@example.com, Net 30"
    )
    assert session.vendor_rep_name == "Riya Sharma"
    assert session.vendor_rep_contact == "riya.sharma@example.com"
    assert session.payment_terms == "Net 30"
    assert is_qualified(session)


@pytest.mark.asyncio
async def test_over_ceiling_order_handoffs_after_desk_capture():
    listing = get_part("chassis-frame-front")
    assert listing is not None
    session = _session("chassis-frame-front", NegotiationStage.QUALIFY)
    graph = build_graph()
    p = PROVIDER.set(MockProvider())
    s = TOKEN_SINK.set(None)
    try:
        result = await graph.ainvoke(
            {
                "session": session.model_dump(mode="json"),
                "listing": listing.model_dump(mode="json"),
                "user_message": "I'm Priya, priya@example.com, Net 30",
                "assistant_message": "",
                "transcript": [],
            }
        )
    finally:
        PROVIDER.reset(p)
        TOKEN_SINK.reset(s)
    assert result["session"]["handoff_flag"] is True
    assert result["session"]["handoff_reason"] == "above_10L_ceiling"
    assert result["session"]["stage"] == "handoff"
    assert "10,00,000" in result["assistant_message"]


@pytest.mark.asyncio
async def test_under_ceiling_part_opens_low_validated_anchor():
    listing = get_part("headlight-lh")
    assert listing is not None
    session = _session("headlight-lh", NegotiationStage.QUALIFY)
    graph = build_graph()
    p = PROVIDER.set(MockProvider())
    s = TOKEN_SINK.set(None)
    try:
        result = await graph.ainvoke(
            {
                "session": session.model_dump(mode="json"),
                "listing": listing.model_dump(mode="json"),
                "user_message": "I'm Arjun, arjun@example.com, Net 45",
                "assistant_message": "",
                "transcript": [],
            }
        )
    finally:
        PROVIDER.reset(p)
        TOKEN_SINK.reset(s)
    expected = compute_anchor(listing)
    assert result["session"]["stage"] == "negotiate"
    assert result["validated_price"] == expected
    assert result["session"]["handoff_flag"] is False
    assert format_inr(listing.vendor_quoted_unit_price) in result["assistant_message"]
    assert format_inr(expected) in result["assistant_message"]
    assert expected < listing.vendor_quoted_unit_price


@pytest.mark.asyncio
async def test_contact_refusal_then_second_refusal_proceeds_to_pricing():
    listing = get_part("wiring-harness-cabin")
    assert listing is not None
    session = _session("wiring-harness-cabin", NegotiationStage.QUALIFY)
    graph = build_graph()
    p = PROVIDER.set(MockProvider())
    s = TOKEN_SINK.set(None)
    try:
        first = await graph.ainvoke(
            {
                "session": session.model_dump(mode="json"),
                "listing": listing.model_dump(mode="json"),
                "user_message": "i cannot give you that",
                "assistant_message": "",
                "transcript": [],
            }
        )
        assert first["session"]["stage"] == "qualify"
        assert first["session"]["contact_refusal_count"] == 1
        assert "name and company" in first["assistant_message"].lower()
        first_text = first["assistant_message"]

        second = await graph.ainvoke(
            {
                "session": first["session"],
                "listing": listing.model_dump(mode="json"),
                "user_message": "i cannot give you that",
                "assistant_message": "",
                "transcript": [],
            }
        )
    finally:
        PROVIDER.reset(p)
        TOKEN_SINK.reset(s)
    assert second["session"]["stage"] == "negotiate"
    assert second["session"]["contact_followup_required"] is True
    assert second["session"]["handoff_flag"] is False
    assert second["assistant_message"] != first_text
    assert second["validated_price"] == compute_anchor(listing)
    assert format_inr(compute_anchor(listing)) in second["assistant_message"]


@pytest.mark.asyncio
async def test_greet_keeps_ai_disclosure_line():
    listing = get_part("headlight-lh")
    assert listing is not None
    session = _session("headlight-lh", NegotiationStage.GREET_AND_DISCLOSE)
    graph = build_graph()
    p = PROVIDER.set(MockProvider())
    s = TOKEN_SINK.set(None)
    try:
        result = await graph.ainvoke(
            {
                "session": session.model_dump(mode="json"),
                "listing": listing.model_dump(mode="json"),
                "user_message": "",
                "assistant_message": "",
                "transcript": [],
            }
        )
    finally:
        PROVIDER.reset(p)
        TOKEN_SINK.reset(s)
    assert "I'm Aria" in result["assistant_message"]
    assert "AI" in result["assistant_message"]
    assert "sourcing" in result["assistant_message"].lower()
    lowered = result["assistant_message"].lower()
    assert "commit on" not in lowered
    assert "lead time" not in lowered
    assert "payment terms" not in lowered


@pytest.mark.asyncio
async def test_lead_time_objection_holds_price_and_logs_reasoning():
    listing = get_part("headlight-lh")
    assert listing is not None
    session = _session("headlight-lh", NegotiationStage.NEGOTIATE)
    session.vendor_rep_name = "Arjun"
    session.vendor_rep_contact = "arjun@example.com"
    session.anchor_price = compute_anchor(listing)
    session.current_bot_offer = session.anchor_price
    graph = build_graph()
    p = PROVIDER.set(MockProvider())
    s = TOKEN_SINK.set(None)
    try:
        result = await graph.ainvoke(
            {
                "session": session.model_dump(mode="json"),
                "listing": listing.model_dump(mode="json"),
                "user_message": "We can't hit 21 days — we need 45",
                "assistant_message": "",
                "transcript": [],
            }
        )
    finally:
        PROVIDER.reset(p)
        TOKEN_SINK.reset(s)
    assert result["tactic"] == "lead_time_trade"
    assert result["session"]["current_bot_offer"] == compute_anchor(listing)
    assert result["interpreted_intent"] == "objection_leadtime"
    assert result.get("reasoning")
    assert result["reasoning"] not in result["assistant_message"]
    assert "lead" in result["assistant_message"].lower()
    events = result["session"]["concession_history"]
    assert events
    assert events[-1]["justification_tactic"] == "lead_time_trade"
    assert events[-1]["interpreted_intent"] == "objection_leadtime"
    assert events[-1]["reasoning"]
    insights = result["session"]["insight_log"]
    assert insights
    assert insights[-1]["intent"] == "objection_leadtime"


@pytest.mark.asyncio
async def test_bare_no_after_floor_does_not_handoff():
    listing = get_part("headlight-lh")
    assert listing is not None
    now = datetime.now(timezone.utc)
    session = _session("headlight-lh", NegotiationStage.NEGOTIATE)
    session.vendor_rep_name = "Mehta"
    session.vendor_rep_contact = "mehta@valeo.example"
    session.anchor_price = compute_anchor(listing)
    session.current_bot_offer = session.anchor_price
    session.current_vendor_offer = 18_000
    session.concession_history = [
        ConcessionEvent(
            round_number=1,
            vendor_offer=18_000,
            bot_offer=session.anchor_price,
            justification_tactic="anchoring_hold",
            timestamp=now,
        )
    ]
    session.round_count = 1
    graph = build_graph()
    p = PROVIDER.set(MockProvider())
    s = TOKEN_SINK.set(None)
    try:
        result = await graph.ainvoke(
            {
                "session": session.model_dump(mode="json"),
                "listing": listing.model_dump(mode="json"),
                "user_message": "no",
                "assistant_message": "",
                "transcript": [],
            }
        )
    finally:
        PROVIDER.reset(p)
        TOKEN_SINK.reset(s)
    assert result["session"]["stage"] == "negotiate"
    assert result["session"]["handoff_flag"] is False


@pytest.mark.asyncio
async def test_rejecting_bot_offer_does_not_close_the_deal():
    listing = get_part("headlight-lh")
    assert listing is not None
    session = _session("headlight-lh", NegotiationStage.NEGOTIATE)
    session.vendor_rep_name = "Kavya"
    session.vendor_rep_contact = "kavya@valeo.example"
    session.anchor_price = compute_anchor(listing)
    session.current_bot_offer = session.anchor_price
    graph = build_graph()
    p = PROVIDER.set(MockProvider())
    s = TOKEN_SINK.set(None)
    try:
        result = await graph.ainvoke(
            {
                "session": session.model_dump(mode="json"),
                "listing": listing.model_dump(mode="json"),
                "user_message": (
                    "Unfortunately, we can't go below our cost threshold on unit price; "
                    f"₹{session.current_bot_offer} isn't feasible. However, we can extend "
                    "payment terms to Net 45 while maintaining the current unit price."
                ),
                "assistant_message": "",
                "transcript": [],
            }
        )
    finally:
        PROVIDER.reset(p)
        TOKEN_SINK.reset(s)
    assert result["session"]["stage"] == "negotiate"
    assert result["session"]["handoff_flag"] is False
    assert result["session"]["stage"] != "agreement"


@pytest.mark.asyncio
async def test_vendor_offer_inside_ceiling_closes_even_above_bot_bid():
    listing = get_part("headlight-lh")
    assert listing is not None
    session = _session("headlight-lh", NegotiationStage.NEGOTIATE)
    session.vendor_rep_name = "Kavya"
    session.vendor_rep_contact = "kavya@valeo.example"
    session.anchor_price = compute_anchor(listing)
    session.current_bot_offer = session.anchor_price
    graph = build_graph()
    p = PROVIDER.set(MockProvider())
    s = TOKEN_SINK.set(None)
    try:
        result = await graph.ainvoke(
            {
                "session": session.model_dump(mode="json"),
                "listing": listing.model_dump(mode="json"),
                "user_message": (
                    "We cannot go below ₹17,500 per unit due to the resin index. "
                    "We can extend lead time to 28 days and payment terms to Net 45."
                ),
                "assistant_message": "",
                "transcript": [],
            }
        )
    finally:
        PROVIDER.reset(p)
        TOKEN_SINK.reset(s)
    assert result["session"]["stage"] == "closed"
    assert result["session"]["handoff_flag"] is False
    assert result["session"]["current_bot_offer"] == 17_500
    assert result["session"]["payment_terms"] == "Net 45"
    assert result["session"]["current_lead_time_days"] == 28
    assert "17,500" in result["assistant_message"] or "17500" in result["assistant_message"].replace(",", "")


@pytest.mark.asyncio
async def test_first_in_range_offer_above_target_gets_one_push():
    listing = get_part("headlight-lh")
    assert listing is not None
    session = _session("headlight-lh", NegotiationStage.NEGOTIATE)
    session.vendor_rep_name = "Rohan"
    session.vendor_rep_contact = "rohan@valeo.example"
    session.anchor_price = compute_anchor(listing)
    session.current_bot_offer = session.anchor_price
    graph = build_graph()
    p = PROVIDER.set(MockProvider())
    s = TOKEN_SINK.set(None)
    try:
        result = await graph.ainvoke(
            {
                "session": session.model_dump(mode="json"),
                "listing": listing.model_dump(mode="json"),
                "user_message": "₹17,800 works but only at Net 60 and MOQ 50",
                "assistant_message": "",
                "transcript": [],
            }
        )
    finally:
        PROVIDER.reset(p)
        TOKEN_SINK.reset(s)
    assert result["session"]["stage"] == "negotiate"
    assert result["session"]["handoff_flag"] is False
    assert result["session"]["in_range_push_done"] is True
    assert result["session"]["current_bot_offer"] != 17_800


@pytest.mark.asyncio
async def test_boundary_part_opens_then_qty_bump_handoffs_over_ceiling():
    listing = get_part("rear-subframe")
    assert listing is not None
    assert listing.vendor_quoted_unit_price * listing.quantity <= 1_000_000
    session = _session("rear-subframe", NegotiationStage.QUALIFY)
    graph = build_graph()
    p = PROVIDER.set(MockProvider())
    s = TOKEN_SINK.set(None)
    try:
        opened = await graph.ainvoke(
            {
                "session": session.model_dump(mode="json"),
                "listing": listing.model_dump(mode="json"),
                "user_message": "I'm Sneha, sneha@example.com, Net 30",
                "assistant_message": "",
                "transcript": [],
            }
        )
        assert opened["session"]["stage"] == "negotiate"
        assert opened["session"]["handoff_flag"] is False
        bumped = await graph.ainvoke(
            {
                "session": opened["session"],
                "listing": listing.model_dump(mode="json"),
                "user_message": "₹24,500 works but only at MOQ 42",
                "assistant_message": "",
                "transcript": [],
            }
        )
    finally:
        PROVIDER.reset(p)
        TOKEN_SINK.reset(s)
    assert bumped["session"]["handoff_flag"] is True
    assert bumped["session"]["handoff_reason"] == "above_10L_ceiling"
    assert bumped["session"]["stage"] == "handoff"
    assert bumped["session"]["stage"] != "agreement"


@pytest.mark.asyncio
async def test_hostile_language_handoffs_from_negotiate():
    listing = get_part("headlight-lh")
    assert listing is not None
    session = _session("headlight-lh", NegotiationStage.NEGOTIATE)
    session.vendor_rep_name = "Rajesh"
    session.vendor_rep_contact = "rajesh@example.com"
    session.anchor_price = compute_anchor(listing)
    session.current_bot_offer = session.anchor_price
    graph = build_graph()
    p = PROVIDER.set(MockProvider())
    s = TOKEN_SINK.set(None)
    try:
        result = await graph.ainvoke(
            {
                "session": session.model_dump(mode="json"),
                "listing": listing.model_dump(mode="json"),
                "user_message": "this is a scam you cheat",
                "assistant_message": "",
                "transcript": [],
            }
        )
    finally:
        PROVIDER.reset(p)
        TOKEN_SINK.reset(s)
    assert result["session"]["handoff_flag"] is True
    assert result["session"]["handoff_reason"] == "aggressive_language"
    assert result["session"]["stage"] == "handoff"
