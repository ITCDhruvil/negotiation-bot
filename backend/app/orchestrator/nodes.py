from __future__ import annotations

import asyncio
import contextvars
import logging
import re
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, TypedDict

from app.config import get_settings
from app.deal_engine import (
    CEILING,
    HOLD_PRICE_TACTICS,
    authorized_price_for_tactic,
    best_alternate_unit_price,
    check_order_eligibility,
    compute_anchor,
    detect_hostile_language,
    detect_impasse,
    effective_order_quantity,
    offer_in_envelope,
    order_total,
    package_ceiling_reason,
    resolved_max_lead_time,
    resolved_max_moq,
    resolved_target_lead_time,
    should_accept,
    validate_offer,
    validate_order_total,
    validate_trade,
)
from app.formatting import format_inr
from app.handoff.notify import execute_handoff
from app.llm.persona_prompt import render_persona_prompt
from app.llm.provider import LLMProvider, LLMTurn, MockProvider
from app.models import (
    ConcessionEvent,
    InsightTurn,
    Interpretation,
    NegotiationSession,
    NegotiationStage,
    PartListing,
)
from app.orchestrator.interpret import interpret_message
from app.orchestrator.qualify import (
    apply_qualification,
    can_proceed_without_contact,
    is_bare_decline,
    is_qualified,
    looks_like_acceptance,
    looks_like_contact_refusal,
)
from app.orchestrator.tactics import select_tactic
from app.playbook import classify_situation, format_lessons, record_lesson, render_playbook_block, retrieve_lessons
from app.rag.retriever import retrieve_grounding

logger = logging.getLogger("orchestrator")

TokenSink = Callable[[str], Awaitable[None]]
TOKEN_SINK: contextvars.ContextVar[TokenSink | None] = contextvars.ContextVar("token_sink", default=None)
PROVIDER: contextvars.ContextVar[LLMProvider | None] = contextvars.ContextVar("provider", default=None)


class TurnState(TypedDict, total=False):
    session: dict
    listing: dict
    user_message: str
    assistant_message: str
    transcript: list[dict]
    validated_price: int | None
    tactic: str | None
    interpretation: dict
    reasoning: str | None
    interpreted_intent: str | None


def _session(state: TurnState) -> NegotiationSession:
    return NegotiationSession.model_validate(state["session"])


def _listing(state: TurnState) -> PartListing:
    return PartListing.model_validate(state["listing"])


def _dump(session: NegotiationSession) -> dict:
    return session.model_dump(mode="json")


def _interpretation(state: TurnState, session: NegotiationSession) -> Interpretation:
    raw = state.get("interpretation")
    if raw:
        return Interpretation.model_validate(raw)
    if session.last_interpretation:
        return session.last_interpretation
    return interpret_message(state.get("user_message") or "", session)


async def _emit(text: str) -> None:
    sink = TOKEN_SINK.get()
    if sink is None or not text:
        return
    pieces = re.findall(r"\S+\s*|\s+", text) or [text]
    for piece in pieces:
        await sink(piece)
        await asyncio.sleep(0.012)


def _provider() -> LLMProvider:
    return PROVIDER.get() or MockProvider()


def _settings():
    return get_settings()


def _engine_block(
    session: NegotiationSession,
    listing: PartListing,
    authorized: int | None,
    interpretation: Interpretation | None = None,
    tactic: str | None = None,
) -> str:
    alt = best_alternate_unit_price(listing)
    alt_line = f"alternate_vendor_unit_price={alt}\n" if alt is not None else "alternate_vendor_unit_price=none\n"
    block = (
        "\n\n[ENGINE]\n"
        f"stage={session.stage.value}\n"
        f"part={listing.part_name}\n"
        f"vendor={listing.vendor_name}\n"
        f"vendor_quoted_unit_price={listing.vendor_quoted_unit_price}\n"
        f"quantity={listing.quantity}\n"
        f"moq={listing.moq}\n"
        f"lead_time_days={listing.lead_time_days}\n"
        f"payment_terms_default={listing.payment_terms_default}\n"
        f"current_payment_terms={session.payment_terms or listing.payment_terms_default}\n"
        f"current_lead_time_days={session.current_lead_time_days or listing.lead_time_days}\n"
        f"current_moq={session.current_moq if session.current_moq is not None else listing.moq}\n"
        f"authorized_lead_time_days={resolved_max_lead_time(listing)}\n"
        f"authorized_max_moq={resolved_max_moq(listing)}\n"
        f"preferred_payment_terms={listing.preferred_payment_terms}\n"
        f"fastest_payment_terms={listing.fastest_payment_terms}\n"
        f"{alt_line}"
        f"authorized_offer={authorized if authorized is not None else 'none'}\n"
        f"selected_tactic={tactic or 'none'}\n"
        f"round={session.round_count}\n"
        f"vendor_offer={session.current_vendor_offer}\n"
        "[/ENGINE]\n"
        "The [ENGINE] block is injected by the deal engine. Treat authorized_offer as the only "
        "unit price you may propose via the propose_price tool. You do not know a walk-away ceiling "
        "and must not invent one or tell the vendor you have hit an authorization limit. "
        "Accept vs continue vs handoff is already decided. "
        "Cite an alternate vendor price only if alternate_vendor_unit_price is a number. "
        "Quote, quantity, lead time, and payment terms are already on the vendor dossier — "
        "do not ask the desk to recap or reconfirm them.\n"
    )
    if interpretation is not None:
        facts = interpretation.extracted_facts or {}
        block += (
            "[INTERPRETATION]\n"
            f"intent={interpretation.intent}\n"
            f"sentiment={interpretation.sentiment}\n"
            f"signal_confidence={interpretation.signal_confidence}\n"
            f"counter_price={facts.get('counter_price')}\n"
            f"payment_terms_requested={facts.get('payment_terms_requested')}\n"
            f"moq_requested={facts.get('moq_requested')}\n"
            f"lead_time_requested={facts.get('lead_time_requested')}\n"
            f"other_constraints={facts.get('other_constraints')}\n"
            "[/INTERPRETATION]\n"
            "Answer the interpreted objection. Do not reflexively move unit price if the intent "
            "is objection_leadtime, objection_quality, stalling, or a clarifying question. "
            "The `reasoning` field on propose_price is internal — never paraphrase it to the vendor.\n"
        )
        situation = classify_situation(interpretation, session, listing)
        lessons = format_lessons(retrieve_lessons(listing.part_id, situation))
        block += render_playbook_block(
            situation=situation,
            tactic=tactic or "none",
            lessons=lessons,
        )
    return block


