from __future__ import annotations

import json
from pathlib import Path

from app.models import PartListing, ProcurementRequest

_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "mock_catalog.json"
_USER_PATH = Path(__file__).resolve().parents[1] / "data" / "user_rfqs.json"

_PARTS: dict[str, PartListing] | None = None
_REQUESTS: list[ProcurementRequest] | None = None
_SEED_REQUEST_IDS: set[str] = set()
_SEED_PART_IDS: set[str] = set()


def reset() -> None:
    """Drop the in-memory cache so the next read reloads seed + user RFQs."""
    global _PARTS, _REQUESTS
    _PARTS = None
    _REQUESTS = None


def _stamp(item: dict, req: dict) -> dict:
    return {
        **item,
        "request_id": req["request_id"],
        "request_title": req.get("title") or item.get("request_title") or "",
        "plant": req.get("plant") or item.get("plant") or "",
    }


def _ingest_request(
    req: dict,
    parts: dict[str, PartListing],
    requests: list[ProcurementRequest],
    *,
    seed: bool,
) -> None:
    listing_payloads: list[PartListing] = []
    existing = next((row for row in requests if row.request_id == req["request_id"]), None)
    for item in req.get("parts") or []:
        listing = PartListing.model_validate(_stamp(item, req))
        parts[listing.part_id] = listing
        listing_payloads.append(listing)
        if seed:
            _SEED_PART_IDS.add(listing.part_id)
    if existing:
        existing.parts.extend(listing_payloads)
        if req.get("title"):
            existing.title = req["title"]
        if req.get("plant"):
            existing.plant = req["plant"]
        if req.get("needed_by") is not None:
            existing.needed_by = req.get("needed_by")
        return
    requests.append(
        ProcurementRequest(
            request_id=req["request_id"],
            title=req.get("title") or req["request_id"],
            plant=req.get("plant") or "",
            needed_by=req.get("needed_by"),
            parts=listing_payloads,
        )
    )
    if seed:
        _SEED_REQUEST_IDS.add(req["request_id"])


def _load() -> tuple[dict[str, PartListing], list[ProcurementRequest]]:
    global _PARTS, _REQUESTS
    if _PARTS is None or _REQUESTS is None:
        _SEED_REQUEST_IDS.clear()
        _SEED_PART_IDS.clear()
        raw = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
        requests: list[ProcurementRequest] = []
        parts: dict[str, PartListing] = {}
        for req in raw["requests"]:
            _ingest_request(req, parts, requests, seed=True)
        if _USER_PATH.exists():
            overlay = json.loads(_USER_PATH.read_text(encoding="utf-8"))
            for req in overlay.get("requests") or []:
                _ingest_request(req, parts, requests, seed=False)
        _PARTS, _REQUESTS = parts, requests
    return _PARTS, _REQUESTS


def _dump_part(part: PartListing) -> dict:
    return part.model_dump()


def _persist_user() -> None:
    parts, requests = _load()
    payload: list[dict] = []
    for req in requests:
        if req.request_id not in _SEED_REQUEST_IDS:
            payload.append(
                {
                    "request_id": req.request_id,
                    "title": req.title,
                    "plant": req.plant,
                    "needed_by": req.needed_by,
                    "parts": [_dump_part(part) for part in req.parts],
                }
            )
            continue
        extra = [part for part in req.parts if part.part_id not in _SEED_PART_IDS]
        if extra:
            payload.append(
                {
                    "request_id": req.request_id,
                    "title": req.title,
                    "plant": req.plant,
                    "needed_by": req.needed_by,
                    "parts": [_dump_part(part) for part in extra],
                }
            )
    _USER_PATH.parent.mkdir(parents=True, exist_ok=True)
    _USER_PATH.write_text(json.dumps({"requests": payload}, indent=2), encoding="utf-8")
    _ = parts


def list_parts() -> list[PartListing]:
    return list(_load()[0].values())


def list_requests() -> list[ProcurementRequest]:
    return list(_load()[1])


def get_part(part_id: str) -> PartListing | None:
    return _load()[0].get(part_id)


def get_request(request_id: str) -> ProcurementRequest | None:
    return next((row for row in _load()[1] if row.request_id == request_id), None)


def add_request(req: ProcurementRequest) -> ProcurementRequest:
    """Insert a user RFQ (newest first) and persist it across API restarts."""
    parts, requests = _load()
    existing = get_request(req.request_id)
    if existing is None:
        requests.insert(0, req)
        for listing in req.parts:
            parts[listing.part_id] = listing
        _persist_user()
        return req
    for listing in req.parts:
        existing.parts.append(listing)
        parts[listing.part_id] = listing
    if req.title:
        existing.title = req.title
    if req.plant:
        existing.plant = req.plant
    if req.needed_by is not None:
        existing.needed_by = req.needed_by
    _persist_user()
    return existing
