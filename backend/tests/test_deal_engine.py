"""Guardrail math is verified in isolation — no LLM, no network.

Buyer-side: the bot pays. It opens low and must never agree above max_acceptable.
The ₹10L gate is on order total (unit × quantity), not unit price.
"""

from datetime import datetime, timezone
from pathlib import Path

from app.models import (
    AlternateQuote,
    ConcessionEvent,
    NegotiationSession,
    NegotiationStage,
    PartListing,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def make_listing(**overrides) -> PartListing:
    data = dict(
        part_id="headlight-lh",
        part_name="Headlight Assembly LH",
        category="Lighting",
        vendor_id="valeo-pune",
        vendor_name="Valeo Lighting India",
        vendor_quoted_unit_price=18_500,
        quantity=40,
        moq=20,
        target_unit_price=16_200,
        max_acceptable_unit_price=17_800,
        lead_time_days=21,
        payment_terms_default="Net 30",
        alternate_vendor_quotes=[
            AlternateQuote(vendor_id="hella-chennai", vendor_name="Hella India", unit_price=17_200),
        ],
        spec_blurb="OEM-equivalent LH headlight for the Pune line.",
        request_id="rfq-2026-041",
        request_title="Q3 lighting & chassis — Pune",
        plant="Pune",
    )
    data.update(overrides)
    return PartListing(**data)


def make_session(**overrides) -> NegotiationSession:
    data = dict(
        session_id="s1",
        vendor_rep_name="Mehta",
        vendor_rep_contact="mehta@vendor.example",
        part_id="headlight-lh",
        request_id="rfq-2026-041",
        stage=NegotiationStage.NEGOTIATE,
        anchor_price=14_904,
        current_bot_offer=14_904,
        current_vendor_offer=18_500,
        concession_history=[],
        round_count=0,
        max_rounds=5,
        sentiment="neutral",
        handoff_flag=False,
        handoff_reason=None,
        created_at=_now(),
        updated_at=_now(),
    )
    data.update(overrides)
    return NegotiationSession(**data)


def test_anchor_opens_eight_percent_below_target_and_never_above_vendor_quote():
    from app.deal_engine import compute_anchor

    listing = make_listing()
    # 16_200 * 0.92 = 14_904, which is below the vendor's 18_500 ask
    assert compute_anchor(listing) == 14_904


def test_anchor_never_opens_above_the_vendor_quote():
    from app.deal_engine import compute_anchor

    listing = make_listing(vendor_quoted_unit_price=14_000, target_unit_price=16_200)
    assert compute_anchor(listing) == 14_000


def test_concession_schedule_is_diminishing_share_of_target_to_ceiling_room():
    from app.deal_engine import concession_schedule

    listing = make_listing()
    # room = 17_800 - 16_200 = 1_600
    schedule = concession_schedule(listing)
    assert schedule == [640.0, 400.0, 320.0, 240.0]
    assert schedule[0] > schedule[1] > schedule[2] > schedule[3]


def test_reject_when_order_total_would_cross_ten_lakh():
    from app.deal_engine import validate_offer

    listing = make_listing(quantity=40)
    session = make_session()
    # 30_000 * 40 = 12_00_000
    allowed, price, reason = validate_offer(30_000, session, listing)
    assert allowed is False
    assert price == 30_000
    assert reason == "above_10L_ceiling"


def test_reject_when_vendor_quoted_total_already_exceeds_ceiling():
    from app.deal_engine import validate_offer

    listing = make_listing(
        vendor_quoted_unit_price=62_000,
        quantity=20,
        target_unit_price=54_000,
        max_acceptable_unit_price=59_000,
    )
    session = make_session()
    allowed, _, reason = validate_offer(54_000, session, listing)
    assert allowed is False
    assert reason == "above_10L_ceiling"


def test_reject_when_buyer_ceiling_times_qty_already_exceeds_ten_lakh():
    from app.deal_engine import check_order_eligibility

    listing = make_listing(
        vendor_quoted_unit_price=18_500,
        quantity=60,
        max_acceptable_unit_price=17_800,
    )
    # 17_800 * 60 = 10_68_000
    eligible, reason = check_order_eligibility(listing)
    assert eligible is False
    assert reason == "above_10L_ceiling"


def test_order_under_ceiling_is_eligible():
    from app.deal_engine import check_order_eligibility

    listing = make_listing()
    eligible, reason = check_order_eligibility(listing)
    assert eligible is True
    assert reason is None


def test_clamp_offer_that_goes_above_max_acceptable():
    from app.deal_engine import validate_offer

    listing = make_listing()
    session = make_session()
    allowed, price, reason = validate_offer(19_500, session, listing)
    assert allowed is True
    assert price == listing.max_acceptable_unit_price
    assert reason is None


def test_reject_when_max_rounds_reached():
    from app.deal_engine import validate_offer

    listing = make_listing()
    session = make_session(round_count=5, max_rounds=5)
    allowed, _, reason = validate_offer(16_200, session, listing)
    assert allowed is False
    assert reason == "max_rounds_reached"


def test_allow_valid_offer_inside_envelope():
    from app.deal_engine import validate_offer

    listing = make_listing()
    session = make_session()
    allowed, price, reason = validate_offer(16_200, session, listing)
    assert allowed is True
    assert price == 16_200
    assert reason is None


def test_impasse_when_vendor_repeats_the_same_number_twice():
    from app.deal_engine import detect_impasse

    session = make_session(
        concession_history=[
            ConcessionEvent(
                round_number=1,
                vendor_offer=18_000,
                bot_offer=15_544,
                justification_tactic="anchoring_hold",
                timestamp=_now(),
            ),
            ConcessionEvent(
                round_number=2,
                vendor_offer=18_000,
                bot_offer=15_944,
                justification_tactic="competitive_bid",
                timestamp=_now(),
            ),
        ]
    )
    assert detect_impasse(session) is True


def test_no_impasse_when_first_round_had_no_stated_vendor_price():
    from app.deal_engine import detect_impasse

    session = make_session(
        concession_history=[
            ConcessionEvent(
                round_number=1,
                vendor_offer=None,
                bot_offer=15_544,
                justification_tactic="lead_time_trade",
                timestamp=_now(),
            ),
            ConcessionEvent(
                round_number=2,
                vendor_offer=18_500,
                bot_offer=15_944,
                justification_tactic="competitive_bid",
                timestamp=_now(),
            ),
        ]
    )
    assert detect_impasse(session) is False


def test_no_impasse_when_vendor_offer_is_still_moving():
    from app.deal_engine import detect_impasse

    session = make_session(
        concession_history=[
            ConcessionEvent(
                round_number=1,
                vendor_offer=18_500,
                bot_offer=15_544,
                justification_tactic="anchoring_hold",
                timestamp=_now(),
            ),
            ConcessionEvent(
                round_number=2,
                vendor_offer=17_800,
                bot_offer=15_944,
                justification_tactic="competitive_bid",
                timestamp=_now(),
            ),
        ]
    )
    assert detect_impasse(session) is False


def test_should_accept_is_graduated_above_target():
    from app.deal_engine import near_target_price, offer_in_envelope, should_accept

    listing = make_listing(
        max_acceptable_lead_time_days=35,
        max_acceptable_moq=50,
        fastest_payment_terms="Net 30",
    )
    ceiling = {"unit_price": 17_800}
    floor_pkg = {"unit_price": 17_200, "payment_terms": "Net 60", "moq": 50}
    assert offer_in_envelope(ceiling, listing) is True
    assert offer_in_envelope({"unit_price": 17_801}, listing) is False
    assert offer_in_envelope({"unit_price": None}, listing) is False
    assert offer_in_envelope({"unit_price": 17_500, "moq": 80}, listing) is False
    assert offer_in_envelope({"unit_price": 17_500, "lead_time_days": 45}, listing) is False
    assert offer_in_envelope(floor_pkg, listing) is True
    assert near_target_price(16_200, listing) is True
    assert near_target_price(16_600, listing) is True
    assert near_target_price(16_800, listing) is False

    session = make_session(round_count=0, in_range_push_done=False)
    assert should_accept({"unit_price": 16_200}, listing, session=session) is True
    assert should_accept(ceiling, listing, session=session, signal_confidence="low") is False
    assert should_accept(ceiling, listing, session=session, signal_confidence="high") is True

    pushed = make_session(round_count=1, in_range_push_done=True)
    assert should_accept(ceiling, listing, session=pushed, signal_confidence="low") is True

    last_round = make_session(round_count=4, max_rounds=5, in_range_push_done=False)
    assert should_accept(ceiling, listing, session=last_round, signal_confidence="medium") is True


def test_order_total_over_ceiling_is_blocked():
    from app.deal_engine import validate_order_total

    allowed, total, reason = validate_order_total(18_500, 60)
    assert allowed is False
    assert total == 1_110_000
    assert reason == "above_10L_ceiling"


def test_order_total_under_ceiling_is_allowed():
    from app.deal_engine import validate_order_total

    allowed, total, reason = validate_order_total(18_500, 40)
    assert allowed is True
    assert total == 740_000
    assert reason is None


def test_next_authorized_offer_rises_by_schedule_and_never_above_max():
    from app.deal_engine import next_authorized_offer

    listing = make_listing()
    session = make_session(current_bot_offer=14_904, round_count=0)
    assert next_authorized_offer(session, listing) == 15_544

    near_max = make_session(current_bot_offer=17_500, round_count=0)
    assert next_authorized_offer(near_max, listing) == 17_800


def test_later_rounds_stop_raising_price_once_schedule_is_exhausted():
    from app.deal_engine import next_authorized_offer

    listing = make_listing()
    session = make_session(current_bot_offer=16_500, round_count=4)
    assert next_authorized_offer(session, listing) == 16_500


def test_competitive_bid_uses_only_stored_alternate_quotes():
    from app.deal_engine import best_alternate_unit_price

    listing = make_listing()
    assert best_alternate_unit_price(listing) == 17_200
    empty = make_listing(alternate_vendor_quotes=[])
    assert best_alternate_unit_price(empty) is None


def test_hostile_language_is_an_escalation_signal():
    from app.deal_engine import detect_hostile_language

    assert detect_hostile_language("this is a scam you cheat") is True
    assert detect_hostile_language("can you improve the unit price on a 12-month release?") is False


def test_deal_engine_module_has_zero_llm_imports():
    import ast

    source = Path(__file__).resolve().parents[1] / "app" / "deal_engine.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    forbidden = {
        "anthropic",
        "openai",
        "langchain",
        "langchain_core",
        "langgraph",
        "httpx",
        "requests",
    }
    assert imported.isdisjoint(forbidden)


