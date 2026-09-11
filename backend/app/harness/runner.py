"""End-to-end harness: Aria's real graph + provider vs a simulated vendor LLM."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.catalog import get_part
from app.config import get_settings
from app.db.postgres import init_postgres
from app.db.redis_client import get_store, init_redis
from app.harness.personas import PRESETS, SCENARIOS, VendorPreset, vendor_system_prompt
from app.harness.score import RunScore, score_run
from app.llm.provider import MockProvider, build_provider
from app.main import _run_turn, app
from app.models import NegotiationSession, NegotiationStage, PartListing
from app.orchestrator.graph import build_graph

logger = logging.getLogger("aria.harness")
UTC = timezone.utc
TERMINAL = {
    NegotiationStage.CLOSED.value,
    NegotiationStage.HANDOFF.value,
    NegotiationStage.AGREEMENT.value,
}


@dataclass
class TranscriptTurn:
    role: str
    content: str
    stage: str | None = None


@dataclass
class ScenarioResult:
    scenario: str
    label: str
    part_id: str
    part_name: str
    provider: str
    vendor_walk_away_min: int
    transcript: list[TranscriptTurn] = field(default_factory=list)
    score: RunScore | None = None
    error: str | None = None


async def ensure_live_app() -> str:
    os.environ.pop("ARIA_ALLOW_MOCK", None)
    get_settings.cache_clear()
    await init_redis()
    await init_postgres()
    provider = build_provider()
    app.state.provider = provider
    app.state.graph = build_graph()
    if isinstance(provider, MockProvider) or provider.name == "mock":
        raise RuntimeError(
            "Harness refuses to run on mock. Set OPENAI_API_KEY (or another real provider) "
            "and do not set ARIA_ALLOW_MOCK=1."
        )
    logger.info("HARNESS LLM PROVIDER: %s (Aria and simulated vendor)", provider.name)
    return provider.name


async def _vendor_utterance(
    preset: VendorPreset,
    listing: PartListing,
    transcript: list[TranscriptTurn],
    queued: list[str],
) -> str:
    if queued:
        return queued.pop(0)
    provider = app.state.provider
    system = vendor_system_prompt(
        preset,
        part_name=listing.part_name,
        vendor_name=listing.vendor_name,
        opening_quote=listing.vendor_quoted_unit_price,
        quantity=listing.quantity,
        lead_time_days=listing.lead_time_days,
        payment_terms=listing.payment_terms_default,
        moq=listing.moq,
    )
    messages: list[dict[str, str]] = []
    for turn in transcript:
        if turn.role == "assistant":
            messages.append({"role": "user", "content": turn.content})
        elif turn.role == "user":
            messages.append({"role": "assistant", "content": turn.content})
    if not messages:
        messages = [{"role": "user", "content": "Hello — who am I speaking with?"}]
    chunks: list[str] = []
    async for token in provider.stream_text(system=system, messages=messages):
        chunks.append(token)
    text = "".join(chunks).strip()
    return text or "What number can you actually do?"


async def run_scenario(preset: VendorPreset, *, max_turns: int = 12) -> ScenarioResult:
    listing = get_part(preset.part_id)
    if listing is None:
        raise RuntimeError(f"Unknown part_id {preset.part_id}")
    provider_name = app.state.provider.name
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
        max_rounds=5,
    )
    result = ScenarioResult(
        scenario=preset.id,
        label=preset.label,
        part_id=listing.part_id,
        part_name=listing.part_name,
        provider=provider_name,
        vendor_walk_away_min=preset.walk_away_min,
    )
    queued = list(preset.qualify_replies) + list(preset.scripted_replies)
    store = get_store()
    try:
        await store.save(session)
        greeting = await _run_turn(session, listing, "", [])
        session = await store.get(session.session_id)
        if session is None:
            raise RuntimeError("session missing after greeting")
        result.transcript.append(TranscriptTurn(role="assistant", content=greeting, stage=session.stage.value))

        for _ in range(max_turns):
            if session.stage.value in TERMINAL or session.handoff_flag:
                break
            vendor_text = await _vendor_utterance(preset, listing, result.transcript, queued)
            result.transcript.append(TranscriptTurn(role="user", content=vendor_text, stage=session.stage.value))
            history = await store.transcript(session.session_id)
            aria_text = await _run_turn(session, listing, vendor_text, history)
            session = await store.get(session.session_id)
            if session is None:
                raise RuntimeError("session missing after turn")
            result.transcript.append(
                TranscriptTurn(role="assistant", content=aria_text, stage=session.stage.value)
            )
            if session.stage.value in TERMINAL or session.handoff_flag:
                break

        closed = session.stage.value in {NegotiationStage.CLOSED.value, NegotiationStage.AGREEMENT.value}
        last_bid = session.current_bot_offer or None
        aria_turns = [t.content for t in result.transcript if t.role == "assistant"]
        vendor_turns = [t.content for t in result.transcript if t.role == "user"]
        result.score = score_run(
            scenario=preset.id,
            opening_quote=listing.vendor_quoted_unit_price,
            target_price=listing.target_unit_price,
            final_price=last_bid,
            closed=closed,
            handoff=bool(session.handoff_flag),
            handoff_reason=session.handoff_reason,
            round_count=session.round_count,
            aria_turns=aria_turns,
            vendor_turns=vendor_turns,
            max_acceptable_unit_price=listing.max_acceptable_unit_price,
        )
    except Exception as exc:
        logger.exception("scenario %s failed", preset.id)
        result.error = str(exc)
    return result


def _result_dict(result: ScenarioResult) -> dict:
    payload = asdict(result)
    if result.score is not None:
        payload["score"] = asdict(result.score)
    return payload


def format_report(results: list[ScenarioResult]) -> str:
    lines: list[str] = []
    lines.append("Aria × simulated-vendor harness")
    lines.append("=" * 72)
    for result in results:
        lines.append("")
        lines.append(f"## {result.label} ({result.scenario}) — {result.part_name}")
        lines.append(f"provider={result.provider}  vendor_floor=₹{result.vendor_walk_away_min:,}")
        if result.error:
            lines.append(f"ERROR: {result.error}")
            continue
        score = result.score
        assert score is not None
        lines.append(
            f"closed={score.closed}  handoff={score.handoff} ({score.handoff_reason})  "
            f"rounds={score.round_count}  final={score.final_price}  "
            f"target={score.target_price}  opening={score.opening_quote}"
        )
        lines.append(
            f"% below opening={score.pct_below_opening}  at/below target={score.at_or_below_target}  "
            f"non-price trade={score.non_price_trade_attempted}  disclosure={score.ai_disclosure_present}"
        )
        lines.append(f"flags={score.flags or ['none']}")
        lines.append("transcript:")
        for turn in result.transcript:
            speaker = "Aria" if turn.role == "assistant" else "Vendor"
            stage = f" [{turn.stage}]" if turn.stage else ""
            lines.append(f"  {speaker}{stage}: {turn.content}")
    return "\n".join(lines) + "\n"


async def run_harness(scenario_ids: list[str] | None = None, *, max_turns: int = 12) -> list[ScenarioResult]:
    await ensure_live_app()
    ids = scenario_ids or list(SCENARIOS)
    results: list[ScenarioResult] = []
    for sid in ids:
        preset = PRESETS[sid]
        logger.info("running scenario %s", sid)
        results.append(await run_scenario(preset, max_turns=max_turns))
    return results


def write_outputs(results: list[ScenarioResult], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "last_run.json"
    txt_path = out_dir / "last_run.txt"
    json_path.write_text(json.dumps([_result_dict(r) for r in results], indent=2, ensure_ascii=False), encoding="utf-8")
    txt_path.write_text(format_report(results), encoding="utf-8")
    return json_path, txt_path
