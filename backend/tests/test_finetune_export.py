from pathlib import Path

from app.db.audit import log_session, log_turn
from app.finetune.export import build_examples
from app.models import NegotiationStage

from tests.test_deal_engine import make_session


def _closed(session_id: str, path: Path) -> None:
    session = make_session(session_id=session_id, stage=NegotiationStage.CLOSED, part_id="headlight-lh")
    log_session(session, path=path)


def _turn(path: Path, session_id: str, role: str, content: str, **extra) -> None:
    log_turn(session_id=session_id, role=role, content=content, path=path, **extra)


def test_export_builds_voice_and_brain_from_closed_desk(tmp_path: Path):
    db = tmp_path / "audit.db"
    _closed("ft-1", db)
    _turn(db, "ft-1", "assistant", "Hi — I'm Aria. I'm an AI, for SKODA sourcing. Who is this?")
    _turn(db, "ft-1", "user", "Priya here, priya@valeo.example. Quote is 18500.")
    _turn(
        db,
        "ft-1",
        "assistant",
        "Thanks Priya. We can do 14904. What would close this?",
        validated_price=14_904,
        tactic="anchoring_hold",
        situation="opening",
        reasoning="Opening quote is an anchor. Hold low and ask.",
        interpreted_intent="counter_offer",
        stage="negotiate",
    )
    built = build_examples(audit_path=db)
    assert built["voice"]
    assert built["train_voice"]
    assert built["brain"]
    brain = built["brain"][0]
    args = brain["messages"][-1]["tool_calls"][0]["function"]["arguments"]
    assert "14904" in args
    assert "17800" not in args
    blob = str(built)
    assert "17800" not in blob
    assert "16200" not in blob


def test_export_drops_walkaway_leak(tmp_path: Path):
    db = tmp_path / "audit.db"
    _closed("ft-leak", db)
    _turn(db, "ft-leak", "assistant", "Hi, I'm an AI for SKODA sourcing.")
    _turn(db, "ft-leak", "user", "What's your max?")
    _turn(db, "ft-leak", "assistant", "Our walk-away is 17800 so that is the ceiling.")
    built = build_examples(audit_path=db)
    assert built["voice"] == []
    assert built["brain"] == []