def test_public_listing_never_includes_max_or_target():
    from app.models import to_public_listing

    listing = make_listing()
    public = to_public_listing(listing).model_dump()
    assert "max_acceptable_unit_price" not in public
    assert "target_unit_price" not in public
    assert "alternate_vendor_quotes" not in public
    assert "max_acceptable_lead_time_days" not in public
    assert "max_acceptable_moq" not in public
    assert "preferred_payment_terms" not in public
    assert public["vendor_quoted_unit_price"] == listing.vendor_quoted_unit_price
    assert public["quantity"] == listing.quantity


def test_qty_bump_package_over_ten_lakh_is_a_ceiling_violation():
    from app.deal_engine import (
        check_order_eligibility,
        offer_in_envelope,
        package_ceiling_reason,
        should_accept,
    )

    listing = make_listing(
        vendor_quoted_unit_price=24_800,
        quantity=40,
        target_unit_price=22_000,
        max_acceptable_unit_price=24_500,
        max_acceptable_moq=50,
        alternate_vendor_quotes=[],
    )
    assert check_order_eligibility(listing) == (True, None)
    package = {"unit_price": 24_500, "moq": 42}
    assert offer_in_envelope(package, listing) is False
    assert should_accept(package, listing, session=make_session()) is False
    assert (
        package_ceiling_reason(listing, unit_price=24_500, moq=42)
        == "above_10L_ceiling"
    )
    assert package_ceiling_reason(listing, unit_price=24_500, moq=40) is None
    assert package_ceiling_reason(listing, unit_price=None, moq=42) == "above_10L_ceiling"