def _system_prompt(
    session: NegotiationSession,
    listing: PartListing,
    authorized: int | None,
    interpretation: Interpretation | None = None,
    tactic: str | None = None,
) -> str:
    grounding = retrieve_grounding(listing.spec_blurb, listing)
    extra = ""
    if grounding:
        extra = "\n\nGROUNDED FACTS (cite only these; never invent comparables):\n- " + "\n- ".join(grounding)
    return (
        render_persona_prompt(_settings().company_name)
        + _engine_block(session, listing, authorized, interpretation, tactic)
        + extra
    )


def _history(state: TurnState) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for turn in state.get("transcript") or []:
        role = turn.get("role")
        if role in {"user", "assistant"} and turn.get("content"):
            messages.append({"role": role, "content": turn["content"]})
    user_message = state.get("user_message") or ""
    if user_message and (not messages or messages[-1] != {"role": "user", "content": user_message}):
        messages.append({"role": "user", "content": user_message})
    return messages


_PRICE_RE = re.compile(
    r"₹\s*(?:\d{1,2}(?:,\d{2})*,\d{3}|\d{4,8})"
    r"|(?<![\d,])(?:\d{1,2}(?:,\d{2})*,\d{3}|\d{4,8})(?![\d,])"
)


def sanitize_prices(text: str, allowed: set[int]) -> str:
    # Quantity / lead-time / MOQ must never become the fallback "price"
    # (min({18500, 40, 21}) == 21 produced ₹21 / ₹200-class garbage in live runs).
    price_like = {n for n in allowed if n >= 1_000} or set(allowed)

    def repl(match: re.Match) -> str:
        raw = re.sub(r"[₹,\s]", "", match.group(0))
        if not raw.isdigit():
            return match.group(0)
        value = int(raw)
        if value in allowed:
            return match.group(0)
        if not price_like:
            return match.group(0)
        nearest = min(price_like, key=lambda p: abs(p - value))
        return format_inr(nearest)

    return _PRICE_RE.sub(repl, text)


def _spoken_prices(
    session: NegotiationSession, listing: PartListing, authorized: int | None
) -> set[int]:
    prices = {listing.vendor_quoted_unit_price}
    if authorized is not None:
        prices.add(authorized)
    if session.current_bot_offer:
        prices.add(session.current_bot_offer)
    if session.current_vendor_offer:
        prices.add(session.current_vendor_offer)
    alt = best_alternate_unit_price(listing)
    if alt is not None:
        prices.add(alt)
    for event in session.concession_history or []:
        if event.bot_offer:
            prices.add(event.bot_offer)
        if event.vendor_offer:
            prices.add(event.vendor_offer)
    return prices


_LEAK = re.compile(r"\[(?:INTERPRETATION|REASONING|INTERNAL|SITUATION|PLAYBOOK|LESSONS)\]", re.I)


def _strip_internal_leak(text: str) -> str:
    if _LEAK.search(text or ""):
        return ""
    return text


_VOICE = (
    "Talk like a person on chat, not a bot. Plain words. Contractions. 1-3 short sentences. "
    "No 'could you please', 'additionally', 'I appreciate', 'on behalf of', 'AI assistant', "
    "'thank you for your patience', or 'looking forward'."
)


