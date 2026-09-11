from datetime import datetime, timezone
from pathlib import Path

from app.db.audit import (
    count_table,
    fetch_lessons,
    fetch_recent_turns,
    list_sessions,
    log_session,
    log_turn,
    session_log,
)
from app.models import InsightTurn, NegotiationStage
from app.playbook.memory import record_lesson

from tests.test_deal_engine import make_listing, make_session


def test_audit_stores_reasoning_with_the_assistant_turn(tmp_path: Path):
    db = tmp_path / "audit.db"
    log_turn(
        session_id="s-audit",
        role="assistant",
        content="We can do ₹14,904. What would close this?",
        validated_price=14_904,
        tactic="anchoring_hold",
        situation="opening",
        reasoning="Opening quote is an anchor, hold low and ask.",
        interpreted_intent="counter_offer",
        stage="negotiate",
        model="o4-mini",
        path=db,
    )
    payload = session_log("s-audit", path=db)
    assert payload["turns"]
    turn = payload["turns"][0]
    assert turn["reasoning"]
    assert "14,904" in turn["content"]
    assert turn["model"] == "o4-mini"
    assert "walk" not in (turn["reasoning"] or "").lower()


def test_record_lesson_writes_audit_row():
    listing = make_listing()
    session = make_session(
        stage=NegotiationStage.CLOSED,
        current_bot_offer=16_800,
        round_count=2,
        insight_log=[
            InsightTurn(
                round_number=1,
                intent="counter_offer",
                sentiment="cooperative",
                signal_confidence="high",
                tactic="package_trade",
                situation="cooperative_move",
                timestamp=datetime.now(timezone.utc),
            )
        ],
    )
    row = record_lesson(session, listing)
    assert row is not None
    found = fetch_lessons(part_id="headlight-lh", situation="cooperative_move")
    assert any(item.get("id") == row["id"] for item in found)
    assert all("max_acceptable" not in json_blob(item) for item in found)


def json_blob(item: dict) -> str:
    return str(item)


def test_list_sessions_and_recent_turns(tmp_path: Path):
    db = tmp_path / "audit.db"
    session = make_session(session_id="s-ops", stage=NegotiationStage.NEGOTIATE, round_count=2)
    log_session(session, path=db)
    log_turn(
        session_id="s-ops",
        role="assistant",
        content="We can do 14904.",
        path=db,
    )
    rows = list_sessions(path=db)
    assert rows[0]["session_id"] == "s-ops"
    assert rows[0]["round_count"] == 2
    assert count_table("turns", path=db) == 1
    recent = fetch_recent_turns(limit=10, path=db)
    assert recent[0]["content"] == "We can do 14904."
