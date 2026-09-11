from __future__ import annotations

import json
from datetime import datetime, timezone

from app.config import get_settings
from app.models import ChatMessage, NegotiationSession

UTC = timezone.utc


class MemorySessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, str] = {}
        self._transcripts: dict[str, list[dict]] = {}

    async def get(self, session_id: str) -> NegotiationSession | None:
        raw = self._sessions.get(session_id)
        if not raw:
            return None
        return NegotiationSession.model_validate_json(raw)

    async def save(self, session: NegotiationSession) -> None:
        session.updated_at = datetime.now(UTC)
        self._sessions[session.session_id] = session.model_dump_json()

    async def append_message(self, session_id: str, message: ChatMessage) -> None:
        self._transcripts.setdefault(session_id, []).append(message.model_dump(mode="json"))

    async def transcript(self, session_id: str) -> list[dict]:
        return list(self._transcripts.get(session_id, []))


class RedisSessionStore:
    def __init__(self, client) -> None:
        self._client = client
        self._ttl = get_settings().session_ttl_seconds

    def _key(self, session_id: str) -> str:
        return f"nego:session:{session_id}"

    def _transcript_key(self, session_id: str) -> str:
        return f"nego:transcript:{session_id}"

    async def get(self, session_id: str) -> NegotiationSession | None:
        raw = await self._client.get(self._key(session_id))
        if not raw:
            return None
        return NegotiationSession.model_validate_json(raw)

    async def save(self, session: NegotiationSession) -> None:
        session.updated_at = datetime.now(UTC)
        await self._client.set(
            self._key(session.session_id),
            session.model_dump_json(),
            ex=self._ttl,
        )

    async def append_message(self, session_id: str, message: ChatMessage) -> None:
        await self._client.rpush(self._transcript_key(session_id), json.dumps(message.model_dump(mode="json")))
        await self._client.expire(self._transcript_key(session_id), self._ttl)

    async def transcript(self, session_id: str) -> list[dict]:
        rows = await self._client.lrange(self._transcript_key(session_id), 0, -1)
        return [json.loads(row) for row in rows]


_STORE: MemorySessionStore | RedisSessionStore | None = None


async def init_redis():
    global _STORE
    settings = get_settings()
    if settings.use_in_memory:
        _STORE = MemorySessionStore()
        return None
    try:
        from redis.asyncio import Redis

        client = Redis.from_url(settings.redis_url, decode_responses=True)
        await client.ping()
        _STORE = RedisSessionStore(client)
        return client
    except Exception:
        _STORE = MemorySessionStore()
        return None


def get_store() -> MemorySessionStore | RedisSessionStore:
    if _STORE is None:
        raise RuntimeError("Session store is not initialized")
    return _STORE
