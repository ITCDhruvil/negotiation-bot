from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import uuid4

from app.catalog import add_request, get_part, get_request, list_requests
from app.models import (
    AlternateQuote,
    CreateRfqRequest,
    PartListing,
    ProcurementRequest,
    RfqDraft,
    RfqPartDraft,
)

UTC = timezone.utc


def slugify(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    slug = slug[:48] or fallback
    return slug


def unique_part_id(name: str, taken: set[str] | None = None) -> str:
    taken = taken or set()
    base = slugify(name, "part")
    if get_part(base) is None and base not in taken:
        return base
    for _ in range(12):
        candidate = f"{base}-{uuid4().hex[:6]}"
        if get_part(candidate) is None and candidate not in taken:
            return candidate
    return f"{base}-{uuid4().hex}"


def unique_request_id(explicit: str = "") -> str:
    if explicit.strip():
        base = slugify(explicit, "rfq")
        if get_request(base) is None:
            return base
        return f"{base}-{uuid4().hex[:4]}"
    year = datetime.now(UTC).year
    existing = {row.request_id for row in list_requests()}
    for index in range(1, 1000):
        candidate = f"rfq-{year}-{index:03d}"
        if candidate not in existing:
            return candidate
    return f"rfq-{year}-{uuid4().hex[:6]}"


def _vendor_id(part: RfqPartDraft) -> str:
    if part.vendor_id.strip():
        return slugify(part.vendor_id, "vendor")
    return slugify(part.vendor_name, "vendor")


def finalize_part(
    part: RfqPartDraft,
    *,
    request_id: str,
    title: str,
    plant: str,
    taken_ids: set[str] | None = None,
) -> PartListing:
    if not (part.part_name or "").strip():
        raise ValueError("Each line needs a part name.")
    if not (part.vendor_name or "").strip():
        raise ValueError(f"{part.part_name}: vendor name is required.")
    if not part.quantity or part.quantity < 1:
        raise ValueError(f"{part.part_name}: quantity must be at least 1.")
    if not part.vendor_quoted_unit_price or part.vendor_quoted_unit_price < 1:
        raise ValueError(f"{part.part_name}: vendor quoted unit price is required.")

    quote = part.vendor_quoted_unit_price
    target = part.target_unit_price if part.target_unit_price and part.target_unit_price > 0 else max(1, int(quote * 0.85))
    walk = (
        part.max_acceptable_unit_price
        if part.max_acceptable_unit_price and part.max_acceptable_unit_price > 0
        else max(target, int(quote * 0.96))
    )
    if walk < target:
        raise ValueError(f"{part.part_name}: walk-away must be at or above target unit price.")

    lead = part.lead_time_days if part.lead_time_days and part.lead_time_days > 0 else 28
    moq = part.moq if part.moq and part.moq > 0 else max(1, part.quantity // 2)
    alternates: list[AlternateQuote] = []
    for alt in part.alternate_vendor_quotes:
        if alt.vendor_name and alt.unit_price and alt.unit_price > 0:
            alternates.append(
                AlternateQuote(
                    vendor_id=slugify(alt.vendor_id or alt.vendor_name, "alt-vendor"),
                    vendor_name=alt.vendor_name.strip(),
                    unit_price=alt.unit_price,
                )
            )

    return PartListing(
        part_id=part.part_id.strip() or unique_part_id(part.part_name, taken_ids),
        part_name=part.part_name.strip(),
        category=(part.category or "Uncategorized").strip(),
        vendor_id=_vendor_id(part),
        vendor_name=part.vendor_name.strip(),
        vendor_quoted_unit_price=quote,
        quantity=part.quantity,
        moq=moq,
        target_unit_price=target,
        max_acceptable_unit_price=walk,
        lead_time_days=lead,
        payment_terms_default=(part.payment_terms_default or "Net 30").strip(),
        alternate_vendor_quotes=alternates,
        spec_blurb=(part.spec_blurb or "").strip(),
        request_id=request_id,
        request_title=title,
        plant=plant,
        target_lead_time_days=part.target_lead_time_days or lead,
        max_acceptable_lead_time_days=part.max_acceptable_lead_time_days or (lead + 14),
        max_acceptable_moq=part.max_acceptable_moq or max(moq, part.quantity),
        preferred_payment_terms=(part.preferred_payment_terms or "Net 60").strip(),
        fastest_payment_terms=(part.fastest_payment_terms or "Net 30").strip(),
        min_warranty_months=part.min_warranty_months or 24,
    )


def create_rfq(body: CreateRfqRequest) -> ProcurementRequest:
    title = body.title.strip()
    plant = (body.plant or "Pune").strip() or "Pune"
    if not title:
        raise ValueError("RFQ title is required.")
    if not body.parts:
        raise ValueError("Add at least one part line.")
    request_id = unique_request_id(body.request_id)
    taken: set[str] = set()
    listings: list[PartListing] = []
    for part in body.parts:
        listing = finalize_part(part, request_id=request_id, title=title, plant=plant, taken_ids=taken)
        taken.add(listing.part_id)
        listings.append(listing)
    req = ProcurementRequest(
        request_id=request_id,
        title=title,
        plant=plant,
        needed_by=body.needed_by or None,
        parts=listings,
    )
    return add_request(req)


def draft_to_create(draft: RfqDraft) -> CreateRfqRequest:
    return CreateRfqRequest(
        request_id=draft.request_id,
        title=draft.title,
        plant=draft.plant or "Pune",
        needed_by=draft.needed_by,
        parts=draft.parts,
    )
