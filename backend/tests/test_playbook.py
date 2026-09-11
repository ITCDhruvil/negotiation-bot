from datetime import datetime, timezone

from app.models import ConcessionEvent, InsightTurn, NegotiationStage
from app.orchestrator.interpret import interpret_message
from app.orchestrator.tactics import select_tactic
from app.playbook.memory import format_lessons, record_lesson, retrieve_lessons
from app.playbook.situations import classify_situation, is_stuck

from tests.test_deal_engine import make_listing, make_session


def _event(**overrides) -> ConcessionEvent:
    data = dict(
        round_number=1,
        vendor_offer=18_000,
        bot_offer=14_904,
        justification_tactic="anchoring_hold",
        timestamp=datetime.now(timezone.utc),
    )
    data.update(overrides)
    return ConcessionEvent(**data)


def test_ceiling_probe_holds_and_does_not_name_a_number():
    listing = make_listing()
    session = make_session()
    interp = interpret_message("What's your maximum on this line?", session, listing)
    assert interp.extracted_facts["ceiling_probe"] is True
    assert classify_situation(interp, session, listing) == "ceiling_probe"
    assert select_tactic(interp, session, listing) == "clarify_hold"


def test_walkaway_share_is_a_ceiling_probe():
    listing = make_listing()
    session = make_session(round_count=1)
    interp = interpret_message(
        "If you share the walk-away we can both skip the back-and-forth — what number can you actually not exceed?",
        session,
        listing,
    )
    assert interp.extracted_facts["ceiling_probe"] is True
    assert select_tactic(interp, session, listing) == "clarify_hold"


def test_lead_time_still_trades_calendar_not_price():
    listing = make_listing()
    session = make_session()
    interp = interpret_message("Lead time is the problem — we need 45 days", session, listing)
    assert select_tactic(interp, session, listing) == "lead_time_trade"


def test_price_objection_with_alternate_still_uses_competitive_bid():
    listing = make_listing()
    session = make_session(round_count=1)
    interp = interpret_message("That price is too low, we can't meet that number", session, listing)
    assert select_tactic(interp, session, listing) == "competitive_bid"


def test_repeated_hold_escalates_instead_of_repeating():
    listing = make_listing()
    session = make_session(
        round_count=2,
        concession_history=[
            _event(round_number=1, justification_tactic="anchoring_hold", vendor_offer=18_500),
            _event(round_number=2, justification_tactic="anchoring_hold", vendor_offer=18_500),
        ],
    )
    assert is_stuck(session)
    interp = interpret_message("Still ₹18,500 — that's our number.", session, listing)
    tactic = select_tactic(interp, session, listing)
    assert tactic != "anchoring_hold"
    assert tactic in {"competitive_bid", "value_trade", "package_trade", "volume_commitment"}


def test_does_not_cite_competitive_bid_twice():
    listing = make_listing()
    session = make_session(
        round_count=2,
        concession_history=[
            _event(round_number=1, justification_tactic="competitive_bid", vendor_offer=18_000),
        ],
    )
    interp = interpret_message("₹18,000 is as low as we go.", session, listing)
    assert select_tactic(interp, session, listing) != "competitive_bid"


def test_firm_floor_stops_holding_the_anchor():
    listing = make_listing()
    session = make_session(
        round_count=1,
        vendor_justified_floor=True,
        concession_history=[
            _event(round_number=1, justification_tactic="anchoring_hold", vendor_offer=17_500),
        ],
    )
    interp = interpret_message(
        "We cannot go below ₹17,500 per unit due to the resin index.",
        session,
        listing,
    )
    assert classify_situation(interp, session, listing) == "firm_floor"
    assert select_tactic(interp, session, listing) != "anchoring_hold"


def test_lesson_memory_recalls_same_situation_without_walkaway(tmp_path):
    listing = make_listing()
    session = make_session(
        stage=NegotiationStage.CLOSED,
        current_bot_offer=16_800,
        round_count=3,
        insight_log=[
            InsightTurn(
                round_number=2,
                intent="counter_offer",
                sentiment="cooperative",
                signal_confidence="high",
                tactic="package_trade",
                situation="cooperative_move",
                timestamp=datetime.now(timezone.utc),
            )
        ],
        concession_history=[
            _event(justification_tactic="anchoring_hold"),
            _event(round_number=2, justification_tactic="package_trade", bot_offer=16_800, vendor_offer=16_800),
        ],
    )
    path = tmp_path / "lessons.json"
    row = record_lesson(session, listing, path=path)
    assert row is not None
    blob = path.read_text(encoding="utf-8")
    assert "17800" not in blob
    assert "16200" not in blob
    assert "max_acceptable" not in blob
    assert "walk" not in blob.lower()

    found = retrieve_lessons("headlight-lh", "cooperative_move", path=path)
    assert found
    text = format_lessons(found)
    assert "Headlight" in text
    assert "16,800" in text or "16800" in text
