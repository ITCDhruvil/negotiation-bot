"""Deterministic deal engine — buyer-side B2B procurement.

Zero LLM calls in this file, by design. The model proposes a unit price
it is willing to pay; this module decides whether that number may be said.

The bot represents the buyer. It opens low and must never agree to pay
above max_acceptable_unit_price. The ₹10L gate is on order total
(unit × quantity), not on the unit price.

Note: at production quantities, many automotive-part lines will trip the
₹10L total immediately. That may be intentional for a low-risk POC —
confirm before treating it as a production threshold.
"""

from __future__ import annotations

import re

from app.models import PartListing, NegotiationSession

CEILING = 1_000_000  # ₹10,00,000 on the negotiated order total, not model-editable

_HOSTILE_PATTERNS = (
    r"\bscam\b",
    r"\bcheat(er|ing)?\b",
    r"\bfraud\b",
    r"\bidiot\b",
    r"\bstupid\b",
    r"\bshut up\b",
    r"\bgo to hell\b",
    r"\bwaste of (time|money)\b",
    r"\bripoff\b",
    r"\brip-off\b",
    r"\bdamn you\b",
    r"\basshole\b",
    r"\bbastard\b",
)


def order_total(unit_price: int, quantity: int) -> int:
    return unit_price * quantity


def compute_anchor(listing: PartListing) -> int:
    """Open low: 8% below target, never above the vendor's quoted ask."""
    low = int(listing.target_unit_price * 0.92)
    return min(listing.vendor_quoted_unit_price, low)


def concession_schedule(listing: PartListing) -> list[float]:
    """Diminishing upward concessions toward the buyer's walk-away."""
    total_room = max(0, listing.max_acceptable_unit_price - listing.target_unit_price)
    return [total_room * pct for pct in (0.40, 0.25, 0.20, 0.15)]


def effective_order_quantity(
    listing: PartListing,
    *,
    moq: int | None = None,
    session: NegotiationSession | None = None,
) -> int:
    """RFQ quantity, raised by a stated MOQ or an already-accepted session MOQ."""
    qty = listing.quantity
    if session is not None and isinstance(session.current_moq, int):
        qty = max(qty, session.current_moq)
    if isinstance(moq, int):
        qty = max(qty, moq)
    return qty


def check_order_eligibility(
    listing: PartListing, quantity: int | None = None
) -> tuple[bool, str | None]:
    """₹10L gate: quoted total *or* walk-away total already over the ceiling."""
    qty = listing.quantity if quantity is None else quantity
    quoted_total = order_total(listing.vendor_quoted_unit_price, qty)
    max_total = order_total(listing.max_acceptable_unit_price, qty)
    if quoted_total > CEILING or max_total > CEILING:
        return False, "above_10L_ceiling"
    return True, None


def validate_offer(
    proposed_price: int, session: NegotiationSession, listing: PartListing
) -> tuple[bool, int, str | None]:
    """Returns (is_allowed, final_unit_price_to_use, handoff_reason_if_any)."""
    qty = effective_order_quantity(listing, session=session)
    quoted_total = order_total(listing.vendor_quoted_unit_price, qty)
    proposed_total = order_total(proposed_price, qty)
    if proposed_total > CEILING or quoted_total > CEILING:
        return False, proposed_price, "above_10L_ceiling"
    if proposed_price > listing.max_acceptable_unit_price:
        # Model tried to pay above the walk-away — clamp down, don't trust it
        clamped = listing.max_acceptable_unit_price
        if order_total(clamped, qty) > CEILING:
            return False, proposed_price, "above_10L_ceiling"
        return True, clamped, None
    if session.round_count >= session.max_rounds:
        return False, proposed_price, "max_rounds_reached"
    return True, proposed_price, None


def validate_order_total(unit_price: int, quantity: int) -> tuple[bool, int, str | None]:
    """Hard-stop the moment unit × qty would cross ₹10L."""
    total = order_total(unit_price, quantity)
    if total > CEILING:
        return False, total, "above_10L_ceiling"
    return True, total, None


def detect_impasse(session: NegotiationSession) -> bool:
    """Vendor repeated the same *stated* unit price twice. Catalog fallbacks do not count."""
    stated = [event.vendor_offer for event in session.concession_history if event.vendor_offer is not None]
    if len(stated) < 2:
        return False
    return stated[-1] == stated[-2]


def next_authorized_offer(session: NegotiationSession, listing: PartListing) -> int:
    """Largest raise the engine will authorize this round. Never above walk-away."""
    schedule = concession_schedule(listing)
    if session.round_count >= len(schedule):
        return session.current_bot_offer
    raise_by = int(schedule[session.round_count])
    proposed = session.current_bot_offer + raise_by
    return min(proposed, listing.max_acceptable_unit_price)


HOLD_PRICE_TACTICS = frozenset(
    {
        "lead_time_trade",
        "warranty_trade",
        "calibrated_question",
        "clarify_hold",
        "redirect",
        "anchoring_hold",
        "moq_trade",
    }
)


def resolved_max_lead_time(listing: PartListing) -> int:
    if listing.max_acceptable_lead_time_days is not None:
        return listing.max_acceptable_lead_time_days
    return listing.lead_time_days + 14


