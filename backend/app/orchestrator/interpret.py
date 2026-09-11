"""Deterministic read of a vendor message.

No LLM in this module. Multi-part messages ("₹17,800 works but only at
Net 60 and MOQ 50") must yield every constraint, not just the price.
"""

from __future__ import annotations

import re

from app.deal_engine import detect_hostile_language, extract_all_rupee_amounts
from app.models import Interpretation, NegotiationSession, PartListing
from app.orchestrator.qualify import looks_like_acceptance

INTENTS = (
    "counter_offer",
    "objection_price",
    "objection_quality",
    "objection_leadtime",
    "stalling",
    "clarifying_question",
    "acceptance",
    "rejection",
    "small_talk",
)

_NET = re.compile(r"\bnet\s*(15|30|45|60|90)\b", re.I)
_MOQ = re.compile(
    r"\b(?:moq|minimum(?:\s+order)?(?:\s+quantity)?|min(?:imum)?\s*qty)\s*(?:of\s*|:?\s*)(\d{1,5})\b",
    re.I,
)
_LEAD = re.compile(r"\b(\d{1,3})\s*(days?|weeks?)\b", re.I)
_LEAD_BARE = re.compile(r"\blead[\s-]*time\s*(?:of\s*|:?\s*)(\d{1,3})\b", re.I)
_WARRANTY = re.compile(r"\b(\d{1,2})\s*(month|months|year|years)\s+warrant", re.I)
_STALL = re.compile(
    r"\b(let me (?:check|ask|confirm)|i'?ll get back|need to ask|circle back|check with (?:my )?(?:manager|boss|plant))\b",
    re.I,
)
_REJECT = re.compile(
    r"\b(no deal|not possible|impossible|can'?t do that|won'?t work|forget it|walk away)\b",
    re.I,
)
_PRICE_REJECT = re.compile(
    r"isn'?t feasible|not feasible|can'?t go that low|"
    r"below (?:our|what we) (?:cost|floor|margin|can)|significantly below|"
    r"below what we can|can'?t accept|cannot accept|won'?t accept|"
    r"too low for (?:us|our)|can'?t align|cannot align|cost floor|cost threshold",
    re.I,
)
_PRICE_OBJ = re.compile(
    r"\b(too (?:low|cheap|expensive)|price is (?:too )?(?:low|high)|won'?t work at (?:that|this) price|"
    r"can'?t (?:do|hit|meet) (?:that|this) (?:price|number)|margin)\b",
    re.I,
)
_LEAD_OBJ = re.compile(
    r"\b(lead[\s-]*time|too slow|too long|delivery|can'?t hit \d+\s*days?|need \d+\s*(?:days?|weeks?)|"
    r"won'?t make .{0,20}days?)\b",
    re.I,
)
_QUALITY_OBJ = re.compile(
    r"\b(quality|warranty|ppap|reject rate|ppm|scrap|fitment|spec)\b",
    re.I,
)
_OPENING = re.compile(r"\b(starting at|opening|ballpark|looking at|around)\b", re.I)
_FINAL = re.compile(r"\b(final|bottom line|can'?t go (?:lower|further)|last (?:price|offer)|firm)\b", re.I)
_FLOOR = re.compile(
    r"can'?t go below|cannot go below|won'?t go below|"
    r"below our (?:cost|floor|margin)|cost (?:floor|line|threshold|structure)|"
    r"\bat cost\b|resin|metal index|production slot|locked .{0,24}slot|"
    r"our floor|walk-?away",
    re.I,
)
_COOPERATIVE = re.compile(
    r"\b(works|can do|happy to|willing|if you|flexible|let'?s|we can)\b",
    re.I,
)
_CEILING_PROBE = re.compile(
    r"what(?:'s| is) (?:your |the )?(?:max|maximum|ceiling|walk-?away|limit|authorization)|"
    r"how (?:high|far) can you (?:go|come)|"
    r"(?:your|the) (?:walk-?away|ceiling|max(?:imum)?|authorization limit)|"
    r"best (?:you|buyer) can (?:do|pay)|"
    r"what number can you actually not exceed|"
    r"share (?:the |your )?(?:walk-?away|ceiling|max)|"
    r"just tell me your ceiling",
    re.I,
)
_FRUSTRATED = re.compile(
    r"\b(ridiculous|unrealistic|already (?:low|thin)|hurting|squeezing|come on)\b",
    re.I,
)


def empty_facts() -> dict:
    return {
        "counter_price": None,
        "payment_terms_requested": None,
        "moq_requested": None,
        "lead_time_requested": None,
        "other_constraints": [],
        "ceiling_probe": False,
    }


