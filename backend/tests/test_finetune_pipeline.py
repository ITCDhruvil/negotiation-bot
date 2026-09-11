from pathlib import Path

from app.config import get_settings
from app.db.audit import get_label, log_session, log_turn
from app.finetune.export import build_examples
from app.finetune.labels import label_session
from app.finetune.pipeline import tick
from app.models import NegotiationStage

from tests.test_deal_engine import make_session


def _desk(path: Path, session_id: str, *, leak: bool = False) -> None:
    session = make_session(session_id=session_id, stage=NegotiationStage.CLOSED, part_id="headlight-lh")
    log_session(session, path=path)
    log_turn(path=path, session_id=session_id, role="assistant", content="Hi. I'm an AI for SKODA sourcing. Who is this?")
    log_turn(path=path, session_id=session_id, role="user", content="Priya here, priya@valeo.example.")
    if leak:
        log_turn(
            path=path,
            session_id=session_id,
            role="assistant",
            content="Our walk-away is 17800 so that is the ceiling.",
        )
        return
    log_turn(
        path=path,
        session_id=session_id,
        role="assistant",
        content="Thanks Priya. We can do 14904. What would close this?",
        validated_price=14_904,
        tactic="anchoring_hold",
        situation="opening",
        reasoning="Opening quote is an anchor. Hold low and ask.",
        interpreted_intent="counter_offer",
        stage="negotiate",
    )


def test_auto_label_train_and_reject(tmp_path: Path):
    db = tmp_path / "audit.db"
    _desk(db, "lab-good")
    _desk(db, "lab-leak", leak=True)
    good = label_session("lab-good", part_id="headlight-lh", stage="closed", audit_path=db)
    bad = label_session("lab-leak", part_id="headlight-lh", stage="closed", audit_path=db)
    assert good["quality"] == "train"
    assert "opening" in good["situations"]
    assert bad["quality"] == "reject"
    assert "named_ceiling" in bad["reasons"] or "leaked_walkaway" in bad["reasons"]
    built = build_examples(audit_path=db)
    assert built["train_sessions"] == ["lab-good"]
    assert built["voice"]
    assert built["brain"]


class _File:
    id = "file-1"


class _Job:
    def __init__(self, status="queued", model=None):
        self.id = "ftjob-test"
        self.status = status
        self.fine_tuned_model = model
        self.error = None


class _FakeClient:
    def __init__(self):
        self.created = 0
        self.files = self
        self.fine_tuning = self
        self.jobs = self

    def create(self, **kwargs):
        if "file" in kwargs:
            return _File()
        self.created += 1
        return _Job()

    def retrieve(self, job_id):
        return _Job(status="succeeded", model="ft:gpt-4o-mini:aria:test")


def test_tick_submits_when_labeled_enough(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_FINETUNE_AUTO", "true")
    monkeypatch.setenv("OPENAI_FINETUNE_MIN_EXAMPLES", "1")
    monkeypatch.setattr("app.finetune.active._PATH", tmp_path / "active_model.json")
    monkeypatch.setattr("app.finetune.settings._PATH", tmp_path / "ft-settings.json")
    get_settings.cache_clear()
    db = tmp_path / "audit.db"
    out = tmp_path / "out"
    _desk(db, "pipe-1")
    fake = _FakeClient()
    try:
        result = tick(audit_path=db, out_dir=out, client=fake, force=True)
        assert result["submitted"]
        assert result["submitted"]["job_id"] == "ftjob-test"
        assert fake.created == 1
        again = tick(audit_path=db, out_dir=out, client=fake, force=True)
        assert again["submitted"] is None
        assert again["promoted"]["chat_model"] == "ft:gpt-4o-mini:aria:test"
    finally:
        get_settings.cache_clear()
        monkeypatch.delenv("OPENAI_FINETUNE_MIN_EXAMPLES", raising=False)
