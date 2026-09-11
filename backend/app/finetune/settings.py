"""Runtime fine-tune config. Overlay file wins over .env. No secrets."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.paths import finetune_dir

_PATH = finetune_dir() / "settings.json"

ALLOWED_BASE_MODELS = (
    "gpt-4o-mini",
    "gpt-4.1-mini",
    "gpt-4o",
)
_BLOCKED_BASE = ("o4-mini", "o3-mini", "o3", "o1", "o1-mini")
_OPENAI_FLOOR = 10
_MAX_EXAMPLES = 2000
_SUFFIX_RE = re.compile(r"^[a-zA-Z0-9-]{1,18}$")


def settings_path() -> Path:
    return _PATH


def openai_example_floor() -> int:
    return _OPENAI_FLOOR


def quality_band(min_examples: int) -> str:
    if min_examples < _OPENAI_FLOOR:
        return "below_floor"
    if min_examples < 50:
        return "thin"
    if min_examples < 100:
        return "workable"
    return "solid"


def guidance(min_examples: int, train_examples: int = 0) -> dict[str, Any]:
    band = quality_band(min_examples)
    notes = {
        "below_floor": (
            "OpenAI supervised chat fine-tunes need at least 10 examples. "
            "A job under that floor is rejected."
        ),
        "thin": (
            "20 examples is enough to start a job, not enough for a reliable voice lift. "
            "Treat this as a smoke run. Prefer 50–100+ clean turns before you care about the result."
        ),
        "workable": (
            "50–99 clean examples is the first range where spoken style usually starts to move."
        ),
        "solid": (
            "100+ clean examples is a serious first fine-tune. 200+ is better if the desks stay clean."
        ),
    }
    return {
        "band": band,
        "openai_floor": _OPENAI_FLOOR,
        "note": notes[band],
        "have": train_examples,
        "need": min_examples,
    }


def _read(path: Path | None = None) -> dict[str, Any]:
    dest = path or _PATH
    if not dest.exists():
        return {}
    try:
        payload = json.loads(dest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def env_defaults() -> dict[str, Any]:
    settings = get_settings()
    return {
        "auto": bool(settings.openai_finetune_auto),
        "base_model": (settings.openai_finetune_base or "gpt-4o-mini").strip(),
        "min_examples": int(settings.openai_finetune_min_examples),
        "suffix": "aria-voice",
        "n_epochs": None,
        "auto_promote": True,
        "tick_seconds": 90,
    }


def _clean_base(value: str, fallback: str) -> str:
    model = (value or fallback or "gpt-4o-mini").strip()
    lowered = model.lower()
    if any(blocked in lowered for blocked in _BLOCKED_BASE):
        raise ValueError("Reasoning models cannot be fine-tuned. Use gpt-4o-mini for voice.")
    if model not in ALLOWED_BASE_MODELS:
        raise ValueError(f"Base must be one of: {', '.join(ALLOWED_BASE_MODELS)}")
    return model


def resolved(*, path: Path | None = None) -> dict[str, Any]:
    defaults = env_defaults()
    overlay = _read(path)
    min_examples = int(overlay.get("min_examples", defaults["min_examples"]))
    base = str(overlay.get("base_model", defaults["base_model"]))
    try:
        base = _clean_base(base, defaults["base_model"])
    except ValueError:
        base = "gpt-4o-mini"
    suffix = str(overlay.get("suffix", defaults["suffix"]) or "aria-voice")
    n_epochs = overlay.get("n_epochs", defaults["n_epochs"])
    if n_epochs in ("", "auto"):
        n_epochs = None
    if n_epochs is not None:
        n_epochs = int(n_epochs)
    tick_seconds = int(overlay.get("tick_seconds", defaults["tick_seconds"]))
    return {
        "auto": bool(overlay.get("auto", defaults["auto"])),
        "base_model": base,
        "min_examples": max(1, min_examples),
        "suffix": suffix,
        "n_epochs": n_epochs,
        "auto_promote": bool(overlay.get("auto_promote", defaults["auto_promote"])),
        "tick_seconds": max(15, min(tick_seconds, 3600)),
        "allowed_base_models": list(ALLOWED_BASE_MODELS),
        "openai_floor": _OPENAI_FLOOR,
        "source": "overlay" if overlay else "env",
        "updated_at": overlay.get("updated_at"),
        "guidance": guidance(max(1, min_examples)),
    }


def apply_patch(patch: dict[str, Any], *, path: Path | None = None, enforce_floor: bool = True) -> dict[str, Any]:
    current = {**_read(path), **{k: v for k, v in resolved(path=path).items() if k not in {
        "allowed_base_models", "openai_floor", "source", "updated_at", "guidance"
    }}}
    if "auto" in patch and patch["auto"] is not None:
        current["auto"] = bool(patch["auto"])
    if "auto_promote" in patch and patch["auto_promote"] is not None:
        current["auto_promote"] = bool(patch["auto_promote"])
    if patch.get("base_model"):
        current["base_model"] = _clean_base(str(patch["base_model"]), current["base_model"])
    if patch.get("suffix") is not None:
        suffix = str(patch["suffix"]).strip() or "aria-voice"
        if not _SUFFIX_RE.match(suffix):
            raise ValueError("Suffix must be 1–18 letters, numbers, or hyphens.")
        current["suffix"] = suffix
    if "min_examples" in patch and patch["min_examples"] is not None:
        n = int(patch["min_examples"])
        if enforce_floor and n < _OPENAI_FLOOR:
            raise ValueError(f"OpenAI needs at least {_OPENAI_FLOOR} examples.")
        if n > _MAX_EXAMPLES:
            raise ValueError(f"Min examples cannot exceed {_MAX_EXAMPLES}.")
        if n < 1:
            raise ValueError("Min examples must be at least 1.")
        current["min_examples"] = n
    if "n_epochs" in patch:
        value = patch["n_epochs"]
        if value in (None, "", "auto"):
            current["n_epochs"] = None
        else:
            epochs = int(value)
            if epochs < 1 or epochs > 10:
                raise ValueError("Epochs must be auto or 1–10.")
            current["n_epochs"] = epochs
    if "tick_seconds" in patch and patch["tick_seconds"] is not None:
        seconds = int(patch["tick_seconds"])
        if seconds < 15 or seconds > 3600:
            raise ValueError("Tick interval must be 15–3600 seconds.")
        current["tick_seconds"] = seconds
    current["updated_at"] = datetime.now(timezone.utc).isoformat()
    dest = path or _PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return resolved(path=dest)
