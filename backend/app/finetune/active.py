"""Promoted chat-model pointer. Never stores secrets."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "data" / "finetune" / "active_model.json"


def active_path() -> Path:
    return _PATH


def load_active(*, path: Path | None = None) -> dict:
    dest = path or _PATH
    if not dest.exists():
        return {}
    try:
        payload = json.loads(dest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def resolved_chat_model(fallback: str, *, path: Path | None = None) -> str:
    model = str(load_active(path=path).get("chat_model") or "").strip()
    return model or fallback


def promote(model: str, *, job_id: str | None = None, path: Path | None = None) -> dict:
    dest = path or _PATH
    row = {
        "chat_model": model,
        "job_id": job_id,
        "promoted_at": datetime.now(timezone.utc).isoformat(),
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(row, indent=2), encoding="utf-8")
    return row
