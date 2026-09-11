"""Durable SKODA-side audit log.

Always writes to a local SQLite file so collection survives restarts even
when USE_IN_MEMORY skips Postgres. Never sent to the vendor.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models import NegotiationSession

_LOCK = threading.Lock()
_PATH = Path(__file__).resolve().parents[2] / "data" / "aria_audit.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    validated_price INTEGER,
    tactic TEXT,
    situation TEXT,
    reasoning TEXT,
    interpreted_intent TEXT,
    stage TEXT,
    model TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    round_number INTEGER,
    intent TEXT,
    sentiment TEXT,
    signal_confidence TEXT,
    tactic TEXT,
    situation TEXT,
    reasoning TEXT,
    extracted_facts TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lessons (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    part_id TEXT,
    part_name TEXT,
    vendor_name TEXT,
    situation TEXT,
    outcome TEXT,
    handoff_reason TEXT,
    final_price INTEGER,
    opening_quote INTEGER,
    rounds INTEGER,
    tactics TEXT,
    note TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS session_snapshots (
    session_id TEXT PRIMARY KEY,
    part_id TEXT,
    stage TEXT,
    payload TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS labels (
    session_id TEXT PRIMARY KEY,
    quality TEXT NOT NULL,
    outcome TEXT,
    reasons TEXT,
    situations TEXT,
    tactics TEXT,
    voice_examples INTEGER DEFAULT 0,
    brain_examples INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ft_jobs (
    job_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    base_model TEXT,
    fine_tuned_model TEXT,
    fingerprint TEXT,
    train_examples INTEGER,
    valid_examples INTEGER,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def audit_path() -> Path:
    return _PATH


def _connect(path: Path | None = None) -> sqlite3.Connection:
    target = path or _PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_turn(
    *,
    session_id: str,
    role: str,
    content: str,
    validated_price: int | None = None,
    tactic: str | None = None,
    situation: str | None = None,
    reasoning: str | None = None,
    interpreted_intent: str | None = None,
    stage: str | None = None,
    model: str | None = None,
    path: Path | None = None,
) -> None:
    with _LOCK:
        conn = _connect(path)
        try:
            conn.execute(
                """
                INSERT INTO turns (
                    session_id, role, content, validated_price, tactic, situation,
                    reasoning, interpreted_intent, stage, model, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    role,
                    content,
                    validated_price,
                    tactic,
                    situation,
                    reasoning,
                    interpreted_intent,
                    stage,
                    model,
                    _now(),
                ),
            )
            conn.commit()
        finally:
            conn.close()


