"""Build leak-safe JSONL from labeled audit rows only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.db.audit import fetch_turns, get_label, list_sessions
from app.finetune.labels import label_session
from app.llm.persona_prompt import render_persona_prompt

_OUT_DIR = Path(__file__).resolve().parents[2] / "data" / "finetune"
_BANNED = (
    "ai assistant",
    "on behalf of",
    "could you please",
    "thank you for your patience",
    "looking forward",
)
_LEAK_WORDS = ("walk-away", "walk away", "authorization limit", "max acceptable")


def _system_prompt() -> str:
    return render_persona_prompt(get_settings().company_name)


def _train_sessions(*, audit_path: Path | None = None) -> list[dict[str, Any]]:
    chosen: list[dict[str, Any]] = []
    for session in list_sessions(path=audit_path):
        label = get_label(session["session_id"], path=audit_path)
        if label is None:
            label = label_session(
                session["session_id"],
                part_id=session.get("part_id"),
                stage=session.get("stage"),
                audit_path=audit_path,
            )
        if label.get("quality") == "train":
            chosen.append(session)
    return chosen


def _voice_example(turns: list[dict[str, Any]], end: int) -> dict[str, Any] | None:
    slice_turns = turns[: end + 1]
    if slice_turns[-1].get("role") != "assistant":
        return None
    text = (slice_turns[-1].get("content") or "").strip()
    if not text:
        return None
    if any(phrase in text.lower() for phrase in _BANNED):
        return None
    messages = [{"role": "system", "content": _system_prompt()}]
    for row in slice_turns:
        role = row.get("role")
        content = (row.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    if len(messages) < 3:
        return None
    return {"messages": messages}


def _brain_example(turns: list[dict[str, Any]], index: int) -> dict[str, Any] | None:
    row = turns[index]
    if row.get("role") != "assistant":
        return None
    price = row.get("validated_price")
    reasoning = (row.get("reasoning") or "").strip()
    if not isinstance(price, int) or not reasoning:
        return None
    if any(word in reasoning.lower() for word in _LEAK_WORDS):
        return None
    messages = [{"role": "system", "content": _system_prompt()}]
    for prior in turns[:index]:
        role = prior.get("role")
        content = (prior.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    arguments = {
        "reasoning": reasoning,
        "interpreted_intent": row.get("interpreted_intent") or "counter_offer",
        "tactic": row.get("tactic") or "volume_commitment",
        "price": price,
    }
    messages.append(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": f"call_{index}",
                    "type": "function",
                    "function": {
                        "name": "propose_price",
                        "arguments": json.dumps(arguments, ensure_ascii=False),
                    },
                }
            ],
        }
    )
    return {"messages": messages}


def _split(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if len(rows) < 10:
        return rows, []
    hold = max(1, len(rows) // 10)
    return rows[:-hold], rows[-hold:]


def build_examples(*, audit_path: Path | None = None) -> dict[str, Any]:
    voice: list[dict[str, Any]] = []
    brain: list[dict[str, Any]] = []
    train_sessions = _train_sessions(audit_path=audit_path)
    train_ids = {row["session_id"] for row in train_sessions}
    skipped = sum(
        1
        for session in list_sessions(path=audit_path)
        if session.get("stage") == "closed" and session["session_id"] not in train_ids
    )
    for session in train_sessions:
        turns = fetch_turns(session["session_id"], path=audit_path)
        for index, row in enumerate(turns):
            if row.get("role") != "assistant":
                continue
            example = _voice_example(turns, index)
            if example:
                voice.append(example)
            brain_ex = _brain_example(turns, index)
            if brain_ex:
                brain.append(brain_ex)
    train_voice, valid_voice = _split(voice)
    return {
        "voice": voice,
        "brain": brain,
        "train_voice": train_voice,
        "valid_voice": valid_voice,
        "skipped": skipped,
        "train_sessions": [row["session_id"] for row in train_sessions],
    }


def preview_dataset(*, audit_path: Path | None = None) -> dict[str, Any]:
    built = build_examples(audit_path=audit_path)
    from app.db.audit import list_labels
    from app.finetune.settings import guidance, resolved

    cfg = resolved()
    counts: dict[str, int] = {}
    for row in list_labels(path=audit_path):
        quality = row.get("quality") or "unknown"
        counts[quality] = counts.get(quality, 0) + 1
    train_n = len(built["train_voice"])
    return {
        "closed_sessions": sum(1 for row in list_sessions(path=audit_path) if row.get("stage") == "closed"),
        "train_sessions": len(built["train_sessions"]),
        "voice_examples": len(built["voice"]),
        "train_examples": train_n,
        "valid_examples": len(built["valid_voice"]),
        "brain_examples": len(built["brain"]),
        "skipped_sessions": built["skipped"],
        "label_counts": counts,
        "min_examples": cfg["min_examples"],
        "base_model": cfg["base_model"],
        "auto": cfg["auto"],
        "ready": train_n >= cfg["min_examples"],
        "guidance": guidance(cfg["min_examples"], train_n),
        "note": (
            "Only sessions labeled train are exported. o4-mini is not fine-tuned; "
            "the job trains the configured voice base (default gpt-4o-mini)."
        ),
    }


def _write_jsonl(rows: list[dict[str, Any]], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def export_dataset(*, audit_path: Path | None = None, out_dir: Path | None = None) -> dict[str, Any]:
    dest = out_dir or _OUT_DIR
    built = build_examples(audit_path=audit_path)
    voice_path = _write_jsonl(built["train_voice"], dest / "voice.jsonl")
    valid_path = _write_jsonl(built["valid_voice"], dest / "voice_valid.jsonl")
    brain_path = _write_jsonl(built["brain"], dest / "brain.jsonl")
    preview = preview_dataset(audit_path=audit_path)
    preview.update(
        {
            "voice_path": str(voice_path),
            "valid_path": str(valid_path),
            "brain_path": str(brain_path),
        }
    )
    (dest / "manifest.json").write_text(json.dumps(preview, indent=2), encoding="utf-8")
    return preview
