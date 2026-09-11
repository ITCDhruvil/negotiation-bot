"""Live desk walkthrough: negotiate, persist reasoning, check lessons.

Run against a running API. Does not print secrets.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8001"
PART = "headlight-lh"
MAX_TURNS = 8


def _safe(text: object, n: int = 160) -> str:
    return str(text or "").replace("₹", "Rs ").encode("ascii", "replace").decode("ascii")[:n]


def _req(method: str, path: str, payload: dict | None = None, timeout: int = 90) -> dict | list | str:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode()
        if resp.headers.get_content_type() == "text/event-stream" or raw.startswith("data:"):
            return raw
        return json.loads(raw) if raw else {}


def _sse_last_session(raw: str) -> dict | None:
    session = None
    for block in raw.split("\n\n"):
        line = next((entry for entry in block.split("\n") if entry.startswith("data: ")), None)
        if not line:
            continue
        payload = json.loads(line[6:])
        if payload.get("type") == "session":
            session = payload.get("session")
        if payload.get("type") == "error":
            raise RuntimeError(payload.get("message") or "stream error")
    return session


def main() -> int:
    health = _req("GET", "/health")
    print("HEALTH", health.get("provider"), health.get("chat_model"), health.get("reasoning_model"), "mock=", health.get("is_mock"))
    if health.get("is_mock"):
        print("FAIL live desk is on mock")
        return 1

    started = _req("POST", "/api/sessions", {"part_id": PART})
    session_id = started["session_id"]
    print("SESSION", session_id, "model", started.get("llm_model"), "greet", _safe(started.get("greeting"), 90))

    latest = {"stage": started.get("stage"), "session_id": session_id}
    for i in range(MAX_TURNS):
        if latest.get("stage") in {"closed", "handoff", "agreement"}:
            break
        vendor = _req("POST", "/api/demo/vendor-turn", {"session_id": session_id})
        print(f"VENDOR {i+1} done={vendor.get('done')} {_safe(vendor.get('text'), 110)}")
        if vendor.get("done") or not (vendor.get("text") or "").strip():
            break
        raw = _req(
            "POST",
            "/api/chat/stream",
            {"session_id": session_id, "message": vendor["text"]},
            timeout=120,
        )
        latest = _sse_last_session(str(raw)) or latest
        print(f"ARIA   {i+1} stage={latest.get('stage')} bid={latest.get('current_bot_offer')} ask={latest.get('current_vendor_offer')}")

    log = _req("GET", f"/api/sessions/{session_id}/log")
    turns = log.get("turns") or []
    insights = log.get("insights") or []
    assistant = [row for row in turns if row.get("role") == "assistant"]
    reasoned = [row for row in assistant if row.get("reasoning")]
    print("LOG turns", len(turns), "assistant", len(assistant), "with_reasoning", len(reasoned), "insights", len(insights))
    if reasoned:
        sample = reasoned[-1]
        print("REASONING_SAMPLE", sample.get("situation") or "-", sample.get("tactic") or "-", _safe(sample.get("reasoning"), 180))
        print("PAIRED_REPLY", _safe(sample.get("content"), 140))

    lessons = _req("GET", "/api/lessons", None)
    if isinstance(lessons, dict):
        rows = lessons.get("lessons") or []
    else:
        rows = []
    mine = [row for row in rows if row.get("session_id") == session_id]
    print("LESSONS_TOTAL", len(rows), "THIS_SESSION", len(mine))
    if mine:
        print("LESSON", mine[0].get("outcome"), mine[0].get("situation"), _safe(mine[0].get("note"), 160))

    second = _req("POST", "/api/sessions", {"part_id": PART})
    reused = _req("GET", "/api/lessons")
    reused_rows = reused.get("lessons") if isinstance(reused, dict) else []
    print("LEARNING_REUSE", "yes" if reused_rows else "no", "count", len(reused_rows or []))
    print("SECOND_SESSION", second.get("session_id"), "opened")

    ok = bool(session_id and assistant and (reasoned or insights) and rows)
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