def log_insights(session: NegotiationSession, *, path: Path | None = None) -> None:
    rows = list(session.insight_log or [])
    if not rows:
        return
    with _LOCK:
        conn = _connect(path)
        try:
            conn.execute("DELETE FROM insights WHERE session_id = ?", (session.session_id,))
            for item in rows:
                conn.execute(
                    """
                    INSERT INTO insights (
                        session_id, round_number, intent, sentiment, signal_confidence,
                        tactic, situation, reasoning, extracted_facts, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session.session_id,
                        item.round_number,
                        item.intent,
                        item.sentiment,
                        item.signal_confidence,
                        item.tactic,
                        getattr(item, "situation", None),
                        item.reasoning,
                        json.dumps(item.extracted_facts or {}, ensure_ascii=False),
                        item.timestamp.isoformat() if item.timestamp else _now(),
                    ),
                )
            conn.commit()
        finally:
            conn.close()


def log_session(session: NegotiationSession, *, path: Path | None = None) -> None:
    with _LOCK:
        conn = _connect(path)
        try:
            conn.execute(
                """
                INSERT INTO session_snapshots (session_id, part_id, stage, payload, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    part_id = excluded.part_id,
                    stage = excluded.stage,
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (
                    session.session_id,
                    session.part_id,
                    session.stage.value,
                    session.model_dump_json(),
                    _now(),
                ),
            )
            conn.commit()
        finally:
            conn.close()


def log_lesson(row: dict[str, Any], *, path: Path | None = None) -> None:
    with _LOCK:
        conn = _connect(path)
        try:
            conn.execute(
                """
                INSERT INTO lessons (
                    id, session_id, part_id, part_name, vendor_name, situation, outcome,
                    handoff_reason, final_price, opening_quote, rounds, tactics, note, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    outcome = excluded.outcome,
                    note = excluded.note,
                    final_price = excluded.final_price
                """,
                (
                    row.get("id"),
                    row.get("session_id"),
                    row.get("part_id"),
                    row.get("part_name"),
                    row.get("vendor_name"),
                    row.get("situation"),
                    row.get("outcome"),
                    row.get("handoff_reason"),
                    row.get("final_price"),
                    row.get("opening_quote"),
                    row.get("rounds"),
                    json.dumps(row.get("tactics") or [], ensure_ascii=False),
                    row.get("note"),
                    row.get("created_at") or _now(),
                ),
            )
            conn.commit()
        finally:
            conn.close()


def fetch_turns(session_id: str, *, path: Path | None = None) -> list[dict[str, Any]]:
    with _LOCK:
        conn = _connect(path)
        try:
            rows = conn.execute(
                "SELECT * FROM turns WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()


def fetch_insights(session_id: str, *, path: Path | None = None) -> list[dict[str, Any]]:
    with _LOCK:
        conn = _connect(path)
        try:
            rows = conn.execute(
                "SELECT * FROM insights WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
            out = []
            for row in rows:
                item = dict(row)
                try:
                    item["extracted_facts"] = json.loads(item.get("extracted_facts") or "{}")
                except json.JSONDecodeError:
                    item["extracted_facts"] = {}
                out.append(item)
            return out
        finally:
            conn.close()


def fetch_lessons(
    *,
    part_id: str | None = None,
    situation: str | None = None,
    limit: int = 200,
    path: Path | None = None,
) -> list[dict[str, Any]]:
    with _LOCK:
        conn = _connect(path)
        try:
            query = "SELECT * FROM lessons WHERE 1=1"
            args: list[Any] = []
            if part_id:
                query += " AND part_id = ?"
                args.append(part_id)
            if situation:
                query += " AND situation = ?"
                args.append(situation)
            query += " ORDER BY created_at DESC LIMIT ?"
            args.append(limit)
            rows = conn.execute(query, args).fetchall()
            out = []
            for row in rows:
                item = dict(row)
                try:
                    item["tactics"] = json.loads(item.get("tactics") or "[]")
                except json.JSONDecodeError:
                    item["tactics"] = []
                out.append(item)
            return out
        finally:
            conn.close()


def fetch_recent_turns(*, limit: int = 200, path: Path | None = None) -> list[dict[str, Any]]:
    with _LOCK:
        conn = _connect(path)
        try:
            rows = conn.execute(
                "SELECT * FROM turns ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()


def count_table(table: str, *, path: Path | None = None) -> int:
    if table not in {"turns", "insights", "lessons", "session_snapshots", "labels", "ft_jobs"}:
        raise ValueError("unknown table")
    with _LOCK:
        conn = _connect(path)
        try:
            row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
            return int(row["n"] if row else 0)
        finally:
            conn.close()


def list_sessions(*, limit: int = 200, path: Path | None = None) -> list[dict[str, Any]]:
    with _LOCK:
        conn = _connect(path)
        try:
            rows = conn.execute(
                """
                SELECT session_id, part_id, stage, payload, updated_at
                FROM session_snapshots
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            out: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                payload: dict[str, Any] = {}
                raw = item.pop("payload", None)
                if raw:
                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError:
                        payload = {}
                item["round_count"] = payload.get("round_count")
                item["handoff_flag"] = bool(payload.get("handoff_flag"))
                item["handoff_reason"] = payload.get("handoff_reason")
                item["current_bot_offer"] = payload.get("current_bot_offer")
                item["current_vendor_offer"] = payload.get("current_vendor_offer")
                item["vendor_company"] = payload.get("vendor_company")
                item["vendor_rep_name"] = payload.get("vendor_rep_name")
                out.append(item)
            return out
        finally:
            conn.close()


def get_snapshot(session_id: str, *, path: Path | None = None) -> dict[str, Any] | None:
    with _LOCK:
        conn = _connect(path)
        try:
            row = conn.execute(
                "SELECT session_id, part_id, stage, payload, updated_at FROM session_snapshots WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def session_log(session_id: str, *, path: Path | None = None) -> dict[str, Any]:
    snapshot = get_snapshot(session_id, path=path)
    payload: dict[str, Any] = {}
    if snapshot and snapshot.get("payload"):
        try:
            payload = json.loads(snapshot["payload"])
        except json.JSONDecodeError:
            payload = {}
    return {
        "session_id": session_id,
        "part_id": snapshot.get("part_id") if snapshot else payload.get("part_id"),
        "stage": snapshot.get("stage") if snapshot else payload.get("stage"),
        "round_count": payload.get("round_count"),
        "handoff_reason": payload.get("handoff_reason"),
        "current_bot_offer": payload.get("current_bot_offer"),
        "current_vendor_offer": payload.get("current_vendor_offer"),
        "turns": fetch_turns(session_id, path=path),
        "insights": fetch_insights(session_id, path=path),
        "lessons": [row for row in fetch_lessons(path=path) if row.get("session_id") == session_id],
        "label": get_label(session_id, path=path),
    }


def upsert_label(row: dict[str, Any], *, path: Path | None = None) -> None:
    now = _now()
    with _LOCK:
        conn = _connect(path)
        try:
            conn.execute(
                """
                INSERT INTO labels (
                    session_id, quality, outcome, reasons, situations, tactics,
                    voice_examples, brain_examples, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    quality = excluded.quality,
                    outcome = excluded.outcome,
                    reasons = excluded.reasons,
                    situations = excluded.situations,
                    tactics = excluded.tactics,
                    voice_examples = excluded.voice_examples,
                    brain_examples = excluded.brain_examples,
                    updated_at = excluded.updated_at
                """,
                (
                    row["session_id"],
                    row.get("quality") or "reject",
                    row.get("outcome"),
                    json.dumps(row.get("reasons") or [], ensure_ascii=False),
                    json.dumps(row.get("situations") or [], ensure_ascii=False),
                    json.dumps(row.get("tactics") or [], ensure_ascii=False),
                    int(row.get("voice_examples") or 0),
                    int(row.get("brain_examples") or 0),
                    now,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()


def get_label(session_id: str, *, path: Path | None = None) -> dict[str, Any] | None:
    with _LOCK:
        conn = _connect(path)
        try:
            row = conn.execute("SELECT * FROM labels WHERE session_id = ?", (session_id,)).fetchone()
            return _decode_label(row) if row else None
        finally:
            conn.close()


def list_labels(*, quality: str | None = None, path: Path | None = None) -> list[dict[str, Any]]:
    with _LOCK:
        conn = _connect(path)
        try:
            if quality:
                rows = conn.execute("SELECT * FROM labels WHERE quality = ? ORDER BY updated_at DESC", (quality,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM labels ORDER BY updated_at DESC").fetchall()
            return [_decode_label(row) for row in rows]
        finally:
            conn.close()


def _decode_label(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    for key in ("reasons", "situations", "tactics"):
        try:
            item[key] = json.loads(item.get(key) or "[]")
        except json.JSONDecodeError:
            item[key] = []
    return item


def upsert_ft_job(row: dict[str, Any], *, path: Path | None = None) -> None:
    now = _now()
    with _LOCK:
        conn = _connect(path)
        try:
            conn.execute(
                """
                INSERT INTO ft_jobs (
                    job_id, status, base_model, fine_tuned_model, fingerprint,
                    train_examples, valid_examples, error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    status = excluded.status,
                    fine_tuned_model = excluded.fine_tuned_model,
                    error = excluded.error,
                    updated_at = excluded.updated_at
                """,
                (
                    row["job_id"],
                    row.get("status") or "queued",
                    row.get("base_model"),
                    row.get("fine_tuned_model"),
                    row.get("fingerprint"),
                    int(row.get("train_examples") or 0),
                    int(row.get("valid_examples") or 0),
                    row.get("error"),
                    now,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()


def list_ft_jobs(*, path: Path | None = None) -> list[dict[str, Any]]:
    with _LOCK:
        conn = _connect(path)
        try:
            rows = conn.execute("SELECT * FROM ft_jobs ORDER BY created_at DESC").fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()


def latest_open_job(*, path: Path | None = None) -> dict[str, Any] | None:
    with _LOCK:
        conn = _connect(path)
        try:
            row = conn.execute(
                """
                SELECT * FROM ft_jobs
                WHERE status IN ('queued', 'validating_files', 'running')
                ORDER BY created_at DESC LIMIT 1
                """
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def latest_job(*, path: Path | None = None) -> dict[str, Any] | None:
    rows = list_ft_jobs(path=path)
    return rows[0] if rows else None