async def _phrase(
    *,
    session: NegotiationSession,
    listing: PartListing,
    fallback: str,
    authorized: int | None,
    instruction: str,
    state: TurnState,
    interpretation: Interpretation | None = None,
    tactic: str | None = None,
) -> str:
    provider = _provider()
    if isinstance(provider, MockProvider):
        await _emit(fallback)
        return fallback
    try:
        chunks: list[str] = []
        spoken = f"{instruction} {_VOICE}"
        async for token in provider.stream_text(
            system=_system_prompt(session, listing, authorized, interpretation, tactic) + "\n\n" + spoken,
            messages=_history(state) + [{"role": "user", "content": spoken}],
        ):
            chunks.append(token)
            await _emit(token)
        text = _strip_internal_leak("".join(chunks).strip())
        if text:
            return sanitize_prices(text, _spoken_prices(session, listing, authorized))
    except Exception:
        logger.exception("LLM phrasing failed; using fallback")
    await _emit(fallback)
    return fallback


async def _complete(
    session: NegotiationSession,
    listing: PartListing,
    state: TurnState,
    hints: dict[str, Any],
    interpretation: Interpretation | None = None,
    tactic: str | None = None,
) -> LLMTurn:
    return await _provider().complete(
        system=_system_prompt(session, listing, hints.get("authorized_offer"), interpretation, tactic),
        messages=_history(state),
        hints=hints,
    )


def _missing_qualify_prompt(session: NegotiationSession, listing: PartListing) -> str:
    if session.contact_refusal_count >= 1:
        return (
            "That's fine — name and company is enough. We can pick up contact before a PO. "
            f"Who am I speaking with on the {listing.part_name} line?"
        )
    needs = []
    if not session.vendor_rep_name:
        needs.append("your name")
    if not session.vendor_rep_contact:
        needs.append("a phone or email")
    need_text = " and ".join(needs) if needs else "a couple of details"
    return (
        f"I need {need_text} before I put a number down. "
        f"Who am I speaking with on the {listing.part_name} line?"
    )


def _update_last_insight(
    session: NegotiationSession,
    *,
    tactic: str | None = None,
    reasoning: str | None = None,
    situation: str | None = None,
) -> None:
    if not session.insight_log:
        return
    last = session.insight_log[-1]
    if tactic:
        last.tactic = tactic
    if reasoning:
        last.reasoning = reasoning
    if situation:
        last.situation = situation


def _apply_trade(
    session: NegotiationSession,
    listing: PartListing,
    interpretation: Interpretation,
    tactic: str,
) -> str:
    """Mutate session commercial terms. Returns a vendor-facing trade clause (never reasoning)."""
    facts = interpretation.extracted_facts or {}
    parts: list[str] = []

    requested_terms = facts.get("payment_terms_requested")
    requested_moq = facts.get("moq_requested")
    requested_lead = facts.get("lead_time_requested")

    if tactic in {"lead_time_trade", "package_trade"} and requested_lead:
        ok, _reason = validate_trade(listing, lead_time_days=int(requested_lead))
        if ok:
            session.current_lead_time_days = int(requested_lead)
            parts.append(f"{requested_lead}-day lead time")
        else:
            stretch = resolved_max_lead_time(listing)
            session.current_lead_time_days = stretch
            parts.append(
                f"{requested_lead} days is outside this release — {stretch} days is the stretch I can do"
            )
    elif tactic == "lead_time_trade":
        hold = session.current_lead_time_days or resolved_target_lead_time(listing)
        session.current_lead_time_days = hold
        parts.append(f"holding {hold}-day lead time")

    if tactic in {"payment_terms_trade", "package_trade", "value_trade"}:
        if requested_terms:
            ok, _reason = validate_trade(listing, payment_terms=str(requested_terms))
            if ok:
                session.payment_terms = str(requested_terms)
                parts.append(str(requested_terms))
            else:
                session.payment_terms = listing.preferred_payment_terms
                parts.append(f"terms at {listing.preferred_payment_terms}")
        elif tactic == "payment_terms_trade":
            session.payment_terms = listing.preferred_payment_terms
            parts.append(f"if we move to {listing.preferred_payment_terms}")

    if tactic in {"package_trade", "moq_trade"} and requested_moq is not None:
        ok, _reason = validate_trade(listing, moq=int(requested_moq))
        if ok:
            session.current_moq = int(requested_moq)
            parts.append(f"MOQ {requested_moq}")
        else:
            cap = resolved_max_moq(listing)
            parts.append(f"MOQ {requested_moq} is above what this release can take — {cap} is the ceiling")

    if tactic == "warranty_trade":
        months = listing.min_warranty_months
        session.current_warranty_months = months
        parts.append(f"{months}-month warranty on this release")

    return "; ".join(parts)


