from __future__ import annotations

import json
from datetime import datetime, timezone

from app.config import get_settings
from app.models import HandoffRecord, NegotiationSession

_POOL = None
_MEMORY_MESSAGES: list[dict] = []
_MEMORY_LEADS: list[dict] = []
_MEMORY_HANDOFFS: list[dict] = []


SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    validated_price INT,
    tactic TEXT,
    reasoning TEXT,
    interpreted_intent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS vendor_desks (
    session_id TEXT PRIMARY KEY,
    name TEXT,
    contact TEXT,
    part_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS handoffs (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    transcript_summary TEXT,
    negotiation_summary JSONB,
    notified_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


async def init_postgres():
    global _POOL
    settings = get_settings()
    if settings.use_in_memory:
        return None
    try:
        import asyncpg

        _POOL = await asyncpg.create_pool(dsn=settings.database_url, min_size=1, max_size=5)
        async with _POOL.acquire() as conn:
            await conn.execute(SCHEMA)
            await conn.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS reasoning TEXT")
            await conn.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS interpreted_intent TEXT")
            await conn.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS situation TEXT")
            await conn.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS stage TEXT")
            await conn.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS model TEXT")
        return _POOL
    except Exception:
        _POOL = None
        return None


async def persist_session(session: NegotiationSession) -> None:
    from app.db.audit import log_insights, log_session

    log_session(session)
    log_insights(session)
    if _POOL is None:
        return
    async with _POOL.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO sessions (session_id, payload, created_at, updated_at)
            VALUES ($1, $2::jsonb, $3, $4)
            ON CONFLICT (session_id) DO UPDATE SET payload = EXCLUDED.payload, updated_at = EXCLUDED.updated_at
            """,
            session.session_id,
            session.model_dump_json(),
            session.created_at,
            session.updated_at,
        )


async def persist_message(
    session_id: str,
    role: str,
    content: str,
    validated_price: int | None = None,
    tactic: str | None = None,
    reasoning: str | None = None,
    interpreted_intent: str | None = None,
    situation: str | None = None,
    stage: str | None = None,
    model: str | None = None,
) -> None:
    row = {
        "session_id": session_id,
        "role": role,
        "content": content,
        "validated_price": validated_price,
        "tactic": tactic,
        "reasoning": reasoning,
        "interpreted_intent": interpreted_intent,
        "situation": situation,
        "stage": stage,
        "model": model,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    from app.db.audit import log_turn

    log_turn(
        session_id=session_id,
        role=role,
        content=content,
        validated_price=validated_price,
        tactic=tactic,
        situation=situation,
        reasoning=reasoning,
        interpreted_intent=interpreted_intent,
        stage=stage,
        model=model,
    )
    if _POOL is None:
        _MEMORY_MESSAGES.append(row)
        return
    async with _POOL.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO messages (
                session_id, role, content, validated_price, tactic, reasoning,
                interpreted_intent, situation, stage, model
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            session_id,
            role,
            content,
            validated_price,
            tactic,
            reasoning,
            interpreted_intent,
            situation,
            stage,
            model,
        )


async def persist_lead(session: NegotiationSession) -> None:
    if not session.vendor_rep_name and not session.vendor_rep_contact:
        return
    row = {
        "session_id": session.session_id,
        "name": session.vendor_rep_name,
        "contact": session.vendor_rep_contact,
        "part_id": session.part_id,
    }
    if _POOL is None:
        _MEMORY_LEADS.append(row)
        return
    async with _POOL.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO vendor_desks (session_id, name, contact, part_id)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (session_id) DO UPDATE SET name = EXCLUDED.name, contact = EXCLUDED.contact
            """,
            session.session_id,
            session.vendor_rep_name,
            session.vendor_rep_contact,
            session.part_id,
        )


async def persist_handoff(record: HandoffRecord) -> None:
    row = record.model_dump(mode="json")
    if _POOL is None:
        _MEMORY_HANDOFFS.append(row)
        return
    async with _POOL.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO handoffs (session_id, reason, transcript_summary, negotiation_summary, notified_at)
            VALUES ($1, $2, $3, $4::jsonb, $5)
            """,
            record.session_id,
            record.reason,
            record.transcript_summary,
            json.dumps(record.negotiation_summary),
            record.notified_at,
        )


async def close_postgres() -> None:
    global _POOL
    if _POOL is not None:
        await _POOL.close()
        _POOL = None
