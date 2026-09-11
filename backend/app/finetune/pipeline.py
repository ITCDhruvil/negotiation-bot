"""End-to-end: label → export → submit when ready → poll → promote."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.db.audit import latest_job, latest_open_job, list_ft_jobs, list_labels, upsert_ft_job
from app.finetune.active import load_active, promote, resolved_chat_model
from app.finetune.export import export_dataset, preview_dataset
from app.finetune.labels import label_all
from app.finetune.settings import guidance, resolved

logger = logging.getLogger("aria.finetune")


def dataset_fingerprint(preview: dict[str, Any]) -> str:
    raw = json.dumps(
        {
            "train": preview.get("train_examples"),
            "valid": preview.get("valid_examples"),
            "sessions": preview.get("train_sessions"),
            "labels": preview.get("label_counts"),
        },
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def status(*, audit_path: Path | None = None) -> dict[str, Any]:
    settings = get_settings()
    cfg = resolved()
    labels = list_labels(path=audit_path)
    counts: dict[str, int] = {}
    for row in labels:
        quality = row.get("quality") or "unknown"
        counts[quality] = counts.get(quality, 0) + 1
    preview = preview_dataset(audit_path=audit_path)
    job = latest_job(path=audit_path)
    active = load_active()
    train_n = int(preview.get("train_examples") or 0)
    return {
        "auto": cfg["auto"],
        "base_model": cfg["base_model"],
        "min_examples": cfg["min_examples"],
        "config": cfg,
        "guidance": guidance(cfg["min_examples"], train_n),
        "label_counts": counts,
        "labels": labels[:200],
        "preview": preview,
        "ready": bool(preview.get("ready")),
        "fingerprint": dataset_fingerprint(preview),
        "open_job": latest_open_job(path=audit_path),
        "last_job": job,
        "active_chat_model": resolved_chat_model(settings.openai_model),
        "promoted": active,
        "jobs": list_ft_jobs(path=audit_path)[:100],
        "note": (
            "Pipeline auto-labels closed desks (train/reject), exports JSONL, starts a "
            f"{cfg['base_model']} job at the configured threshold, then can promote the chat model. "
            "o4-mini stays the brain."
        ),
    }


def _refresh_open_job(client, *, audit_path: Path | None = None) -> dict[str, Any] | None:
    open_job = latest_open_job(path=audit_path)
    if not open_job:
        return None
    remote = client.fine_tuning.jobs.retrieve(open_job["job_id"])
    row = {
        **open_job,
        "status": remote.status,
        "fine_tuned_model": getattr(remote, "fine_tuned_model", None),
        "error": str(getattr(remote, "error", None) or "") or None,
    }
    upsert_ft_job(row, path=audit_path)
    return row


def _promote_if_ready(job: dict[str, Any] | None) -> dict[str, Any] | None:
    if not resolved().get("auto_promote"):
        return None
    if not job or job.get("status") != "succeeded":
        return None
    model = job.get("fine_tuned_model")
    if not model:
        return None
    current = load_active()
    if current.get("chat_model") == model:
        return current
    promoted = promote(model, job_id=job.get("job_id"))
    logger.info("Promoted chat model to %s (job %s)", model, job.get("job_id"))
    return promoted


def _already_submitted(fingerprint: str, *, audit_path: Path | None = None) -> bool:
    for job in list_ft_jobs(path=audit_path):
        if job.get("fingerprint") == fingerprint and job.get("status") in {
            "queued",
            "validating_files",
            "running",
            "succeeded",
        }:
            return True
    return False


def tick(
    *,
    audit_path: Path | None = None,
    out_dir: Path | None = None,
    client=None,
    force: bool = False,
) -> dict[str, Any]:
    """One pipeline step. Safe to call after every close and on a timer."""
    settings = get_settings()
    cfg = resolved()
    labels = label_all(audit_path=audit_path)
    preview = preview_dataset(audit_path=audit_path)
    fingerprint = dataset_fingerprint(preview)
    refreshed = None
    submitted = None
    promoted = None

    live = client
    allow_network = os.environ.get("ARIA_ALLOW_MOCK") != "1" or force
    if live is None and allow_network and settings.openai_api_key and (cfg["auto"] or force):
        from openai import OpenAI

        live = OpenAI(api_key=settings.openai_api_key)

    if live is not None:
        refreshed = _refresh_open_job(live, audit_path=audit_path)
        promoted = _promote_if_ready(refreshed or latest_job(path=audit_path))

    can_submit = (
        (cfg["auto"] or force)
        and preview.get("ready")
        and live is not None
        and latest_open_job(path=audit_path) is None
        and not _already_submitted(fingerprint, audit_path=audit_path)
    )
    if can_submit:
        from app.finetune.submit import submit_voice_job

        submitted = submit_voice_job(
            audit_path=audit_path,
            out_dir=out_dir,
            client=live,
            fingerprint=fingerprint,
        )

    return {
        "labeled": len(labels),
        "label_counts": {
            key: sum(1 for row in labels if row.get("quality") == key)
            for key in ("train", "reject")
        },
        "preview": preview,
        "fingerprint": fingerprint,
        "submitted": submitted,
        "refreshed": refreshed,
        "promoted": promoted,
        "status": status(audit_path=audit_path),
    }
