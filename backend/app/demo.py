"""Live vendor-bot replies for the on-screen Test / client demo."""

from __future__ import annotations

from app.catalog import get_part
from app.harness.personas import PRESETS, VendorPreset, vendor_system_prompt
from app.llm.provider import LLMProvider
from app.models import PartListing

_QUEUES: dict[str, list[str]] = {}

_DEFAULT_PERSONA = {
    "headlight-lh": "cooperative",
    "chassis-frame-front": "over_ceiling",
    "rear-subframe": "ceiling_boundary",
    "wiring-harness-cabin": "vague",
}


def generic_vendor_preset(listing: PartListing) -> VendorPreset:
    walk = max(1, int(listing.vendor_quoted_unit_price * 0.88))
    return VendorPreset(
        id="live_demo",
        label="Vendor desk",
        part_id=listing.part_id,
        walk_away_min=walk,
        tone="professional, short, human",
        move_rate="reasonable — you can close in a few turns if the buyer is serious",
        qualify_replies=(
            f"I'm Ravi, ravi@{listing.vendor_id}.example, we can talk this quarter.",
        ),
        extra_rules=(
            "Talk like a real sales rep on chat. Short sentences. You want the deal. "
            "Come down in visible steps toward your floor when they offer a real number or a trade. "
            "Never invent SKODA's ceiling."
        ),
    )


def resolve_preset(part_id: str, persona: str | None = None) -> VendorPreset:
    listing = get_part(part_id)
    if listing is None:
        raise KeyError(part_id)
    if persona and persona in PRESETS and PRESETS[persona].part_id == part_id:
        return PRESETS[persona]
    preferred = _DEFAULT_PERSONA.get(part_id)
    if preferred and preferred in PRESETS:
        return PRESETS[preferred]
    return generic_vendor_preset(listing)


def remaining_script(session_id: str, preset: VendorPreset) -> list[str]:
    if session_id not in _QUEUES:
        _QUEUES[session_id] = list(preset.qualify_replies) + list(preset.scripted_replies)
    return _QUEUES[session_id]


async def next_vendor_reply(
    *,
    provider: LLMProvider,
    session_id: str,
    listing: PartListing,
    transcript: list[dict],
    persona: str | None = None,
) -> tuple[str, VendorPreset]:
    preset = resolve_preset(listing.part_id, persona)
    queued = remaining_script(session_id, preset)
    if queued:
        return queued.pop(0), preset

    system = vendor_system_prompt(
        preset,
        part_name=listing.part_name,
        vendor_name=listing.vendor_name,
        opening_quote=listing.vendor_quoted_unit_price,
        quantity=listing.quantity,
        lead_time_days=listing.lead_time_days,
        payment_terms=listing.payment_terms_default,
        moq=listing.moq,
    )
    messages: list[dict[str, str]] = []
    for turn in transcript:
        role = turn.get("role")
        content = (turn.get("content") or "").strip()
        if not content:
            continue
        if role == "assistant":
            messages.append({"role": "user", "content": content})
        elif role == "user":
            messages.append({"role": "assistant", "content": content})
    if not messages:
        messages = [{"role": "user", "content": "Who am I talking to?"}]
    chunks: list[str] = []
    async for token in provider.stream_text(system=system, messages=messages):
        chunks.append(token)
    text = "".join(chunks).strip()
    return text or "What number can you actually do?", preset