def extract_facts(text: str, bot_offer: int | None = None) -> dict:
    facts = empty_facts()
    if not text or not text.strip():
        return facts

    net = _NET.search(text)
    if net:
        facts["payment_terms_requested"] = f"Net {net.group(1)}"

    moq = _MOQ.search(text)
    if moq:
        facts["moq_requested"] = int(moq.group(1))

    lead_matches = list(_LEAD.finditer(text))
    chosen_lead = None
    if lead_matches:
        chosen_lead = lead_matches[-1]
        for match in lead_matches:
            window = text[max(0, match.start() - 24) : match.end()].lower()
            if any(token in window for token in ("need", "want", "only", "require", "at least", "to")):
                chosen_lead = match
                break
        days = int(chosen_lead.group(1))
        if "week" in chosen_lead.group(2).lower():
            days *= 7
        facts["lead_time_requested"] = days
    else:
        bare = _LEAD_BARE.search(text)
        if bare:
            facts["lead_time_requested"] = int(bare.group(1))

    need_span = re.search(
        r"\b(?:need|want|require)\s+(\d{1,3})\s*(days?|weeks?)?\b",
        text,
        re.I,
    )
    if need_span and (
        facts["lead_time_requested"] is not None
        or _LEAD.search(text)
        or "lead" in text.lower()
        or "deliver" in text.lower()
    ):
        days = int(need_span.group(1))
        unit = need_span.group(2) or ""
        if "week" in unit.lower():
            days *= 7
        if days < 500:
            facts["lead_time_requested"] = days

    warranty = _WARRANTY.search(text)
    if warranty:
        months = int(warranty.group(1))
        if "year" in warranty.group(2).lower():
            months *= 12
        facts["other_constraints"].append(f"warranty_{months}_months")

    amounts = extract_all_rupee_amounts(text)
    filtered: list[int] = []
    for price in amounts:
        if facts["moq_requested"] == price:
            continue
        if facts["lead_time_requested"] == price:
            continue
        if price < 500:
            continue
        filtered.append(price)
    facts["counter_price"] = pick_vendor_counter(text, filtered, bot_offer)
    if _CEILING_PROBE.search(text or ""):
        facts["ceiling_probe"] = True
        facts["other_constraints"].append("ceiling_probe")
    return facts


def pick_vendor_counter(text: str, amounts: list[int], bot_offer: int | None) -> int | None:
    """Prefer the vendor's own number, not a restatement of Aria's bid they are rejecting."""
    if not amounts:
        return None
    if bot_offer:
        others = [amount for amount in amounts if amount != bot_offer]
        if others:
            return others[-1]
        if _PRICE_REJECT.search(text or "") or _REJECT.search(text or ""):
            return None
        if looks_like_acceptance(text or ""):
            return bot_offer
        return None
    return amounts[-1]


def classify_intent(text: str, facts: dict) -> str:
    stripped = (text or "").strip()
    if not stripped:
        return "small_talk"

    if looks_like_acceptance(stripped) and facts.get("counter_price") is None:
        return "acceptance"
    if _STALL.search(stripped):
        return "stalling"
    if (_REJECT.search(stripped) or _PRICE_REJECT.search(stripped)) and facts.get("counter_price") is None:
        return "rejection"

    lead_obj = bool(_LEAD_OBJ.search(stripped) or facts.get("lead_time_requested"))
    price_obj = bool(_PRICE_OBJ.search(stripped))
    quality_obj = bool(_QUALITY_OBJ.search(stripped))
    has_price = facts.get("counter_price") is not None
    package = any(
        facts.get(key)
        for key in ("payment_terms_requested", "moq_requested", "lead_time_requested")
    )

    if has_price and (package or re.search(r"\b(works|can do|offer|at)\b", stripped, re.I)):
        return "counter_offer"
    if lead_obj and not has_price:
        return "objection_leadtime"
    if quality_obj and not has_price:
        return "objection_quality"
    if has_price:
        return "counter_offer"
    if price_obj:
        return "objection_price"
    if lead_obj:
        return "objection_leadtime"
    if "?" in stripped:
        return "clarifying_question"
    if len(stripped.split()) <= 4 and not package:
        return "small_talk"
    if package:
        return "counter_offer"
    return "small_talk"


def classify_sentiment(text: str) -> str:
    if detect_hostile_language(text or ""):
        return "aggressive"
    if _FRUSTRATED.search(text or ""):
        return "frustrated"
    if _COOPERATIVE.search(text or ""):
        return "cooperative"
    return "neutral"


def classify_confidence(
    text: str,
    facts: dict,
    session: NegotiationSession,
) -> str:
    lowered = (text or "").lower()
    counter = facts.get("counter_price")
    if _FINAL.search(lowered) or _FLOOR.search(lowered):
        return "high"
    if session.vendor_justified_floor and counter is not None:
        return "high"
    if (
        counter is not None
        and session.concession_history
        and session.concession_history[-1].vendor_offer == counter
    ):
        return "high"
    if session.round_count >= 2 and counter is not None:
        return "high"
    if session.round_count == 0 or _OPENING.search(lowered):
        return "low"
    return "medium"


def interpret_message(
    text: str,
    session: NegotiationSession,
    listing: PartListing | None = None,
) -> Interpretation:
    facts = extract_facts(text, bot_offer=session.current_bot_offer or None)
    if _FLOOR.search(text or ""):
        session.vendor_justified_floor = True
    intent = classify_intent(text, facts)
    sentiment = classify_sentiment(text)
    confidence = classify_confidence(text, facts, session)
    _ = listing
    return Interpretation(
        extracted_facts=facts,
        intent=intent,
        sentiment=sentiment,
        signal_confidence=confidence,
    )
