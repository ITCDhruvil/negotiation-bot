from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from app.config import get_settings
from app.db.postgres import persist_handoff
from app.models import HandoffRecord, NegotiationSession

logger = logging.getLogger("handoff")


def _summary(session: NegotiationSession, transcript: list[dict]) -> dict:
    return {
        "part_id": session.part_id,
        "request_id": session.request_id,
        "anchor": session.anchor_price,
        "final_bot_offer": session.current_bot_offer,
        "final_vendor_offer": session.current_vendor_offer,
        "rounds": session.round_count,
        "gap": (
            None
            if session.current_vendor_offer is None
            else session.current_vendor_offer - session.current_bot_offer
        ),
        "vendor_rep_name": session.vendor_rep_name,
        "vendor_rep_contact": session.vendor_rep_contact,
        "turns": len(transcript),
    }


def _transcript_blurb(transcript: list[dict]) -> str:
    lines = []
    for turn in transcript[-12:]:
        role = turn.get("role", "?")
        content = (turn.get("content") or "")[:240]
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


async def execute_handoff(
    session: NegotiationSession,
    reason: str,
    transcript: list[dict],
) -> HandoffRecord:
    record = HandoffRecord(
        session_id=session.session_id,
        reason=reason,
        transcript_summary=_transcript_blurb(transcript),
        negotiation_summary=_summary(session, transcript),
        notified_at=datetime.now(timezone.utc),
    )
    await persist_handoff(record)
    await notify(record)
    return record


async def notify(record: HandoffRecord) -> None:
    settings = get_settings()
    payload = {
        "event": "negotiation_handoff",
        "session_id": record.session_id,
        "reason": record.reason,
        "summary": record.negotiation_summary,
        "transcript_summary": record.transcript_summary,
        "notified_at": record.notified_at.isoformat(),
    }
    logger.info("handoff", extra={"payload": payload})

    async with httpx.AsyncClient(timeout=8.0) as client:
        if settings.handoff_webhook_url:
            try:
                await client.post(settings.handoff_webhook_url, json=payload)
            except Exception:
                logger.exception("handoff webhook failed")
        if settings.slack_webhook_url:
            gap = record.negotiation_summary.get("gap")
            text = (
                f"*Aria handoff* `{record.session_id}`\n"
                f"Reason: `{record.reason}`\n"
                f"Vendor desk: {record.negotiation_summary.get('vendor_rep_name')} "
                f"({record.negotiation_summary.get('vendor_rep_contact')})\n"
                f"Our bid: ₹{record.negotiation_summary.get('final_bot_offer')}  "
                f"Vendor ask: ₹{record.negotiation_summary.get('final_vendor_offer')}  "
                f"Gap: {gap}"
            )
            try:
                await client.post(settings.slack_webhook_url, json={"text": text})
            except Exception:
                logger.exception("slack webhook failed")

    if settings.sendgrid_api_key and settings.notify_email_to:
        logger.info(
            "email stub (SendGrid/SES swap-in)",
            extra={"to": settings.notify_email_to, "reason": record.reason},
        )
