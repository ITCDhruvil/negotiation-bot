"""Writable vs packaged data paths.

On Vercel the deployment filesystem is read-only except /tmp. Seed JSON
(mock catalog) stays in the package; SQLite and overlays go under /tmp.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_PACKAGED_DATA = _BACKEND_ROOT / "data"


@lru_cache
def on_vercel() -> bool:
    return os.environ.get("VERCEL") == "1"


def packaged_data_dir() -> Path:
    return _PACKAGED_DATA


@lru_cache
def writable_data_dir() -> Path:
    if on_vercel():
        root = Path(os.environ.get("TMPDIR") or "/tmp") / "aria"
    else:
        root = _PACKAGED_DATA
    root.mkdir(parents=True, exist_ok=True)
    return root


def audit_db_path() -> Path:
    return writable_data_dir() / "aria_audit.db"


def finetune_dir() -> Path:
    dest = writable_data_dir() / "finetune"
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def user_rfqs_path() -> Path:
    return writable_data_dir() / "user_rfqs.json"


def strategy_lessons_path() -> Path:
    return writable_data_dir() / "strategy_lessons.json"
