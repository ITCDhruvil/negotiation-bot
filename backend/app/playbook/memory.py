"""Short lessons from closed desks — retrieved on later similar situations."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.models import NegotiationSession, NegotiationStage, PartListing

_LOCK = threading.Lock()
_PATH = Path(__file__).resolve().parents[2] / "data" / "strategy_lessons.json"
_MAX_STORED = 80
_MAX_RETRIEVE = 3

_TERMINAL_CLOSE = {NegotiationStage.CLOSED, NegotiationStage.AGREEMENT}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def lessons_path() -> Path:
    return _PATH


def _read(path: Path | None = None) -> list[dict[str, Any]]:
    target = path or _PATH
    if not target.exists():
        return []
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def _write(rows: list[dict[str, Any]], path: Path | None = None) -> None:
    target = path or _PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(rows[-_MAX_STORED:], ensure_ascii=False, indent=2), encoding="utf-8")


def _dominant_situation(session: NegotiationSession) -> str:
    tagged = [item.situation for item in session.insight_log if getattr(item, "situation", None)]
    return tagged[-1] if tagged else "price_fight"


def _what_worked(session: NegotiationSession, outcome: str) -> str:
    tactics = [event.justification_tactic for event in session.concession_history if event.justification_tactic]
    if not tactics:
        return "qualify-only desk"
    last = tactics[-1]
    unique = []
    for tactic in tactics:
        if tactic not in unique:
            unique.append(tactic)
    if outcome == "closed":
        return f"closed after {last}; sequence {' → '.join(unique)}"
    reason = session.handoff_reason or "handoff"
    return f"handoff ({reason}); last move {last}; sequence {' → '.join(unique)}"


def record_lesson(
    session: NegotiationSession,
    listing: PartListing,
    *,
    path: Path | None = None,
) -> dict[str, Any] | None:
    """Store a public outcome. Never writes walk-away or target."""
    if session.stage not in _TERMINAL_CLOSE and not session.handoff_flag:
        return None
    outcome = "closed" if session.stage in _TERMINAL_CLOSE else "handoff"
    row = {
        "id": str(uuid4()),
        "part_id": listing.part_id,
        "part_name": listing.part_name,
        "vendor_name": listing.vendor_name,
        "situation": _dominant_situation(session),
        "outcome": outcome,
        "handoff_reason": session.handoff_reason if outcome == "handoff" else None,
        "final_price": session.current_bot_offer,
        "opening_quote": listing.vendor_quoted_unit_price,
        "rounds": session.round_count,
        "tactics": [event.justification_tactic for event in session.concession_history],
        "note": _what_worked(session, outcome),
        "session_id": session.session_id,
        "created_at": _now(),
    }
    with _LOCK:
        rows = _read(path)
        rows.append(row)
        _write(rows, path)
    try:
        from app.db.audit import log_lesson

        log_lesson(row)
    except Exception:
        pass
    try:
        from app.finetune.submit import maybe_auto_submit

        maybe_auto_submit()
    except Exception:
        pass
    return row


def retrieve_lessons(
    part_id: str,
    situation: str,
    *,
    path: Path | None = None,
    limit: int = _MAX_RETRIEVE,
) -> list[dict[str, Any]]:
    rows = _read(path)
    try:
        from app.db.audit import fetch_lessons as fetch_audit_lessons

        for extra in fetch_audit_lessons(part_id=part_id, situation=situation, limit=20):
            if extra.get("id") and extra["id"] not in {row.get("id") for row in rows}:
                rows.append(extra)
    except Exception:
        pass
    scored: list[tuple[int, dict[str, Any]]] = []
    for row in rows:
        score = 0
        if row.get("situation") == situation:
            score += 3
        if row.get("part_id") == part_id:
            score += 2
        if score:
            scored.append((score, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    seen: set[str] = set()
    picked: list[dict[str, Any]] = []
    for _, row in scored:
        key = str(row.get("id") or "")
        if key in seen:
            continue
        seen.add(key)
        picked.append(row)
        if len(picked) >= limit:
            break
    return picked


def format_lessons(rows: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for row in rows:
        part = row.get("part_name") or row.get("part_id") or "this part"
        vendor = row.get("vendor_name") or "a vendor"
        note = row.get("note") or row.get("outcome")
        quote = row.get("opening_quote")
        final = row.get("final_price")
        money = ""
        if isinstance(quote, int) and isinstance(final, int) and row.get("outcome") == "closed":
            money = f" Opened at ₹{quote:,}, closed at ₹{final:,}."
        lines.append(f"- {part} vs {vendor}: {note}.{money}")
    return "\n".join(lines)
