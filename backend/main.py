"""Vercel Services entrypoint.

Public traffic is routed at /backend/*. Depending on the rewrite config, the
function may see that prefix or a stripped path — accept both.
"""

from __future__ import annotations

from app.main import app as aria_app

app = aria_app


@app.middleware("http")
async def accept_backend_prefix(request, call_next):
    path = request.scope.get("path") or ""
    if path == "/backend" or path.startswith("/backend/"):
        stripped = path[len("/backend") :] or "/"
        request.scope["path"] = stripped
        if "raw_path" in request.scope:
            request.scope["raw_path"] = stripped.encode("utf-8")
    return await call_next(request)