def _fallback_for_tactic(
    *,
    tactic: str,
    interpretation: Interpretation,
    price: int,
    listing: PartListing,
    session: NegotiationSession,
    trade_clause: str,
    cite_alternate: bool = True,
) -> str:
    heard_price = (
        format_inr(session.current_vendor_offer)
        if session.current_vendor_offer
        else "that ask"
    )
    facts = interpretation.extracted_facts or {}
    lead_req = facts.get("lead_time_requested")

    if tactic == "lead_time_trade":
        if lead_req:
            return (
                f"I hear you on lead time — {lead_req} days is the constraint, not the unit price. "
                f"{trade_clause or 'We hold the RFQ window'}. Bid stays at {format_inr(price)} per unit. "
                "Which way do you want to play the calendar?"
            )
        return (
            f"Lead time is the issue I heard, so I'm not moving the rupee figure. "
            f"We can hold {format_inr(price)} per unit on a "
            f"{session.current_lead_time_days or listing.lead_time_days}-day window. What would close the calendar?"
        )
    if tactic == "warranty_trade":
        return (
            f"Quality is the objection, so I won't grind the unit price. "
            f"I'll hold {format_inr(price)} per unit if we lock {listing.min_warranty_months}-month warranty "
            "and PPAP on this release. Does that address it?"
        )
    if tactic == "calibrated_question":
        return (
            f"I'm holding {format_inr(price)} per unit while you check. "
            "What would it actually take to land this release this quarter — price, terms, or the calendar?"
        )
    if tactic == "clarify_hold":
        if facts.get("ceiling_probe"):
            return (
                f"I don't share a ceiling — that's not how this desk works. "
                f"We're at {format_inr(price)} per unit. What number can you actually do?"
            )
        return (
            f"Happy to clarify without moving the bid — we're at {format_inr(price)} per unit on "
            f"{listing.quantity} pieces, {session.current_lead_time_days or listing.lead_time_days} days, "
            f"{session.payment_terms or listing.payment_terms_default}. What specifically do you need?"
        )
    if tactic == "moq_trade":
        return (
            f"MOQ is the lever I heard, so the unit price stays {format_inr(price)}. "
            f"{trade_clause or 'Tell me the quantity that actually lands this release.'} "
            "Does that work?"
        )
    if tactic == "redirect":
        return (
            f"Back to the line: {listing.part_name} at {format_inr(price)} per unit. "
            "What would it take to close this quarter?"
        )
    if tactic == "anchoring_hold":
        return (
            f"I hear {heard_price}. That's an opening position from where I sit — I'm holding "
            f"{format_inr(price)} per unit on this quantity. What would it take to land there?"
        )
    if tactic == "package_trade":
        clause = trade_clause or "those terms"
        return (
            f"I can work with {clause} if we land at {format_inr(price)} per unit on {listing.quantity} pieces. "
            "That's the package, not a naked price move. Does that close it?"
        )
    if tactic == "payment_terms_trade":
        terms = session.payment_terms or listing.preferred_payment_terms
        return (
            f"I can hold {format_inr(price)} per unit if we lock this release. I'm at the edge of what I can do on unit price — "
            f"what I can still trade is payment terms ({terms}). Does that close it?"
        )
    if tactic == "value_trade":
        return (
            f"If the rupee figure is stuck, let's trade the rest: "
            f"{trade_clause or listing.preferred_payment_terms + ' or a longer release'} at {format_inr(price)} per unit. "
            "Does a package close it?"
        )
    if tactic == "competitive_bid" and cite_alternate and best_alternate_unit_price(listing):
        return (
            f"I hear you on {heard_price}. "
            f"We have a comparable quote at {format_inr(best_alternate_unit_price(listing))} per unit. "
            f"If you can confirm this quantity this quarter, we can move to {format_inr(price)}. Does that work?"
        )
    return (
        f"I hear you on {heard_price}. If we can lock a {listing.quantity}-unit release this quarter, I can move to "
        f"{format_inr(price)} per unit. That's the move I can make this round — what would close it?"
    )


def _tool_reasoning(call_input: dict, interpretation: Interpretation, tactic: str) -> tuple[str, str, str]:
    reasoning = str(call_input.get("reasoning") or "").strip()
    intent = str(call_input.get("interpreted_intent") or interpretation.intent)
    used_tactic = str(call_input.get("tactic") or tactic)
    if not reasoning:
        reasoning = (
            f"Vendor intent is {intent} at {interpretation.signal_confidence} confidence; "
            f"respond with {used_tactic}."
        )
    return reasoning, intent, used_tactic


async def greet_node(state: TurnState) -> dict:
    session = _session(state)
    listing = _listing(state)
    company = _settings().company_name
    fallback = (
        f"Hi — I'm Aria. I'm an AI, for {company} sourcing. "
        f"This is the {listing.part_name} line with {listing.vendor_name}. "
        "Who am I talking to?"
    )
    session.stage = NegotiationStage.QUALIFY
    session.payment_terms = session.payment_terms or listing.payment_terms_default
    session.current_lead_time_days = session.current_lead_time_days or listing.lead_time_days
    session.current_moq = session.current_moq if session.current_moq is not None else listing.moq
    text = await _phrase(
        session=session,
        listing=listing,
        fallback=fallback,
        authorized=None,
        instruction=(
            "Write the opening like a person texting. Disclose once, plainly, that you are an AI "
            "for the company's sourcing team — say 'I'm an AI', not 'AI assistant'. Name the part "
            "and vendor. Do not recap quote, quantity, lead time, or payment terms. Do not ask them "
            "to confirm those facts. Do not state a bid. Ask only who you are talking to. 1-3 sentences."
        ),
        state=state,
    )
    return {"session": _dump(session), "assistant_message": text}


