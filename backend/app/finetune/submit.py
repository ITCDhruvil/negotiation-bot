"""Upload labeled JSONL and start a supervised job."""

from __future__ import annotations

from pathlib import Path

from app.config import get_settings
from app.db.audit import upsert_ft_job
from app.finetune.export import export_dataset
from app.finetune.settings import resolved


def submit_voice_job(
    *,
    audit_path: Path | None = None,
    out_dir: Path | None = None,
    client=None,
    fingerprint: str | None = None,
) -> dict:
    settings = get_settings()
    cfg = resolved()
    preview = export_dataset(audit_path=audit_path, out_dir=out_dir)
    if preview["train_examples"] < cfg["min_examples"]:
        raise RuntimeError(
            f"Need {cfg['min_examples']} train examples; have {preview['train_examples']}"
        )
    if client is None:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY missing")
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)

    uploaded = client.files.create(file=open(preview["voice_path"], "rb"), purpose="fine-tune")
    kwargs: dict = {
        "training_file": uploaded.id,
        "model": cfg["base_model"],
        "suffix": cfg["suffix"] or "aria-voice",
    }
    if preview.get("valid_examples"):
        valid = client.files.create(file=open(preview["valid_path"], "rb"), purpose="fine-tune")
        kwargs["validation_file"] = valid.id
    if cfg.get("n_epochs"):
        kwargs["hyperparameters"] = {"n_epochs": cfg["n_epochs"]}
    job = client.fine_tuning.jobs.create(**kwargs)
    row = {
        "job_id": job.id,
        "status": job.status,
        "base_model": cfg["base_model"],
        "fine_tuned_model": getattr(job, "fine_tuned_model", None),
        "fingerprint": fingerprint,
        "train_examples": preview["train_examples"],
        "valid_examples": preview.get("valid_examples") or 0,
        "error": None,
    }
    upsert_ft_job(row, path=audit_path)
    return {**row, "training_file": uploaded.id, "examples": preview["train_examples"]}


def maybe_auto_submit() -> dict | None:
    from app.finetune.pipeline import tick

    result = tick()
    return result.get("submitted")
