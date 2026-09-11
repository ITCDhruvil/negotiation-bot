from pathlib import Path

import pytest

from app.finetune.settings import apply_patch, quality_band, resolved


def test_overlay_wins_over_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENAI_FINETUNE_MIN_EXAMPLES", "20")
    monkeypatch.setenv("OPENAI_FINETUNE_AUTO", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    dest = tmp_path / "settings.json"
    monkeypatch.setattr("app.finetune.settings._PATH", dest)
    cfg = apply_patch(
        {
            "min_examples": 100,
            "auto": False,
            "base_model": "gpt-4o-mini",
            "n_epochs": 3,
            "tick_seconds": 120,
            "auto_promote": False,
            "suffix": "aria-desk",
        },
        path=dest,
    )
    assert cfg["min_examples"] == 100
    assert cfg["auto"] is False
    assert cfg["n_epochs"] == 3
    assert cfg["tick_seconds"] == 120
    assert cfg["auto_promote"] is False
    assert cfg["suffix"] == "aria-desk"
    assert cfg["source"] == "overlay"
    assert resolved(path=dest)["min_examples"] == 100
    get_settings.cache_clear()


def test_rejects_reasoning_base_and_sub_floor(tmp_path: Path):
    dest = tmp_path / "settings.json"
    with pytest.raises(ValueError, match="cannot be fine-tuned"):
        apply_patch({"base_model": "o4-mini"}, path=dest)
    with pytest.raises(ValueError, match="at least 10"):
        apply_patch({"min_examples": 9}, path=dest)
    assert quality_band(20) == "thin"
    assert quality_band(50) == "workable"
    assert quality_band(120) == "solid"


def test_settings_route_registered():
    from app.main import app

    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/api/finetune/settings" in paths