async def interpret_node(state: TurnState) -> dict:
    session = _session(state)
    listing = _listing(state)
    user_text = state.get("user_message") or ""
    interp = interpret_message(user_text, session, listing)
    session.last_interpretation = interp
    session.sentiment = interp.sentiment
    facts = interp.extracted_facts or {}
    if isinstance(facts.get("counter_price"), int):
        session.current_vendor_offer = facts["counter_price"]
    tactic = select_tactic(interp, session, listing)
    situation = classify_situation(interp, session, listing)
    session.insight_log.append(
        InsightTurn(
            round_number=session.round_count,
            intent=interp.intent,
            sentiment=interp.sentiment,
            signal_confidence=interp.signal_confidence,
            tactic=tactic,
            situation=situation,
            reasoning=None,
            extracted_facts=facts,
            timestamp=datetime.now(timezone.utc),
        )
    )
    return {
        "session": _dump(session),
        "interpretation": interp.model_dump(),
        "tactic": tactic,
        "interpreted_intent": interp.intent,
    }


async def qualify_node(state: TurnState) -> dict:
    session = _session(state)
    listing = _listing(state)
    user_text = state.get("user_message") or ""
    session = apply_qualification(session, user_text)
    if looks_like_contact_refusal(user_text) or (
        session.contact_refusal_count >= 1 and is_bare_decline(user_text)
    ):
        session.contact_refusal_count += 1

    proceed = is_qualified(session) or can_proceed_without_contact(session)
    if not proceed:
        lighter = session.contact_refusal_count >= 1
        instruction = (
            "They declined phone/email. Say that's fine once. Name and company is enough; contact can wait for the PO. "
            "Do not state a bid. 1-3 short sentences."
            if lighter
            else (
                "Still missing name or a phone/email. Ask only for that, plainly. Do not discuss a bid. "
                "Do not reconfirm quote, quantity, lead time, or terms."
            )
        )
        text = await _phrase(
            session=session,
            listing=listing,
            fallback=_missing_qualify_prompt(session, listing),
            authorized=None,
            instruction=instruction,
            state=state,
        )
        return {"session": _dump(session), "assistant_message": text}

    if not is_qualified(session):
        session.contact_followup_required = True

    from app.db.postgres import persist_lead

    await persist_lead(session)
    session.stage = NegotiationStage.PRICE_ELIGIBILITY_CHECK
    return {"session": _dump(session), "assistant_message": state.get("assistant_message") or ""}


async def eligibility_node(state: TurnState) -> dict:
    session = _session(state)
    listing = _listing(state)
    eligible, reason = check_order_eligibility(listing)
    if not eligible:
        session.stage = NegotiationStage.HANDOFF
        session.handoff_flag = True
        session.handoff_reason = reason
        return {"session": _dump(session)}
    session.stage = NegotiationStage.OPEN_OFFER
    return {"session": _dump(session)}


def _competitive_line(listing: PartListing, *, include: bool = True) -> str:
    if not include:
        return ""
    alt = best_alternate_unit_price(listing)
    if alt is None:
        return ""
    return f" We've got another quote at {format_inr(alt)}."


def _digits(text: str) -> str:
    return re.sub(r"[^\d]", "", text or "")


def _alt_already_cited(state: TurnState, listing: PartListing) -> bool:
    alt = best_alternate_unit_price(listing)
    if alt is None:
        return False
    needle = str(alt)
    for turn in state.get("transcript") or []:
        if needle in _digits(turn.get("content") or ""):
            return True
    if needle in _digits(state.get("assistant_message") or ""):
        return True
    return False


def _offer_from_facts(facts: dict | None) -> dict:
    facts = facts or {}
    price = facts.get("counter_price")
    return {
        "unit_price": price if isinstance(price, int) else None,
        "moq": facts.get("moq_requested"),
        "lead_time_days": facts.get("lead_time_requested"),
        "payment_terms": facts.get("payment_terms_requested"),
    }


def _commit_acceptance(session: NegotiationSession, offer: dict) -> None:
    price = offer["unit_price"]
    session.current_vendor_offer = price
    session.current_bot_offer = price
    session.authorized_offer = price
    if offer.get("payment_terms"):
        session.payment_terms = offer["payment_terms"]
    if offer.get("lead_time_days") is not None:
        session.current_lead_time_days = offer["lead_time_days"]
    if offer.get("moq") is not None:
        session.current_moq = offer["moq"]
    session.stage = NegotiationStage.AGREEMENT


def _try_accept_offer(
    session: NegotiationSession,
    listing: PartListing,
    interp: Interpretation,
    offer: dict,
) -> bool:
    confidence = interp.signal_confidence if interp is not None else None
    if should_accept(offer, listing, session=session, signal_confidence=confidence):
        _commit_acceptance(session, offer)
        return True
    if offer_in_envelope(offer, listing):
        session.in_range_push_done = True
    return False


