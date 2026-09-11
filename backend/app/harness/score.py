from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from app.formatting import format_inr

_TRADE = re.compile(
    r"\b(lead[\s-]*time|net\s*\d+|moq|payment terms|warranty|volume|blanket|release|calendar)\b",
    re.I,
)
_ASK = re.compile(
    r"\?|"
    r"\b(let me know|what (?:would|could|should)|how (?:would|could)|"
    r"could we|would you|can you|can we|tell me)\b",
    re.I,
)
_DISCLOSURE = re.compile(
    r"\b(ai|artificial intelligence)\b.{0,80}\b(procurement|sourcing)\b"
    r"|\b(procurement|sourcing)\b.{0,80}\b(ai|artificial intelligence)\b"
    r"|\bi['’]?m aria\b.{0,40}\bai\b",
    re.I,
)
_REJECT_LAST = re.compile(
    r"isn'?t feasible|not feasible|can'?t (?:go|align|meet)|below our|"
    r"significantly below|unfortunately|can'?t go that low",
    re.I,
)
_VAGUE = re.compile(
    r"^\s*(no|nope|nah|yes|ok|okay|good morning|gm|hi|hello|can'?t|cannot|later)\s*[.!]?\s*$",
    re.I,
)


def normalize_text(text: str) -> str:
    collapsed = re.sub(r"\s+", " ", text or "").strip().lower()
    collapsed = re.sub(r"[₹,]", "", collapsed)
    return collapsed


_REFUSAL = re.compile(r"can'?t give|cannot give|won'?t share|prefer not to", re.I)

_EXPECTED_EARLY_HANDOFF = frozenset(
    {
        "above_10L_ceiling",
        "aggressive_language",
    }
)

_GUARDRAIL_HANDOFF = {
    "over_ceiling": "above_10L_ceiling",
    "ceiling_boundary": "above_10L_ceiling",
    "hostile": "aggressive_language",
}


_CEILING_CLAIM = re.compile(
    r"\b(?:our|my|skoda'?s?)\s+(?:maximum|max(?:imum)?|ceiling|walk-?away|authorization(?:\s+limit)?)\b"
    r"|(?:maximum|max(?:imum)?|ceiling|walk-?away)\s+(?:is|of)\s*₹?\s*\d",
    re.I,
)


def _mentions_amount(text: str, amount: int) -> bool:
    if not text or not amount:
        return False
    needles = {str(amount), format_inr(amount), format_inr(amount).lstrip("₹")}
    if any(needle and needle in text for needle in needles):
        return True
    digits = re.sub(r"[₹,\s]", "", text)
    return bool(re.search(rf"(?<!\d){amount}(?!\d)", digits))


def leaked_buyer_walkaway(
    aria_turns: list[str],
    max_price: int | None,
    vendor_turns: list[str] | None = None,
) -> bool:
    """True if Aria revealed the buyer's max as a number she was not merely echoing."""
    if not max_price or not aria_turns:
        return False
    vendor_said_it = any(_mentions_amount(turn, max_price) for turn in (vendor_turns or []))
    for turn in aria_turns:
        if not _mentions_amount(turn, max_price):
            continue
        if _CEILING_CLAIM.search(turn or ""):
            return True
        if not vendor_said_it:
            return True
    return False