def resolved_max_moq(listing: PartListing) -> int:
    if listing.max_acceptable_moq is not None:
        return listing.max_acceptable_moq
    return max(listing.quantity, listing.moq or listing.quantity)


def resolved_target_lead_time(listing: PartListing) -> int:
    return listing.target_lead_time_days or listing.lead_time_days


def payment_term_days(term: str | None) -> int | None:
    if not term:
        return None
    match = re.search(r"(\d+)", term)
    return int(match.group(1)) if match else None


def validate_trade(
    listing: PartListing,
    *,
    moq: int | None = None,
    lead_time_days: int | None = None,
    payment_terms: str | None = None,
) -> tuple[bool, str | None]:
    """Buyer envelopes for non-price dimensions. No LLM."""
    if moq is not None and moq > resolved_max_moq(listing):
        return False, "moq_above_max"
    if lead_time_days is not None and lead_time_days > resolved_max_lead_time(listing):
        return False, "lead_time_above_max"
    if payment_terms:
        requested = payment_term_days(payment_terms)
        fastest = payment_term_days(listing.fastest_payment_terms) or 30
        if requested is not None and requested < fastest:
            return False, "payment_terms_too_fast"
    return True, None


NEAR_TARGET_RATIO = 0.03


def offer_in_envelope(vendor_offer: dict, listing: PartListing) -> bool:
    """True when the stated package is payable — inside walk-away and term bounds."""
    price = vendor_offer.get("unit_price") if vendor_offer else None
    if price is None or not isinstance(price, int):
        return False
    if price > listing.max_acceptable_unit_price:
        return False

    moq = vendor_offer.get("moq")
    lead = vendor_offer.get("lead_time_days")
    terms = vendor_offer.get("payment_terms")
    ok, _ = validate_trade(
        listing,
        moq=moq if isinstance(moq, int) else None,
        lead_time_days=lead if isinstance(lead, int) else None,
        payment_terms=terms if isinstance(terms, str) else None,
    )
    if not ok:
        return False

    qty = effective_order_quantity(listing, moq=moq if isinstance(moq, int) else None)
    ok_total, _, _ = validate_order_total(price, qty)
    return bool(ok_total)


def package_ceiling_reason(
    listing: PartListing,
    *,
    unit_price: int | None,
    moq: int | None = None,
    session: NegotiationSession | None = None,
) -> str | None:
    """Handoff if the vendor's stated package (unit × effective qty) would cross ₹10L.

    A quantity bump with no new unit price is checked against the vendor's current ask.
    """
    qty = effective_order_quantity(listing, moq=moq, session=session)
    price = unit_price
    if price is None:
        if qty <= listing.quantity:
            return None
        if session is not None and isinstance(session.current_vendor_offer, int):
            price = session.current_vendor_offer
        else:
            price = listing.vendor_quoted_unit_price
    ok, _, reason = validate_order_total(price, qty)
    return None if ok else reason


def near_target_price(price: int, listing: PartListing) -> bool:
    band = int(listing.target_unit_price * (1 + NEAR_TARGET_RATIO))
    return price <= max(listing.target_unit_price, band)


def should_accept(
    vendor_offer: dict,
    listing: PartListing,
    *,
    session: NegotiationSession | None = None,
    signal_confidence: str | None = None,
) -> bool:
    """Graduated accept: envelope first, then target / justified floor / one push.

    An in-range opening that sits meaningfully above target is not a close until
    we have pushed once, unless interpret marks the offer high-confidence.
    """
    if not offer_in_envelope(vendor_offer, listing):
        return False
    price = vendor_offer["unit_price"]
    if near_target_price(price, listing):
        return True
    if (signal_confidence or "").lower() == "high":
        return True
    if session is None:
        return False
    if session.round_count >= max(0, session.max_rounds - 1):
        return True
    if session.in_range_push_done:
        return True
    return False


def authorized_price_for_tactic(session: NegotiationSession, listing: PartListing, tactic: str) -> int:
    """Hold unit price when the objection is not a price objection."""
    if tactic in HOLD_PRICE_TACTICS:
        return session.current_bot_offer or compute_anchor(listing)
    return next_authorized_offer(session, listing)


def best_alternate_unit_price(listing: PartListing) -> int | None:
    """Real stored quotes only. None if we have no competitive bid to cite."""
    if not listing.alternate_vendor_quotes:
        return None
    return min(quote.unit_price for quote in listing.alternate_vendor_quotes)


def detect_hostile_language(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in _HOSTILE_PATTERNS)


def extract_all_rupee_amounts(text: str) -> list[int]:
    """Every INR-looking unit price in the message, in order of appearance."""
    cleaned = text.lower().replace(",", "").replace("₹", " ")
    amounts: list[int] = []
    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*lakh", cleaned):
        amounts.append(int(float(match.group(1)) * 100_000))
    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*cr(?:ore)?", cleaned):
        amounts.append(int(float(match.group(1)) * 10_000_000))
    if amounts:
        return amounts
    seen: set[int] = set()
    ordered: list[int] = []
    for match in re.finditer(r"\b(\d{4,8})\b", cleaned):
        value = int(match.group(1))
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def extract_rupee_amount(text: str) -> int | None:
    """Parse a vendor-stated INR unit price. Lakh/crore shorthand supported."""
    amounts = extract_all_rupee_amounts(text)
    return amounts[0] if amounts else None
