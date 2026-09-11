"""Auto-label closed desks so only clean, tagged examples enter training."""

from __future__ import annotations

from typing import Any

from app.catalog import get_part
from app.db.audit import fetch_turns, list_sessions, upsert_label
from app.harness.score import leaked_buyer_walkaway

_BANNED = (
    "ai assistant",
    "on behalf of",
    "could you please",
    "thank you for your patience",
    "looking forward",
)
_LEAK_WORDS = ("walk-away", "walk away", "authorization limit", "max acceptable")


def session_is_safe(turns: list[dict[str, Any]], part_id: str | None) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    aria = [str(row.get("content") or "") for row in turns if row.get("role") == "assistant"]
    vendor = [str(row.get("content") or "") for row in turns if row.get("role") == "user"]
    listing = get_part(part_id) if part_id else None
    walk = listing.max_acceptable_unit_price if listing else None
    if leaked_buyer_walkaway(aria, walk, vendor):
        reasons.append("leaked_walkaway")
    blob = " ".join(aria).lower()
    if any(word in blob for word in _LEAK_WORDS):
        reasons.append("named_ceiling")
    if listing and str(listing.target_unit_price) in blob and "target" in blob:
        reasons.append("named_target")
    if any(phrase in blob for phrase in _BANNED):
        reasons.append("persona_banned")
    return (not reasons), reasons


def label_session(
    session_id: str,
    *,
    part_id: str | None,
    stage: str | None,
    turns: list[dict[str, Any]] | None = None,
    audit_path=None,
) -> dict[str, Any]:
    turns = turns if turns is not None else fetch_turns(session_id, path=audit_path)
    reasons: list[str] = []
    quality = "train"
    if stage != "closed":
        quality = "reject"
        reasons.append("not_closed")
    if len(turns) < 3:
        quality = "reject"
        reasons.append("too_short")
    safe, leak_reasons = session_is_safe(turns, part_id)
    if not safe:
        quality = "reject"
        reasons.extend(leak_reasons)
    aria = [row for row in turns if row.get("role") == "assistant"]
    vendor = [row for row in turns if row.get("role") == "user"]
    if quality == "train" and not vendor:
        quality = "reject"
        reasons.append("no_vendor_turns")
    if quality == "train" and not any((row.get("content") or "").strip() for row in aria):
        quality = "reject"
        reasons.append("no_aria_text")

    situations = []
    tactics = []
    for row in turns:
        if row.get("situation") and row["situation"] not in situations:
            situations.append(row["situation"])
        if row.get("tactic") and row["tactic"] not in tactics:
            tactics.append(row["tactic"])

    voice_n = sum(1 for row in aria if (row.get("content") or "").strip())
    brain_n = sum(1 for row in aria if row.get("validated_price") and (row.get("reasoning") or "").strip())
    record = {
        "session_id": session_id,
        "quality": quality,
        "outcome": stage,
        "reasons": reasons,
        "situations": situations,
        "tactics": tactics,
        "voice_examples": voice_n,
        "brain_examples": brain_n,
    }
    upsert_label(record, path=audit_path)
    return record


def label_all(*, audit_path=None) -> list[dict[str, Any]]:
    labeled: list[dict[str, Any]] = []
    for session in list_sessions(path=audit_path):
        labeled.append(
            label_session(
                session["session_id"],
                part_id=session.get("part_id"),
                stage=session.get("stage"),
                audit_path=audit_path,
            )
        )
    return labeled