async def open_offer_node(state: TurnState) -> dict:
    session = _session(state)
    listing = _listing(state)
    interp = _interpretation(state, session)
    offer = _offer_from_facts(interp.extracted_facts)
    if _try_accept_offer(session, listing, interp, offer):
        return {"session": _dump(session)}

    tactic = "anchoring_hold"
    anchor = compute_anchor(listing)
    allowed, price, reason = validate_offer(anchor, session, listing)
    if not allowed:
        session.stage = NegotiationStage.HANDOFF
        session.handoff_flag = True
        session.handoff_reason = reason
        return {"session": _dump(session)}

    ok_total, _, total_reason = validate_order_total(price, listing.quantity)
    if not ok_total:
        session.stage = NegotiationStage.HANDOFF
        session.handoff_flag = True
        session.handoff_reason = total_reason
        return {"session": _dump(session)}

    turn = await _complete(
        session,
        listing,
        state,
        hints={
            "stage": "open_offer",
            "authorized_offer": price,
            "selected_tactic": tactic,
            "interpreted_intent": interp.intent,
            "signal_confidence": interp.signal_confidence,
        },
        interpretation=interp,
        tactic=tactic,
    )
    reasoning = ""
    intent = interp.intent
    if turn.tool_calls:
        call = turn.tool_calls[0]
        if call.name == "propose_price":
            proposed = int(call.input["price"])
            reasoning, intent, tactic = _tool_reasoning(call.input, interp, tactic)
            allowed, price, reason = validate_offer(proposed, session, listing)
            if not allowed:
                session.stage = NegotiationStage.HANDOFF
                session.handoff_flag = True
                session.handoff_reason = reason
                return {"session": _dump(session)}

    session.anchor_price = price
    session.current_bot_offer = price
    session.authorized_offer = price
    session.current_vendor_offer = listing.vendor_quoted_unit_price
    session.payment_terms = session.payment_terms or listing.payment_terms_default
    session.current_lead_time_days = session.current_lead_time_days or listing.lead_time_days
    session.current_moq = session.current_moq if session.current_moq is not None else listing.moq
    session.stage = NegotiationStage.NEGOTIATE
    _update_last_insight(session, tactic=tactic, reasoning=reasoning or None)
    first = (session.vendor_rep_name or "there").split()[0]
    cite_alt = not _alt_already_cited(state, listing)
    if session.contact_followup_required:
        fallback = (
            "We can start without a phone or email — we'll pick up contact before a PO. "
            f"Your quote is {format_inr(listing.vendor_quoted_unit_price)}."
            f"{_competitive_line(listing, include=cite_alt)} "
            f"We can do {format_inr(price)}. What would close this?"
        )
    else:
        fallback = (
            f"Thanks {first}. Your quote is {format_inr(listing.vendor_quoted_unit_price)}."
            f"{_competitive_line(listing, include=cite_alt)} "
            f"We can do {format_inr(price)}. What would close this?"
        )
    followup_note = (
        "Desk contact was declined; proceed into pricing anyway. You MUST state the authorized bid. "
        "One clause that sourcing will collect contact before a PO is enough — do not refuse to bid or re-open qualify."
        if session.contact_followup_required
        else ""
    )
    if session.contact_followup_required:
        await _emit(fallback)
        text = fallback
    else:
        text = await _phrase(
            session=session,
            listing=listing,
            fallback=fallback,
            authorized=price,
            instruction=(
                f"Say the authorized bid of exactly {format_inr(price)} per unit (tactic: {tactic}). "
                f"You may mention the vendor quote {format_inr(listing.vendor_quoted_unit_price)}. "
                f"{followup_note} "
                "Anchor low. Do not bid higher. Ask one simple question. Never mention your internal reasoning. 1-3 sentences."
            ),
            state=state,
            interpretation=interp,
            tactic=tactic,
        )
    return {
        "session": _dump(session),
        "assistant_message": text,
        "validated_price": price,
        "tactic": tactic,
        "reasoning": reasoning or None,
        "interpreted_intent": intent,
    }


