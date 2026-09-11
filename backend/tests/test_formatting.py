from app.deal_engine import extract_rupee_amount
from app.formatting import format_inr
from app.orchestrator.nodes import sanitize_prices


def test_indian_grouping():
    assert format_inr(1_000_000) == "₹10,00,000"
    assert format_inr(749_000) == "₹7,49,000"
    assert format_inr(999) == "₹999"


def test_sanitize_keeps_indian_grouped_unit_prices():
    allowed = {18_500, 14_904, 17_200, 40, 21}
    text = "Your quote is ₹18,500. Alternate ₹17,200. We can start at ₹14,904 per unit."
    out = sanitize_prices(text, allowed)
    assert "₹18,500" in out
    assert "₹17,200" in out
    assert "₹14,904" in out
    assert "₹200" not in out
    assert "₹214" not in out


def test_sanitize_does_not_collapse_unknown_prices_to_qty_or_lead_time():
    allowed = {18_500, 14_904, 17_200, 40, 21}
    out = sanitize_prices("We can do ₹16,000 per unit.", allowed)
    assert "₹21" not in out
    assert "₹40" not in out
    assert "₹200" not in out
    assert "₹14,904" in out or "₹17,200" in out or "₹18,500" in out


def test_parse_lakh_and_digits():
    assert extract_rupee_amount("I can do 7 lakh") == 700_000
    assert extract_rupee_amount("my budget is ₹7,20,000") == 720_000
    assert extract_rupee_amount("we can do 7200 per unit") == 7200
    assert extract_rupee_amount("just looking at features") is None
