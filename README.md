# Aria — B2B Parts Procurement Negotiator (POC)

Aria is an AI assistant acting for **SKODA sourcing**. She negotiates **unit price and terms** with a vendor's sales desk over a web chat widget, in **INR**.

The LLM is the mouth. It is never the wallet.

Every rupee figure the model wants to say is proposed through a `propose_price` tool call and checked by a plain Python deal engine (`backend/app/deal_engine.py`) before it reaches the vendor. The engine has **zero LLM imports** and is unit-tested in isolation.

Aria represents the **buyer**. She opens **low**, defends a **walk-away ceiling** (`max_acceptable_unit_price`, never shown to the vendor), and tries to close **as low as possible**.

## The ₹10L rule — please confirm this threshold

The gate is applied to **order total** (`unit_price × quantity`), not to the unit price.

That matters: production automotive-part lines cross ₹10,00,000 quickly. In the mock catalog:

| Part | Quote / unit | Qty | Quoted total | Automated? |
|---|---|---|---|---|
| Headlight Assembly LH | ₹18,500 | 40 | ₹7,40,000 | yes |
| Front Brake Caliper | ₹7,200 | 80 | ₹5,76,000 | yes |
| Cabin Wiring Harness | ₹12,500 | 50 | ₹6,25,000 | yes |
| Front Chassis Frame | ₹62,000 | 20 | ₹12,40,000 | no — desk capture + handoff |
| Brake Pad Set | ₹800 | 1,500 | ₹12,00,000 | no — cheap unit, production qty |

If the intent is "AI only on small / low-risk orders," this is working as designed. If the intent is "AI on typical production RFQs," ₹10L will send most real lines to a human immediately. **Confirm before treating this as a production number.**

Walk-away unit price is never sent to the frontend.

## Architecture (unchanged shape)

```
Vendor desk  →  Next.js widget  →  FastAPI
                                   ├─ LangGraph orchestrator (persona / tactics)
                                   ├─ deal_engine.py (walk-away / ₹10L total / concessions)
                                   ├─ Redis (live session)
                                   └─ Postgres (transcripts, vendor desks, handoffs)
```

State machine: greet → qualify (vendor rep) → ₹10L eligibility → open low → negotiate → agree / hand off.

Tactics: competitive-bid leverage (real stored quotes only), volume/commitment trade, payment-terms trade, landed-cost framing, diminishing upward concessions, impasse → human.

## Local start (on-prem)

Postgres and Redis are optional. If they are not reachable, the API falls back to in-memory stores.

```bash
# backend
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
set USE_IN_MEMORY=true
set LLM_PROVIDER=auto
set COMPANY_NAME=SKODA
set BACKEND_PORT=8000
python -m app.main

# frontend
cd frontend
npm install
set BACKEND_PORT=8000
npm run dev
```

If port 8000 is already taken, set `BACKEND_PORT=8001` on **both** processes (see `DEPLOYMENT.md`). Do not kill the other listener.

- UI: http://localhost:3000
- API: http://127.0.0.1:$BACKEND_PORT/health

Leave `LLM_PROVIDER=auto` (default). If `OPENAI_API_KEY` or another real key is set, the API uses that model — it will **not** silently fall back to mock. Mock is for `pytest` only (`ARIA_ALLOW_MOCK=1`). `GET /health` and the chat header show the active provider.

OpenAI: `LLM_PROVIDER=openai` (or `auto`) + `OPENAI_API_KEY`. Commercial turns (`propose_price`) use `OPENAI_REASONING_MODEL` (default `o4-mini`) with `OPENAI_REASONING_EFFORT` (default `medium`). Streamed vendor-facing lines stay on `OPENAI_MODEL` (default `gpt-4o`) so chat stays snappy. The deal engine still validates every rupee. Claude: `LLM_PROVIDER=claude` + `ANTHROPIC_API_KEY`. Azure OpenAI: `LLM_PROVIDER=azure` + endpoint/key/deployment.

## Tests

```bash
cd backend
python -m pytest -q
```

No LLM calls.

Live negotiation harness (real model, simulated vendor personas):

```bash
cd backend
python -m app.harness
```

Requires `OPENAI_API_KEY` (or another real provider). Refuses to run on mock. Writes `backend/harness/results/last_run.txt`.

## Catalog

`backend/data/mock_catalog.json` — swap this loader for a real vendor/RFQ API later without touching negotiation logic. Multiple parts and vendors live under one `ProcurementRequest`; each chat session is still one part-vendor pair.

## Vercel (POC)

Monorepo deploy uses [Vercel Services](https://vercel.com/docs/services): Next.js at `/`, FastAPI at `/backend/*` (see root `vercel.json`).

Required project env vars:

| Name | Value |
|---|---|
| `OPENAI_API_KEY` | your key |
| `LLM_PROVIDER` | `auto` or `openai` |
| `USE_IN_MEMORY` | `true` (defaulted automatically when `VERCEL=1`) |
| `CORS_ORIGINS` | your `https://….vercel.app` origin (optional; browser uses same-origin `/backend`) |

Do **not** commit `.env`. Copy from `.env.example` locally.
