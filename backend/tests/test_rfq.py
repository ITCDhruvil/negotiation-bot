"""Tests for RFQ intake: parse labeled documents and persist new catalog lines."""

from pathlib import Path

import pytest

from app.catalog import get_part, list_requests, reset
from app.models import CreateRfqRequest, RfqPartDraft
from app.rfq.extract import parse_text
from app.rfq.service import create_rfq

SAMPLE = """
SKODA AUTO INDIA
Request for Quotation

RFQ title: Q4 fascia refresh — Pune plant
Plant: Pune
Needed by: 2026-11-30
RFQ id: rfq-test-fascia

Part name: Front Bumper Fascia
Category: Body
Vendor: Plastic Omnium India
Vendor quoted unit price: ₹8,400
Quantity: 60
MOQ: 30
Lead time: 28 days
Payment terms: Net 45
Target unit price: ₹7,200
Max acceptable unit price: ₹8,000
Warranty: 24 months
Spec: Painted front bumper fascia, colour-matched to Pune line.
Alternate vendor: Magna Exteriors at ₹7,850
"""


@pytest.fixture()
def isolated_catalog(tmp_path: Path, monkeypatch):
    dest = tmp_path / "user_rfqs.json"
    monkeypatch.setattr("app.catalog._USER_PATH", dest)
    reset()
    yield dest
    if dest.exists():
        dest.unlink()
    reset()


def test_parse_labeled_rfq_fills_required_fields():
    draft = parse_text(SAMPLE)
    assert draft.title.startswith("Q4 fascia refresh")
    assert draft.plant == "Pune"
    assert draft.needed_by == "2026-11-30"
    assert len(draft.parts) == 1
    part = draft.parts[0]
    assert part.part_name == "Front Bumper Fascia"
    assert part.vendor_name == "Plastic Omnium India"
    assert part.vendor_quoted_unit_price == 8400
    assert part.quantity == 60
    assert part.moq == 30
    assert part.target_unit_price == 7200
    assert part.max_acceptable_unit_price == 8000
    assert part.lead_time_days == 28
    assert part.payment_terms_default == "Net 45"
    assert part.min_warranty_months == 24
    assert part.alternate_vendor_quotes[0].vendor_name == "Magna Exteriors"
    assert part.alternate_vendor_quotes[0].unit_price == 7850
    assert part.missing == []


def test_parse_marks_missing_fields():
    draft = parse_text("RFQ title: Incomplete\nPlant: Pune\nPart name: Widget\n")
    assert draft.parts[0].part_name == "Widget"
    assert "vendor_name" in draft.parts[0].missing
    assert "quantity" in draft.parts[0].missing
    assert "vendor_quoted_unit_price" in draft.parts[0].missing


def test_create_rfq_persists_and_is_negotiable(isolated_catalog: Path):
    created = create_rfq(
        CreateRfqRequest(
            title="Q4 fascia refresh — Pune plant",
            plant="Pune",
            needed_by="2026-11-30",
            parts=[
                RfqPartDraft(
                    part_name="Front Bumper Fascia",
                    category="Body",
                    vendor_name="Plastic Omnium India",
                    vendor_quoted_unit_price=8400,
                    quantity=60,
                    target_unit_price=7200,
                    max_acceptable_unit_price=8000,
                )
            ],
        )
    )
    assert created.request_id
    listing = created.parts[0]
    assert listing.target_unit_price == 7200
    assert listing.max_acceptable_unit_price == 8000
    assert listing.lead_time_days == 28
    assert get_part(listing.part_id) is not None
    ids = [row.request_id for row in list_requests()]
    assert created.request_id in ids
    assert isolated_catalog.exists()
    # Seed catalog is still intact.
    assert get_part("headlight-lh") is not None


def test_create_rfq_derives_buyer_envelope(isolated_catalog: Path):
    created = create_rfq(
        CreateRfqRequest(
            title="Harness top-up",
            plant="Pune",
            parts=[
                RfqPartDraft(
                    part_name="Cabin clip pack",
                    vendor_name="Yazaki India",
                    vendor_quoted_unit_price=1000,
                    quantity=10,
                )
            ],
        )
    )
    listing = created.parts[0]
    assert listing.target_unit_price == 850
    assert listing.max_acceptable_unit_price == 960


def test_rfq_routes_registered():
    from app.main import app

    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/api/rfq" in paths
    assert "/api/rfq/parse" in paths
    assert "/api/rfq/parse-text" in paths
