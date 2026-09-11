from app.catalog import get_part
from app.demo import remaining_script, resolve_preset


def test_default_persona_for_known_parts():
    assert resolve_preset("headlight-lh").id == "cooperative"
    assert resolve_preset("chassis-frame-front").id == "over_ceiling"
    assert resolve_preset("rear-subframe").id == "ceiling_boundary"


def test_generic_preset_for_unmapped_part():
    listing = get_part("brake-caliper-fr")
    assert listing is not None
    preset = resolve_preset(listing.part_id)
    assert preset.id == "live_demo"
    assert preset.walk_away_min < listing.vendor_quoted_unit_price
    assert preset.qualify_replies


def test_script_queue_pops_qualify_first():
    preset = resolve_preset("headlight-lh")
    queued = remaining_script("demo-session-1", preset)
    first = queued.pop(0)
    assert "Priya" in first
    assert "@" in first