async def negotiate_node(state: TurnState) -> dict:
    session = _session(state)
    listing = _listing(state)
    user_text = state.get("user_message") or ""
    interp = _interpretation(state, session)
    tactic = state.get("tactic") or select_tactic(interp, session, listing)

    if detect_hostile_language(user_text):
        session.stage = NegotiationStage.HANDOFF
        session.handoff_flag = True
        session.handoff_reason = "aggressive_language"
        session.sentiment = "aggressive"
        return {"session": _dump(session)}

    if re.search(r"\b(human|manager|person|sourcing|someone real)\b", user_text, re.I) and re.search(
        r"\b(talk|speak|connect|transfer|real|call me|want to)\b", user_text, re.I
    ):
        session.stage = NegotiationStage.HANDOFF
        session.handoff_flag = True
        session.handoff_reason = "vendor_requested_human"
        return {"session": _dump(session)}

    session = apply_qualification(session, user_text)
    facts = interp.extracted_facts or {}
    vendor_offer = facts.get("counter_price")
    if isinstance(vendor_offer, int):
        session.current_vendor_offer = vendor_offer

    offer = _offer_from_facts(facts)
    ceiling_reason = package_ceiling_reason(
        listing,
        unit_price=offer.get("unit_price") if isinstance(offer.get("unit_price"), int) else None,
        moq=offer.get("moq") if isinstance(offer.get("moq"), int) else None,
        session=session,
    )
    if ceiling_reason:
        session.stage = NegotiationStage.HANDOFF
        session.handoff_flag = True
        session.handoff_reason = ceiling_reason
        return {"session": _dump(session)}

    if _try_accept_offer(session, listing, interp, offer):
        return {"session": _dump(session)}

    rejecting = interp.intent in {"rejection", "objection_price"}
    if (
        isinstance(vendor_offer, int)
        and vendor_offer <= session.current_bot_offer
        and not rejecting
    ):
        allowed, price, reason = validate_offer(vendor_offer, session, listing)
        if allowed:
            session.current_bot_offer = price
            session.stage = NegotiationStage.AGREEMENT
            return {"session": _dump(session)}
        session.stage = NegotiationStage.HANDOFF
        session.handoff_flag = True
        session.handoff_reason = reason
        return {"session": _dump(session)}
    if interp.intent == "acceptance" or (
        looks_like_acceptance(user_text) and vendor_offer is None
    ):
        session.stage = NegotiationStage.AGREEMENT
        return {"session": _dump(session)}

    if session.round_count >= session.max_rounds:
        session.stage = NegotiationStage.HANDOFF
        session.handoff_flag = True
        session.handoff_reason = "max_rounds_reached"
        return {"session": _dump(session)}

    authorized = authorized_price_for_tactic(session, listing, tactic)
    near_ceiling = authorized == listing.max_acceptable_unit_price or authorized == session.current_bot_offer
    turn = await _complete(
        session,
        listing,
        state,
        hints={
            "stage": "negotiate",
            "authorized_offer": authorized,
            "near_ceiling": near_ceiling,
            "selected_tactic": tactic,
            "interpreted_intent": interp.intent,
            "signal_confidence": interp.signal_confidence,
        },
        interpretation=interp,
        tactic=tactic,
    )

    proposed = authorized
    reasoning = ""
    intent = interp.intent
    for call in turn.tool_calls:
        if call.name == "escalate_to_human":
            # Engine decides accept / continue / handoff. The model must not invent a limit.
            continue
        if call.name == "propose_price":
            reasoning, intent, tool_tactic = _tool_reasoning(call.input, interp, tactic)
            if tactic in HOLD_PRICE_TACTICS:
                proposed = authorized
            else:
                tactic = tool_tactic
                proposed = int(call.input["price"])

    allowed, price, reason = validate_offer(proposed, session, listing)
    if not allowed:
        session.stage = NegotiationStage.HANDOFF
        session.handoff_flag = True
        session.handoff_reason = reason
        return {"session": _dump(session)}

    eff_qty = effective_order_quantity(
        listing,
        moq=facts.get("moq_requested") if isinstance(facts.get("moq_requested"), int) else None,
        session=session,
    )
    ok_total, _, total_reason = validate_order_total(price, eff_qty)
    if not ok_total:
        session.stage = NegotiationStage.HANDOFF
        session.handoff_flag = True
        session.handoff_reason = total_reason
        return {"session": _dump(session)}

    trade_clause = _apply_trade(session, listing, interp, tactic)
    stated_vendor_offer = vendor_offer if isinstance(vendor_offer, int) else None
    session.round_count += 1
    session.current_bot_offer = price
    session.authorized_offer = price
    session.concession_history.append(
        ConcessionEvent(
            round_number=session.round_count,
            vendor_offer=stated_vendor_offer,
            bot_offer=price,
            justification_tactic=tactic,
            timestamp=datetime.now(timezone.utc),
            reasoning=reasoning or None,
            interpreted_intent=intent,
            lead_time_days=session.current_lead_time_days,
            payment_terms=session.payment_terms,
            moq=session.current_moq,
        )
    )
    _update_last_insight(session, tactic=tactic, reasoning=reasoning or None)
    if stated_vendor_offer is not None and detect_impasse(session):
        session.stage = NegotiationStage.HANDOFF
        session.handoff_flag = True
        session.handoff_reason = "impasse"
        return {"session": _dump(session), "reasoning": reasoning or None, "interpreted_intent": intent, "tactic": tactic}

    cite_alt = not _alt_already_cited(state, listing)
    fallback = _fallback_for_tactic(
        tactic=tactic,
        interpretation=interp,
        price=price,
        listing=listing,
        session=session,
        trade_clause=trade_clause,
        cite_alternate=cite_alt,
    )
    skip_alt = "" if cite_alt else " Do not mention the alternate vendor quote again; it was already cited."
    text = await _phrase(
        session=session,
        listing=listing,
        fallback=fallback,
        authorized=price,
        instruction=(
            f"The engine authorized a bid of exactly {format_inr(price)} per unit (tactic: {tactic}, "
            f"intent: {intent}). Address the interpreted objection. "
            f"{'Trade: ' + trade_clause + '. ' if trade_clause else ''}"
            f"{skip_alt} "
            "A short rejection like 'no' is not an impasse — keep negotiating or trade terms. "
            "Do not call escalate_to_human. Do not mention authorization limits. "
            "Do not bid higher. Never mention or paraphrase your internal reasoning. 1-3 short sentences."
        ),
        state=state,
        interpretation=interp,
        tactic=tactic,
    )
    return {
        "session": _dump(session),
        "assistant_message": text,
        "validated_price": price,
        "tactic": tactic,
        "reasoning": reasoning or None,
        "interpreted_intent": intent,
    }


