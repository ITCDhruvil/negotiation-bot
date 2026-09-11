from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import get_settings
from app.db.audit import (
    audit_path,
    count_table,
    fetch_lessons,
    fetch_recent_turns,
    list_labels,
    list_sessions,
    session_log,
)
from app.finetune.export import export_dataset, preview_dataset
from app.finetune.pipeline import status as finetune_status
from app.finetune.pipeline import tick as finetune_tick
from app.finetune.settings import apply_patch as apply_finetune_settings
from app.finetune.settings import resolved as finetune_resolved
from app.db.postgres import close_postgres, init_postgres, persist_message, persist_session
from app.db.redis_client import get_store, init_redis
from app.catalog import get_part, list_parts, list_requests
from app.rfq.extract import parse_document, parse_text
from app.rfq.service import create_rfq
from app.llm.provider import build_provider, provider_models
from app.demo import next_vendor_reply
from app.models import (
    ChatMessage,
    ChatRequest,
    CreateRfqRequest,
    DemoVendorRequest,
    NegotiationSession,
    NegotiationStage,
    StartSessionRequest,
    StartSessionResponse,
    to_public_listing,
    to_public_session,
)
from app.orchestrator.graph import build_graph
from app.orchestrator.nodes import PROVIDER, TOKEN_SINK
from app.security import SlidingWindowLimiter, looks_like_jailbreak

logger = logging.getLogger("aria")
UTC = timezone.utc


