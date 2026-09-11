# On-prem deployment

Aria is meant to run on an internal server (systemd), not as a cloud/Docker-first install. Postgres and Redis are optional; the API falls back to in-memory stores if they are unreachable.

## Backend port

The listen port is **not hardcoded**. It comes from `BACKEND_PORT` (default **8000**).

| Setting | Where | Default |
|---|---|---|
| `BACKEND_PORT` | `/etc/aria/aria.env`, process env, systemd drop-in | `8000` |
| `BACKEND_HOST` | same | `0.0.0.0` |
| `BACKEND_INTERNAL_URL` | frontend process env | `http://127.0.0.1:${BACKEND_PORT}` |
| `NEXT_PUBLIC_API_URL` | optional; leave empty to use the `/backend` rewrite | empty |

The Next.js app proxies `/backend/*` to `BACKEND_INTERNAL_URL`. Keep the frontend rewrite and the API port on the same number.

### Fallback to 8001

If something else already owns **8000**, do **not** kill it. Set:

```
BACKEND_PORT=8001
BACKEND_INTERNAL_URL=http://127.0.0.1:8001
```

in `/etc/aria/aria.env` (or the shell you use to start both processes), then restart:

```bash
sudo systemctl daemon-reload
sudo systemctl restart aria-backend
```

On this workstation, port 8000 is already used by an unrelated `auto_delete_simple_version` uvicorn. Use **8001** here.

## systemd

Unit file: `deploy/aria-backend.service`.

```bash
sudo cp deploy/aria-backend.service /etc/systemd/system/aria-backend.service
sudo mkdir -p /etc/aria
sudo cp .env.example /etc/aria/aria.env   # then edit secrets + BACKEND_PORT
sudo systemctl daemon-reload
sudo systemctl enable --now aria-backend
curl -sS http://127.0.0.1:${BACKEND_PORT:-8000}/health
```

The unit starts `python -m app.main`, which reads `BACKEND_HOST` / `BACKEND_PORT` from the environment. To change the port later without editing the unit:

```bash
sudo systemctl edit aria-backend
# [Service]
# Environment=BACKEND_PORT=8001
```

## Local start (Windows / dev)

```powershell
# backend — 8000 taken on this machine, so 8001
cd backend
$env:USE_IN_MEMORY = "true"
$env:LLM_PROVIDER = "auto"
$env:BACKEND_HOST = "127.0.0.1"
$env:BACKEND_PORT = "8001"
python -m app.main

# frontend
cd frontend
$env:BACKEND_PORT = "8001"
$env:BACKEND_INTERNAL_URL = "http://127.0.0.1:8001"
npm run dev
```

- UI: http://localhost:3000
- API: http://127.0.0.1:8001/health

## Health

`GET /health` returns `{ ok, provider, is_mock, company, port }`. `port` is the configured `BACKEND_PORT`, not a probe of the socket. `provider` is the active LLM (`openai` / `anthropic` / `azure` / `mock`). Live sessions do not silently use mock when an API key is present.