async def agreement_node(state: TurnState) -> dict:
    session = _session(state)
    listing = _listing(state)
    price = session.current_bot_offer
    qty = listing.quantity
    if session.current_moq and session.current_moq > qty:
        qty = session.current_moq
    total = order_total(price, qty)
    contact = session.vendor_rep_contact or "the desk you shared"
    terms = session.payment_terms or listing.payment_terms_default
    lead = session.current_lead_time_days or listing.lead_time_days
    fallback = (
        f"We're on {format_inr(price)} per unit for {qty} pieces "
        f"({format_inr(total)} total), {terms}, {lead} days. "
        f"Someone on sourcing will send the PO to {contact}."
    )
    text = await _phrase(
        session=session,
        listing=listing,
        fallback=fallback,
        authorized=price,
        instruction=(
            f"The engine accepted {format_inr(price)} per unit. Confirm the line in plain words. "
            "A human issues the PO. Do not reopen negotiation or mention an authorization limit. 1-3 sentences."
        ),
        state=state,
    )
    session.stage = NegotiationStage.CLOSED
    try:
        record_lesson(session, listing)
    except Exception:
        logger.exception("strategy lesson write failed")
    return {
        "session": _dump(session),
        "assistant_message": text,
        "validated_price": price,
    }


async def handoff_node(state: TurnState) -> dict:
    session = _session(state)
    listing = _listing(state)
    reason = session.handoff_reason or "vendor_requested_human"
    sla = _settings().handoff_sla
    session.handoff_flag = True
    session.stage = NegotiationStage.HANDOFF
    if reason == "above_10L_ceiling":
        quoted_total = order_total(listing.vendor_quoted_unit_price, listing.quantity)
        if quoted_total > CEILING:
            fallback = (
                f"This {listing.part_name} line totals {format_inr(quoted_total)} — that's above our ₹10,00,000 sign-off. "
                f"A sourcing manager will take it from here, within {sla}."
            )
        else:
            fallback = (
                f"That package on {listing.part_name} would take the order over ₹10,00,000. "
                f"A sourcing manager will take it from here, within {sla}."
            )
    elif reason == "impasse":
        fallback = (
            f"We're circling the same number, and I shouldn't grind this. A sourcing manager will pick up "
            f"{listing.part_name} within {sla}."
        )
    elif reason == "aggressive_language":
        fallback = (
            f"I'll hand this to a colleague so we stay useful. A sourcing manager will continue within {sla}."
        )
    elif reason == "max_rounds_reached":
        fallback = (
            f"I've taken this as far as I'm authorized to go in chat. A sourcing manager will pick up the thread "
            f"within {sla}."
        )
    else:
        fallback = (
            f"I'm handing this to a sourcing manager so you get a human on the desk. They'll reach you within {sla}."
        )

    transcript = list(state.get("transcript") or [])
    await execute_handoff(session, reason, transcript)
    if reason == "above_10L_ceiling":
        # Hard gate — do not let the model substitute a unit price for ₹10,00,000.
        await _emit(fallback)
        text = fallback
    else:
        text = await _phrase(
            session=session,
            listing=listing,
            fallback=fallback,
            authorized=None,
            instruction=(
                f"Handoff reason: {reason}. Tell them what happens next and by when ({sla}), in plain words. "
                "Do not keep negotiating or state a new bid. 1-3 short sentences."
            ),
            state=state,
        )
    try:
        record_lesson(session, listing)
    except Exception:
        logger.exception("strategy lesson write failed")
    return {"session": _dump(session), "assistant_message": text}


def after_interpret(state: TurnState) -> str:
    stage = state["session"]["stage"]
    if stage == NegotiationStage.QUALIFY.value:
        return "qualify"
    if stage == NegotiationStage.NEGOTIATE.value:
        return "negotiate"
    return "end"


def after_qualify(state: TurnState) -> str:
    if state["session"]["stage"] == NegotiationStage.PRICE_ELIGIBILITY_CHECK.value:
        return "eligibility"
    return "end"


def after_eligibility(state: TurnState) -> str:
    if state["session"]["stage"] == NegotiationStage.HANDOFF.value:
        return "handoff"
    return "open_offer"


def after_open(state: TurnState) -> str:
    if state["session"]["stage"] == NegotiationStage.HANDOFF.value:
        return "handoff"
    if state["session"]["stage"] == NegotiationStage.AGREEMENT.value:
        return "agreement"
    return "end"


def after_negotiate(state: TurnState) -> str:
    stage = state["session"]["stage"]
    if stage == NegotiationStage.HANDOFF.value:
        return "handoff"
    if stage == NegotiationStage.AGREEMENT.value:
        return "agreement"
    return "end"