class FineTuneSettingsIn(BaseModel):
    auto: bool | None = None
    min_examples: int | None = Field(default=None, ge=10, le=2000)
    base_model: str | None = None
    suffix: str | None = None
    n_epochs: int | str | None = None
    auto_promote: bool | None = None
    tick_seconds: int | None = Field(default=None, ge=15, le=3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    await init_redis()
    await init_postgres()
    app.state.provider = build_provider()
    app.state.graph = build_graph()
    app.state.limiter = SlidingWindowLimiter(settings.rate_limit_per_minute)
    logger.info(
        "============================================================"
    )
    chat_model, reasoning_model = provider_models(app.state.provider)
    logger.info(
        "ARIA LLM PROVIDER: %s  chat=%s  reason=%s  mock=%s  company=%s  bind=%s:%s",
        app.state.provider.name,
        chat_model or "-",
        reasoning_model or "-",
        app.state.provider.name == "mock",
        settings.company_name,
        settings.backend_host,
        settings.backend_port,
    )
    if app.state.provider.name == "mock":
        logger.critical(
            "LIVE SESSION ON MOCK — replies are fixture text. Set OPENAI_API_KEY (or another real provider)."
        )
    logger.info(
        "============================================================"
    )
    stop = asyncio.Event()

    async def _finetune_loop() -> None:
        from app.finetune.settings import resolved as finetune_resolved

        while not stop.is_set():
            try:
                finetune_tick()
            except Exception:
                logger.exception("finetune pipeline tick failed")
            wait = max(15, int(finetune_resolved().get("tick_seconds") or 90))
            try:
                await asyncio.wait_for(stop.wait(), timeout=wait)
            except TimeoutError:
                continue

    loop_task = asyncio.create_task(_finetune_loop())
    yield
    stop.set()
    loop_task.cancel()
    await close_postgres()


def _cors_origins() -> list[str]:
    return [origin.strip() for origin in get_settings().cors_origins.split(",") if origin.strip()]


app = FastAPI(title="Aria Procurement Negotiation", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins() or ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    provider = getattr(app.state, "provider", None)
    chat_model, reasoning_model = provider_models(provider) if provider else ("", "")
    return {
        "ok": True,
        "provider": getattr(provider, "name", None),
        "is_mock": bool(provider and provider.name == "mock"),
        "chat_model": chat_model or None,
        "reasoning_model": reasoning_model or None,
        "company": get_settings().company_name,
        "port": get_settings().backend_port,
    }


@app.get("/api/catalog")
async def catalog():
    requests = []
    for req in list_requests():
        requests.append(
            {
                "request_id": req.request_id,
                "title": req.title,
                "plant": req.plant,
                "needed_by": req.needed_by,
                "parts": [to_public_listing(part).model_dump() for part in req.parts],
            }
        )
    return {"company": get_settings().company_name, "requests": requests}


@app.post("/api/rfq/parse")
async def parse_rfq(
    request: Request,
    file: UploadFile | None = File(default=None),
    text: str = Form(default=""),
):
    if not app.state.limiter.allow(_client_key(request, "rfq-parse")):
        raise HTTPException(status_code=429, detail="Too many requests")
    pasted = (text or "").strip()
    filename = file.filename if file else ""
    content = await file.read() if file else b""
    content_type = file.content_type if file else None
    if not content and not pasted:
        raise HTTPException(status_code=400, detail="Upload a document or paste RFQ text.")
    try:
        draft = await parse_document(
            filename=filename or "",
            content=content,
            content_type=content_type,
            pasted_text=pasted,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return draft.model_dump()


class ParseRfqTextIn(BaseModel):
    text: str


@app.post("/api/rfq/parse-text")
async def parse_rfq_text(body: ParseRfqTextIn, request: Request):
    if not app.state.limiter.allow(_client_key(request, "rfq-parse")):
        raise HTTPException(status_code=429, detail="Too many requests")
    if not (body.text or "").strip():
        raise HTTPException(status_code=400, detail="Paste RFQ text first.")
    draft = parse_text(body.text)
    if (not draft.title) or any(part.missing for part in draft.parts):
        draft = await parse_document(
            filename="pasted.txt",
            content=b"",
            content_type="text/plain",
            pasted_text=body.text,
        )
    return draft.model_dump()


@app.post("/api/rfq")
async def create_rfq_route(body: CreateRfqRequest, request: Request):
    if not app.state.limiter.allow(_client_key(request, "rfq-create")):
        raise HTTPException(status_code=429, detail="Too many requests")
    try:
        created = create_rfq(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "request_id": created.request_id,
        "title": created.title,
        "plant": created.plant,
        "needed_by": created.needed_by,
        "parts": [to_public_listing(part).model_dump() for part in created.parts],
    }


@app.get("/api/sessions/{session_id}/insights")
async def get_insights(session_id: str):
    """SKODA-side only. Reasoning traces are never part of the vendor chat payload."""
    session = await get_store().get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session")
    return {
        "session_id": session.session_id,
        "insights": [item.model_dump(mode="json") for item in session.insight_log],
    }


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    session = await get_store().get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session")
    listing = get_part(session.part_id)
    return {
        "session": to_public_session(session).model_dump(),
        "listing": to_public_listing(listing).model_dump() if listing else None,
        "transcript": await get_store().transcript(session_id),
    }


@app.get("/api/sessions/{session_id}/log")
async def get_session_log(session_id: str):
    """SKODA data-collection log: each turn + internal reasoning. Never vendor-facing."""
    session = await get_store().get(session_id)
    payload = session_log(session_id)
    if session is None and not payload["turns"]:
        raise HTTPException(status_code=404, detail="Unknown session")
    if session is not None:
        payload["stage"] = session.stage.value
        payload["part_id"] = session.part_id
        payload["handoff_reason"] = session.handoff_reason
        payload["round_count"] = session.round_count
        payload["current_bot_offer"] = session.current_bot_offer
        payload["current_vendor_offer"] = session.current_vendor_offer
    return payload


@app.get("/api/lessons")
async def get_lessons(part_id: str | None = None, situation: str | None = None):
    """Cross-desk lessons the next negotiation can reuse."""
    return {"lessons": fetch_lessons(part_id=part_id, situation=situation)}


@app.get("/api/labels")
async def get_labels(quality: str | None = None):
    """Train/reject labels for closed desks. SKODA-side only."""
    return {"labels": list_labels(quality=quality)}


@app.get("/api/logs/sessions")
async def get_logged_sessions():
    return {"sessions": list_sessions()}


@app.get("/api/finetune/preview")
async def finetune_preview():
    """How many closed desks are ready for a gpt-4o-mini job. Does not start one."""
    return preview_dataset()


@app.get("/api/finetune/status")
async def get_finetune_status():
    """Labels, readiness, open job, and the promoted chat model."""
    return finetune_status()


@app.post("/api/finetune/tick")
async def post_finetune_tick():
    """Label new desks, submit if the threshold is met, poll/promote if a job is running."""
    return finetune_tick()


@app.post("/api/finetune/export")
async def post_finetune_export():
    """Write labeled JSONL to backend/data/finetune. Does not start a job."""
    return export_dataset()


@app.post("/api/finetune/submit")
async def post_finetune_submit():
    """Force a pipeline tick, including a job if enough train examples exist."""
    return finetune_tick(force=True)


@app.get("/api/finetune/settings")
async def get_finetune_settings():
    """Live fine-tune knobs. Overlay file wins over .env. No secrets."""
    return finetune_resolved()


@app.patch("/api/finetune/settings")
async def patch_finetune_settings(body: FineTuneSettingsIn):
    """Save dashboard edits. Takes effect on the next tick / preview / submit."""
    patch = body.model_dump(exclude_unset=True)
    try:
        return apply_finetune_settings(patch)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/logs/recent")
async def get_recent_logs():
    return {"turns": fetch_recent_turns(limit=200)}


@app.get("/api/ops/overview")
async def ops_overview():
    provider = getattr(app.state, "provider", None)
    chat_model, reasoning_model = provider_models(provider) if provider else ("", "")
    settings = get_settings()
    pipeline = finetune_status()
    return {
        "health": {
            "ok": True,
            "provider": getattr(provider, "name", None),
            "is_mock": bool(provider and provider.name == "mock"),
            "chat_model": chat_model or None,
            "reasoning_model": reasoning_model or None,
            "company": settings.company_name,
            "port": settings.backend_port,
            "finetune_auto": pipeline.get("auto"),
        },
        "counts": {
            "sessions": count_table("session_snapshots"),
            "turns": count_table("turns"),
            "insights": count_table("insights"),
            "lessons": count_table("lessons"),
            "labels": count_table("labels"),
            "jobs": count_table("ft_jobs"),
            "catalog_parts": len(list_parts()),
        },
        "sessions": list_sessions(limit=200),
        "audit_db": str(audit_path()),
        "pipeline": {
            "ready": pipeline.get("ready"),
            "auto": pipeline.get("auto"),
            "train_examples": (pipeline.get("preview") or {}).get("train_examples"),
            "min_examples": pipeline.get("min_examples"),
            "guidance": pipeline.get("guidance"),
            "label_counts": pipeline.get("label_counts"),
            "active_chat_model": pipeline.get("active_chat_model"),
            "open_job": pipeline.get("open_job"),
        },
    }


@app.post("/api/sessions", response_model=StartSessionResponse)
async def start_session(body: StartSessionRequest, request: Request):
    listing = get_part(body.part_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Unknown part_id")
    if not app.state.limiter.allow(_client_key(request, "start")):
        raise HTTPException(status_code=429, detail="Too many requests")

    now = datetime.now(UTC)
    session = NegotiationSession(
        session_id=str(uuid4()),
        vendor_rep_name=None,
        vendor_rep_contact=None,
        part_id=listing.part_id,
        request_id=listing.request_id,
        stage=NegotiationStage.GREET_AND_DISCLOSE,
        anchor_price=0,
        current_bot_offer=0,
        current_vendor_offer=listing.vendor_quoted_unit_price,
        payment_terms=listing.payment_terms_default,
        current_lead_time_days=listing.lead_time_days,
        current_moq=listing.moq,
        created_at=now,
        updated_at=now,
    )
    greeting = await _run_turn(session, listing, user_message="", transcript=[])
    stored = await get_store().get(session.session_id)
    return StartSessionResponse(
        session_id=session.session_id,
        stage=stored.stage if stored else session.stage,
        listing=to_public_listing(listing),
        greeting=greeting,
        llm_provider=app.state.provider.name,
        llm_model=provider_models(app.state.provider)[1],
    )


@app.post("/api/demo/vendor-turn")
async def demo_vendor_turn(body: DemoVendorRequest, request: Request):
    """One opposite-side (vendor bot) line for the on-screen Test demo."""
    if not app.state.limiter.allow(_client_key(request, body.session_id)):
        raise HTTPException(status_code=429, detail="Too many requests")
    session = await get_store().get(body.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session")
    listing = get_part(session.part_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Unknown part_id")
    if session.stage in {NegotiationStage.CLOSED, NegotiationStage.HANDOFF, NegotiationStage.AGREEMENT}:
        return {"text": "", "persona": None, "label": None, "done": True}
    transcript = await get_store().transcript(session.session_id)
    text, preset = await next_vendor_reply(
        provider=app.state.provider,
        session_id=session.session_id,
        listing=listing,
        transcript=transcript,
        persona=body.persona,
    )
    return {
        "text": text,
        "persona": preset.id,
        "label": preset.label,
        "done": False,
    }


@app.post("/api/chat/stream")
async def chat_stream(body: ChatRequest, request: Request):
    if not app.state.limiter.allow(_client_key(request, body.session_id)):
        raise HTTPException(status_code=429, detail="Too many requests")
    session = await get_store().get(body.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session")
    listing = get_part(session.part_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Unknown part_id")

    message = body.message.strip()
    if looks_like_jailbreak(message):
        refusal = (
            "I can't share internal instructions or walk-away prices. "
            "I can keep talking about this part's unit price and terms — what would close the line?"
        )
        return StreamingResponse(_one_shot_sse(refusal, session), media_type="text/event-stream")

    return StreamingResponse(
        _turn_sse(session, listing, message),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _client_key(request: Request, extra: str) -> str:
    host = request.client.host if request.client else "unknown"
    return f"{host}:{extra}"


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _one_shot_sse(text: str, session: NegotiationSession) -> AsyncIterator[str]:
    yield _sse({"type": "token", "content": text})
    yield _sse({"type": "session", "session": to_public_session(session).model_dump()})
    yield _sse({"type": "done"})


async def _turn_sse(session: NegotiationSession, listing, message: str) -> AsyncIterator[str]:
    import asyncio

    queue: asyncio.Queue = asyncio.Queue()

    async def sink(token: str) -> None:
        await queue.put(("token", token))

    async def run() -> None:
        try:
            transcript = await get_store().transcript(session.session_id)
            text = await _run_turn(session, listing, message, transcript, sink=sink)
            latest = await get_store().get(session.session_id)
            await queue.put(("result", {"text": text, "session": latest}))
        except Exception as exc:
            logger.exception("turn failed")
            await queue.put(("error", str(exc)))
        finally:
            await queue.put(("close", None))

    task = asyncio.create_task(run())
    try:
        while True:
            kind, data = await queue.get()
            if kind == "token":
                yield _sse({"type": "token", "content": data})
            elif kind == "result":
                latest = data["session"] or session
                yield _sse({"type": "session", "session": to_public_session(latest).model_dump()})
                insights = [item.model_dump(mode="json") for item in (latest.insight_log or [])]
                if insights:
                    yield _sse({"type": "insights", "insights": insights})
                if latest.current_bot_offer and latest.stage.value in {"negotiate", "agreement", "closed"}:
                    yield _sse({"type": "price", "amount": latest.current_bot_offer})
                yield _sse({"type": "stage", "stage": latest.stage.value})
                yield _sse({"type": "done"})
            elif kind == "error":
                yield _sse({"type": "error", "message": data})
                yield _sse({"type": "done"})
            elif kind == "close":
                break
    finally:
        await task


async def _run_turn(session: NegotiationSession, listing, user_message: str, transcript: list, sink=None) -> str:
    store = get_store()
    if user_message:
        user_msg = ChatMessage(role="user", content=user_message, timestamp=datetime.now(UTC))
        await store.append_message(session.session_id, user_msg)
        await persist_message(
            session.session_id,
            "user",
            user_message,
            stage=session.stage.value,
        )
        transcript = [*transcript, user_msg.model_dump(mode="json")]

    token = TOKEN_SINK.set(sink)
    prov = PROVIDER.set(app.state.provider)
    try:
        result = await app.state.graph.ainvoke(
            {
                "session": session.model_dump(mode="json"),
                "listing": listing.model_dump(mode="json"),
                "user_message": user_message,
                "assistant_message": "",
                "transcript": transcript,
                "validated_price": None,
                "tactic": None,
            }
        )
    finally:
        TOKEN_SINK.reset(token)
        PROVIDER.reset(prov)

    updated = NegotiationSession.model_validate(result["session"])
    assistant_text = result.get("assistant_message") or ""
    last_insight = updated.insight_log[-1] if updated.insight_log else None
    situation = result.get("situation") or (last_insight.situation if last_insight else None)
    reasoning = result.get("reasoning") or (last_insight.reasoning if last_insight else None)
    intent = result.get("interpreted_intent") or (last_insight.intent if last_insight else None)
    tactic = result.get("tactic") or (last_insight.tactic if last_insight else None)
    _, model_name = provider_models(app.state.provider)
    await store.save(updated)
    await persist_session(updated)
    if assistant_text:
        await store.append_message(
            updated.session_id,
            ChatMessage(
                role="assistant",
                content=assistant_text,
                timestamp=datetime.now(UTC),
                validated_price=result.get("validated_price"),
                tactic=tactic,
                reasoning=reasoning,
                interpreted_intent=intent,
                situation=situation,
            ),
        )
        await persist_message(
            updated.session_id,
            "assistant",
            assistant_text,
            validated_price=result.get("validated_price"),
            tactic=tactic,
            reasoning=reasoning,
            interpreted_intent=intent,
            situation=situation,
            stage=updated.stage.value,
            model=model_name,
        )
    return assistant_text


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.backend_host,
        port=settings.backend_port,
    )