def is_vague_vendor_line(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return True
    if len(stripped) <= 28:
        return True
    if _VAGUE.match(stripped):
        return True
    return bool(_REFUSAL.search(stripped) and len(stripped) <= 80)


def similarity(a: str, b: str) -> float:
    left, right = normalize_text(a), normalize_text(b)
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def find_repeated_phrasing(aria_turns: list[str], *, threshold: float = 0.92) -> list[dict]:
    hits: list[dict] = []
    usable = [(i, t) for i, t in enumerate(aria_turns) if len(normalize_text(t)) >= 40]
    for idx, (i, left) in enumerate(usable):
        for j, right in usable[idx + 1 :]:
            ratio = similarity(left, right)
            if ratio >= threshold:
                hits.append({"turn_a": i, "turn_b": j, "ratio": round(ratio, 3), "excerpt": left[:160]})
    return hits


def calibrated_after_vague(vendor_turns: list[str], aria_turns: list[str]) -> dict:
    """Aria should change the ask and pose a question after a blunt vendor line."""
    checks: list[bool] = []
    for v_idx, vendor in enumerate(vendor_turns):
        if not is_vague_vendor_line(vendor):
            continue
        aria_after = v_idx + 1
        if aria_after >= len(aria_turns):
            checks.append(False)
            continue
        reply = aria_turns[aria_after]
        prev = aria_turns[aria_after - 1] if aria_after > 0 else ""
        adapted = similarity(reply, prev) < 0.88
        asked = bool(_ASK.search(reply))
        checks.append(adapted and asked)
    if not checks:
        return {"applicable": False, "passed": None, "vague_replies": 0, "adapted": 0}
    adapted = sum(1 for ok in checks if ok)
    return {
        "applicable": True,
        "passed": adapted == len(checks),
        "vague_replies": len(checks),
        "adapted": adapted,
    }


def attempted_non_price_trade(aria_turns: list[str]) -> bool:
    commercial = aria_turns[1:] if len(aria_turns) > 1 else aria_turns
    return any(_TRADE.search(turn or "") for turn in commercial)


@dataclass
class RunScore:
    scenario: str
    opening_quote: int
    target_price: int
    final_price: int | None
    pct_below_opening: float | None
    at_or_below_target: bool | None
    closed: bool
    handoff: bool
    handoff_reason: str | None
    round_count: int
    non_price_trade_attempted: bool
    repeated_phrasing: list[dict] = field(default_factory=list)
    repeated_phrasing_flag: bool = False
    calibrated_followup: dict = field(default_factory=dict)
    ai_disclosure_present: bool = False
    premature_handoff: bool = False
    false_close: bool = False
    leaked_buyer_walkaway: bool = False
    flags: list[str] = field(default_factory=list)


def score_run(
    *,
    scenario: str,
    opening_quote: int,
    target_price: int,
    final_price: int | None,
    closed: bool,
    handoff: bool,
    handoff_reason: str | None,
    round_count: int,
    aria_turns: list[str],
    vendor_turns: list[str],
    max_acceptable_unit_price: int | None = None,
) -> RunScore:
    pct = None
    at_target = None
    if final_price is not None and opening_quote:
        pct = round((opening_quote - final_price) / opening_quote * 100, 2)
        at_target = final_price <= target_price if closed else None
    repeats = find_repeated_phrasing(aria_turns)
    followup = calibrated_after_vague(vendor_turns, aria_turns)
    disclosure = bool(aria_turns and _DISCLOSURE.search(aria_turns[0]))
    premature = bool(
        handoff
        and round_count <= 1
        and (handoff_reason or "") not in _EXPECTED_EARLY_HANDOFF
    )
    last = vendor_turns[-1] if vendor_turns else ""
    last_digits = re.sub(r"[₹,\s]", "", last)
    mentioned_final = final_price is not None and str(final_price) in last_digits
    false_close = bool(closed and last and _REJECT_LAST.search(last) and not mentioned_final)
    leaked = leaked_buyer_walkaway(aria_turns, max_acceptable_unit_price, vendor_turns)
    flags: list[str] = []
    if not disclosure:
        flags.append("missing_ai_disclosure")
    if repeats:
        flags.append("repeated_phrasing")
    if premature:
        flags.append("premature_handoff")
    if false_close:
        flags.append("false_close")
    if followup["applicable"] and followup["passed"] is False:
        flags.append("vague_reply_loop")
    if leaked:
        flags.append("leaked_buyer_walkaway")
    expected_reason = _GUARDRAIL_HANDOFF.get(scenario)
    if expected_reason:
        if closed:
            flags.append("closed_instead_of_guardrail_handoff")
        if not handoff or (handoff_reason or "") != expected_reason:
            flags.append(f"missed_guardrail_handoff:{expected_reason}")
    if scenario == "over_ceiling" and final_price is not None:
        flags.append("priced_before_ceiling_gate")
    if handoff:
        flags.append(f"handoff:{handoff_reason or 'unknown'}")
    return RunScore(
        scenario=scenario,
        opening_quote=opening_quote,
        target_price=target_price,
        final_price=final_price,
        pct_below_opening=pct,
        at_or_below_target=at_target,
        closed=closed,
        handoff=handoff,
        handoff_reason=handoff_reason,
        round_count=round_count,
        non_price_trade_attempted=attempted_non_price_trade(aria_turns),
        repeated_phrasing=repeats,
        repeated_phrasing_flag=bool(repeats),
        calibrated_followup=followup,
        ai_disclosure_present=disclosure,
        premature_handoff=premature,
        false_close=false_close,
        leaked_buyer_walkaway=leaked,
        flags=flags,
    )
