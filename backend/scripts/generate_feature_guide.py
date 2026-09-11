"""Generate docs/Aria_Feature_Guide.pdf — product + ops dashboards.

Run from repo root:
    pip install reportlab
    python backend/scripts/generate_feature_guide.py
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "docs" / "Aria_Feature_Guide.pdf"

PIT = HexColor("#14181F")
BONE = HexColor("#EEEAE2")
AMBER = HexColor("#E09A3D")
STITCH = HexColor("#8A6A4B")
INK = HexColor("#1A1714")
CEILING = HexColor("#C0392B")
DEAL = HexColor("#2E6B4F")


def styles():
    base = getSampleStyleSheet()
    return {
        "cover_kicker": ParagraphStyle(
            "cover_kicker",
            parent=base["Normal"],
            fontName="Times-Roman",
            fontSize=9,
            textColor=AMBER,
            letterSpacing=2,
            spaceAfter=8,
        ),
        "cover_title": ParagraphStyle(
            "cover_title",
            parent=base["Title"],
            fontName="Times-Bold",
            fontSize=32,
            leading=36,
            textColor=PIT,
            alignment=TA_LEFT,
            spaceAfter=12,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub",
            parent=base["Normal"],
            fontName="Times-Roman",
            fontSize=12,
            leading=16,
            textColor=INK,
            spaceAfter=6,
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=base["Heading1"],
            fontName="Times-Bold",
            fontSize=16,
            leading=20,
            textColor=PIT,
            spaceBefore=16,
            spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontName="Times-Bold",
            fontSize=12,
            leading=16,
            textColor=STITCH,
            spaceBefore=12,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["Normal"],
            fontName="Times-Roman",
            fontSize=10,
            leading=14,
            textColor=INK,
            spaceAfter=6,
        ),
        "mono": ParagraphStyle(
            "mono",
            parent=base["Normal"],
            fontName="Courier",
            fontSize=8,
            leading=11,
            textColor=PIT,
            spaceAfter=4,
        ),
        "caption": ParagraphStyle(
            "caption",
            parent=base["Normal"],
            fontName="Times-Italic",
            fontSize=9,
            leading=12,
            textColor=STITCH,
            spaceAfter=8,
        ),
        "footer": ParagraphStyle(
            "footer",
            parent=base["Normal"],
            fontName="Times-Roman",
            fontSize=8,
            textColor=STITCH,
        ),
    }


def bullets(items: list[str], style) -> ListFlowable:
    return ListFlowable(
        [ListItem(Paragraph(item, style), leftIndent=8, bulletColor=AMBER) for item in items],
        bulletType="bullet",
        start="•",
        leftIndent=14,
        bulletFontName="Times-Bold",
        bulletFontSize=10,
        spaceAfter=8,
    )


def kv_table(rows: list[tuple[str, str]], s) -> Table:
    data = [
        [Paragraph(f"<b>{key}</b>", s["body"]), Paragraph(value, s["body"])]
        for key, value in rows
    ]
    table = Table(data, colWidths=[48 * mm, 122 * mm])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LINEBELOW", (0, 0), (-1, -2), 0.3, HexColor("#C9CDD3")),
                ("BACKGROUND", (0, 0), (0, -1), HexColor("#F6F3EC")),
            ]
        )
    )
    return table


def header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(PIT)
    canvas.rect(0, A4[1] - 8 * mm, A4[0], 8 * mm, fill=1, stroke=0)
    canvas.setFillColor(AMBER)
    canvas.rect(0, A4[1] - 8 * mm, 6 * mm, 8 * mm, fill=1, stroke=0)
    canvas.setFillColor(white)
    canvas.setFont("Times-Roman", 8)
    canvas.drawString(14 * mm, A4[1] - 5.4 * mm, "ARIA  ·  SKODA SOURCING  ·  FEATURE GUIDE")
    canvas.setFillColor(STITCH)
    canvas.setFont("Times-Roman", 8)
    canvas.drawString(14 * mm, 10 * mm, "Internal SKODA document. Do not share walk-away numbers with vendors.")
    canvas.drawRightString(A4[0] - 14 * mm, 10 * mm, str(doc.page))
    canvas.restoreState()


def cover_page(canvas, doc):
    header_footer(canvas, doc)
    canvas.saveState()
    canvas.setFillColor(PIT)
    canvas.rect(0, 0, 18 * mm, A4[1], fill=1, stroke=0)
    canvas.setFillColor(AMBER)
    canvas.rect(18 * mm, 0, 3 * mm, A4[1], fill=1, stroke=0)
    canvas.restoreState()


def build() -> Path:
    s = styles()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=A4,
        leftMargin=22 * mm,
        rightMargin=16 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="Aria Feature Guide",
        author="SKODA sourcing",
        subject="Aria negotiation bot — product, ops dashboards, fine-tune, APIs",
    )
    story = []

    story.append(Paragraph("SKODA SOURCING  ·  PUNE", s["cover_kicker"]))
    story.append(Paragraph("Aria feature guide", s["cover_title"]))
    story.append(
        Paragraph(
            "Buyer-side B2B parts negotiation bot. Aria is an AI procurement assistant. "
            "She discloses that once at the start of a desk. The numbers are not AI — "
            "the deal engine owns price, the ₹10,00,000 ceiling, and walk-away.",
            s["cover_sub"],
        )
    )
    story.append(Spacer(1, 8))
    story.append(
        kv_table(
            [
                ("Product", "Aria · SKODA sourcing desk"),
                ("UI", "http://localhost:3000"),
                ("Ops", "http://localhost:3000/ops"),
                ("API", "127.0.0.1:8001 when port 8000 is taken"),
                ("Audience", "SKODA buyers and ops. Never vendor-facing."),
                ("Date", "10 September 2026"),
            ],
            s,
        )
    )
    story.append(Spacer(1, 10))
    story.append(
        Paragraph(
            "This PDF is the feature record for the product and the four ops dashboards. "
            "It is not a markdown file. Secrets, API keys, and walk-away prices are omitted on purpose.",
            s["caption"],
        )
    )

    story.append(PageBreak())
    story.append(Paragraph("1. What Aria is", s["h1"]))
    story.append(
        Paragraph(
            "Aria sits on the SKODA side of a parts RFQ. One session is one part–vendor line. "
            "She greets, qualifies the vendor contact, checks whether the quoted order total is even eligible "
            "for automated negotiation, opens with a deterministic anchor, then bargains inside a hard ceiling. "
            "If the desk cannot close inside policy she hands off to a human buyer.",
            s["body"],
        )
    )
    story.append(Paragraph("Non-negotiable product rules", s["h2"]))
    story.append(
        bullets(
            [
                "Aria is an AI and must say so once, at the start of the desk.",
                "The deal engine (<font face='Courier'>backend/app/deal_engine.py</font>) has zero LLM imports.",
                "The ₹10,00,000 gate is on order total (unit price × quantity), constant CEILING = 1,000,000.",
                "Walk-away / max acceptable is never spoken, trained, or shown to the vendor.",
                "Insights, reasoning, labels, and ops dashboards are SKODA-only.",
            ],
            s["body"],
        )
    )

    story.append(Paragraph("2. Home: Open RFQs", s["h1"]))
    story.append(
        Paragraph(
            "Route <font face='Courier'>/</font>. Lists live catalog RFQs with part, vendor, unit quote, and quoted total. "
            "If quoted total is above ₹10L the row says so before anyone opens a desk.",
            s["body"],
        )
    )
    story.append(
        kv_table(
            [
                ("Negotiate", "Opens /chat?part={id} with a live vendor. Human types on the vendor side."),
                ("Test", "Opens /chat?part={id}&demo=1. A vendor bot replies so buyers can watch Aria without a live counterpart."),
                ("Ops", "Opens the overall status dashboard at /ops."),
            ],
            s,
        )
    )
    story.append(Paragraph("Test personas (demo=1)", s["h2"]))
    story.append(
        bullets(
            [
                "headlight-lh — cooperative vendor.",
                "chassis-frame-front — over-ceiling quote; eligibility should fail automated close.",
                "rear-subframe — ceiling-boundary desk.",
                "wiring-harness-cabin — vague vendor; Aria must qualify before pricing.",
            ],
            s["body"],
        )
    )
    story.append(
        Paragraph(
            "In Test mode the composer is disabled. The UI loops vendor-bot → Aria automatically until the persona is done.",
            s["body"],
        )
    )

    story.append(Paragraph("3. Negotiation desk", s["h1"]))
    story.append(
        Paragraph(
            "Route <font face='Courier'>/chat</font>. Three columns: part dossier, chat + deal rail, SKODA insights. "
            "Header shows live vs mock model, stage, and links back to RFQs and Ops.",
            s["body"],
        )
    )
    story.append(Paragraph("Desk surfaces", s["h2"]))
    story.append(
        bullets(
            [
                "Part dossier — part name, vendor, quantity, quoted unit, spec blurb.",
                "Deal rail — vendor ask, Aria bid, stage. Numbers come from the engine, not free text.",
                "Chat — streamed Aria replies. Vendor-facing text never includes reasoning or walk-away.",
                "Insights panel — situation, tactic, sentiment, internal reasoning. SKODA only.",
                "Handoff — shown when the engine or policy requires a human buyer.",
            ],
            s["body"],
        )
    )
    story.append(Paragraph("Session stages", s["h2"]))
    story.append(
        Paragraph(
            "greet_and_disclose → qualify → price_eligibility_check → open_offer → negotiate → agreement / handoff / closed.",
            s["body"],
        )
    )

    story.append(Paragraph("4. Deal engine", s["h1"]))
    story.append(
        Paragraph(
            "Deterministic. The LLM may propose a unit price; the engine decides whether that number may be said. "
            "Aria represents the buyer: she opens low and must never agree to pay above max acceptable unit price.",
            s["body"],
        )
    )
    story.append(
        kv_table(
            [
                ("Anchor", "Opens ~8% below target, never above the vendor quote."),
                ("Concessions", "Diminishing schedule of the room between target and ceiling."),
                ("₹10L gate", "If unit × qty &gt; 1,000,000 the line is not auto-closed; handoff."),
                ("Hostile language", "Vendor abuse / fraud language can force handoff."),
                ("Hold tactics", "Named tactics the engine will not undercut on the same round."),
            ],
            s,
        )
    )

    story.append(Paragraph("5. Dual models", s["h1"]))
    story.append(
        Paragraph(
            "Commercial complete() / propose_price uses a reasoning model (default o4-mini, effort medium). "
            "Streamed vendor-facing text uses a chat model (default gpt-4o). o4-mini cannot be fine-tuned. "
            "Fine-tune target is gpt-4o-mini for voice only. If the reasoning model is unavailable that turn falls back to the chat model. "
            "GPT-5.4+ Chat Completions with tools forces reasoning_effort=none.",
            s["body"],
        )
    )
    story.append(
        Paragraph(
            "After a successful job, the promoted chat model is stored in backend/data/finetune/active_model.json "
            "and resolved_chat_model() serves it. Do not plant fake ft: models in that file.",
            s["body"],
        )
    )

    story.append(Paragraph("6. Strategy playbook and lesson memory", s["h1"]))
    story.append(
        Paragraph(
            "Each turn is classified into a situation. Coaching and a tactic that has not already failed are injected into the prompt. "
            "Aria does not train weights from this. Walk-away is never stored in a lesson.",
            s["body"],
        )
    )
    story.append(
        bullets(
            [
                "ceiling_probe — fishing for a max. Hold. Do not name a ceiling.",
                "firm_floor — vendor named a cost. One visible move or a terms trade.",
                "stalling — no price cut while they check with a manager.",
                "leadtime_gate / quality_gate — trade calendar or warranty, hold unit price.",
                "package_ask — answer terms, MOQ, lead time together.",
                "stuck_repeat — last tactic failed; change the lever.",
                "in_range_push — payable number, one push, then close.",
                "cooperative_move / ready_to_close / opening / price_fight.",
            ],
            s["body"],
        )
    )
    story.append(
        Paragraph(
            "Closed desks write a short lesson (JSON file + SQLite). Later similar desks retrieve up to three prior tactics. "
            "API: GET /api/lessons.",
            s["body"],
        )
    )

    story.append(Paragraph("7. Audit database", s["h1"]))
    story.append(
        Paragraph(
            "Always on, even with USE_IN_MEMORY=true. Local SQLite at backend/data/aria_audit.db (gitignored). "
            "Postgres dual-write happens when a pool exists. Nothing in this database is sent to the vendor.",
            s["body"],
        )
    )
    story.append(
        kv_table(
            [
                ("turns", "Every vendor and Aria message plus tactic, situation, reasoning, model."),
                ("insights", "Per-round SKODA insight snapshot."),
                ("lessons", "Reusable close notes without walk-away."),
                ("session_snapshots", "Latest public-ish session payload for live lists."),
                ("labels", "train / reject quality for fine-tune export."),
                ("ft_jobs", "OpenAI fine-tune job id, status, promoted model."),
            ],
            s,
        )
    )

    story.append(PageBreak())
    story.append(Paragraph("8. Fine-tune pipeline", s["h1"]))
    story.append(
        Paragraph(
            "Live, auto on by default. After a desk closes, and every 90 seconds in the FastAPI lifespan, the pipeline ticks. "
            "It labels closed desks, exports JSONL when asked, and at 20 train voice examples can start a supervised job on gpt-4o-mini. "
            "Pytest cannot spend money: ARIA_ALLOW_MOCK=1 blocks a live client unless force=true and a client is injected.",
            s["body"],
        )
    )
    story.append(Paragraph("Label rules (train vs reject)", s["h2"]))
    story.append(
        bullets(
            [
                "Reject if the desk is not closed / agreement.",
                "Reject if the transcript is too short to be a voice example.",
                "Reject if Aria leaked walk-away, named a ceiling, named a target, or used banned assistant phrases.",
                "Train only when the voice turns are clean. Brain/reasoning JSONL is exported separately and is not the OpenAI job.",
            ],
            s["body"],
        )
    )
    story.append(Paragraph("Controls and config", s["h2"]))
    story.append(
        kv_table(
            [
                ("OPENAI_FINETUNE_AUTO", "true — tick may submit when ready."),
                ("OPENAI_FINETUNE_BASE", "gpt-4o-mini (voice). Not o4-mini."),
                ("OPENAI_FINETUNE_MIN_EXAMPLES", "20 train voice examples."),
                ("Dedup", "Dataset fingerprint. Will not resubmit the same set."),
                ("CLI", "python -m app.finetune preview | export | tick | submit | status"),
            ],
            s,
        )
    )
    story.append(Paragraph("HTTP for the pipeline", s["h2"]))
    story.append(
        kv_table(
            [
                ("GET /api/finetune/preview", "Counts only. Does not start a job."),
                ("GET /api/finetune/status", "Labels, jobs, active chat model, readiness."),
                ("POST /api/finetune/tick", "Label, poll open job, submit if auto+ready."),
                ("POST /api/finetune/export", "Write JSONL under backend/data/finetune. No job."),
                ("POST /api/finetune/submit", "Force tick including a paid job if ready. Dashboard confirms first."),
            ],
            s,
        )
    )

    story.append(Paragraph("9. Overview dashboard", s["h1"]))
    story.append(
        Paragraph(
            "Route <font face='Courier'>/ops</font>. Overall status, health checks, and a snapshot of every other desk. "
            "Polls GET /api/ops/overview every four seconds.",
            s["body"],
        )
    )
    story.append(Paragraph("Status cards", s["h2"]))
    story.append(
        bullets(
            [
                "API — up/down, company, bind port.",
                "LLM — live provider vs mock. Mock means fixture text, not production voice.",
                "Reasoning — o4-mini (or configured). Never fine-tuned.",
                "Fine-tune — ready, or train_examples / min_examples. Auto on/off.",
                "Sessions, turns, lessons, labels — SQLite counts.",
            ],
            s["body"],
        )
    )
    story.append(Paragraph("Health checks panel", s["h2"]))
    story.append(
        bullets(
            [
                "FastAPI /health responds.",
                "Live OpenAI provider (not mock).",
                "Chat model set.",
                "Reasoning model set.",
                "Fine-tune auto tick enabled.",
                "No open fine-tune job (watch if a job is in flight).",
                "Catalog parts loaded.",
                "Audit SQLite path shown at the foot of the panel.",
            ],
            s["body"],
        )
    )
    story.append(Paragraph("Controls", s["h2"]))
    story.append(
        bullets(
            [
                "Recheck — immediate refetch of overview.",
                "Recent desks list — open the selected session on the Data dashboard.",
                "Nav — Overview, Data, Logs, Fine-tune, Open RFQs.",
            ],
            s["body"],
        )
    )

    story.append(Paragraph("10. Data dashboard", s["h1"]))
    story.append(
        Paragraph(
            "Route <font face='Courier'>/ops/data</font>. Live visibility of collected desks, lessons, and labels. "
            "Polls sessions, lessons, and labels every four seconds. Query <font face='Courier'>?session=</font> "
            "opens a desk from Overview.",
            s["body"],
        )
    )
    story.append(Paragraph("What is visible", s["h2"]))
    story.append(
        bullets(
            [
                "Counts — desks, lessons, train labels, reject labels.",
                "Filter — part, vendor, stage, session id.",
                "Session list — stage, rounds, Aria bid, vendor ask, contact name.",
                "Desk detail — turns, tactics, situations, SKODA reasoning, train/reject reasons.",
                "Playbook lessons — part, situation, outcome, tactics, note. No walk-away.",
            ],
            s["body"],
        )
    )
    story.append(Paragraph("Controls", s["h2"]))
    story.append(
        bullets(
            [
                "Refresh — pull the live feed now.",
                "Click a session — load GET /api/sessions/{id}/log.",
                "Filter field — client-side subset of the live list.",
            ],
            s["body"],
        )
    )

    story.append(Paragraph("11. Logs dashboard", s["h1"]))
    story.append(
        Paragraph(
            "Route <font face='Courier'>/ops/logs</font>. Cross-desk audit stream from GET /api/logs/recent (last 80 turns). "
            "Polls every four seconds.",
            s["body"],
        )
    )
    story.append(
        bullets(
            [
                "Cards — recent turns, assistant count, vendor count.",
                "Role filter — all / assistant / vendor.",
                "Search — content, reasoning, tactic, situation, model, session id.",
                "Each row — role, short session id, stage, model, tactic, situation, message, reasoning, timestamp.",
                "Refresh — immediate pull.",
            ],
            s["body"],
        )
    )

    story.append(Paragraph("12. Fine-tune dashboard", s["h1"]))
    story.append(
        Paragraph(
            "Route <font face='Courier'>/ops/finetune</font>. Status, controls, testing, labels, and jobs. "
            "Polls GET /api/finetune/status and GET /health every five seconds.",
            s["body"],
        )
    )
    story.append(Paragraph("Status cards", s["h2"]))
    story.append(
        bullets(
            [
                "Ready — yes, or not yet, with train_examples / min_examples.",
                "Auto — on/off. Warns if the LLM provider is mock.",
                "Chat model — current voice model, including a promoted ft: id when present.",
                "Open job — none, or OpenAI status + job id.",
                "Train labels, reject labels, valid split, skipped desks.",
            ],
            s["body"],
        )
    )
    story.append(Paragraph("Controls", s["h2"]))
    story.append(
        kv_table(
            [
                ("Tick pipeline", "POST /api/finetune/tick. Labels new desks, polls an open job, submits only if auto and ready."),
                ("Export JSONL", "POST /api/finetune/export. Writes voice.jsonl, voice_valid.jsonl, brain.jsonl, manifest.json. No paid job."),
                ("Force submit", "POST /api/finetune/submit. Disabled until ready. Confirm dialog: this spends money."),
                ("Refresh status", "GET status + health now."),
                ("Run checks", "Testing: GET /health, GET /api/finetune/status, GET /api/finetune/preview. Does not tick or submit."),
            ],
            s,
        )
    )
    story.append(Paragraph("Testing panel", s["h2"]))
    story.append(
        Paragraph(
            "Run checks reports pass/fail for Health (API up and not mock), Status (auto flag, example counts, active chat model), "
            "and Preview (train/valid/skipped). It will not start an OpenAI job. Use Tick to label. Use Force submit only when "
            "the desk is deliberately ready to spend.",
            s["body"],
        )
    )
    story.append(Paragraph("Tables", s["h2"]))
    story.append(
        bullets(
            [
                "Labels — session prefix, quality, outcome, voice example count, reject reasons.",
                "Jobs — status, job id, base model, promoted fine-tuned model, error if any.",
            ],
            s["body"],
        )
    )

    story.append(PageBreak())
    story.append(Paragraph("13. Ops navigation and visual system", s["h1"]))
    story.append(
        Paragraph(
            "All four dashboards share the sourcing-desk look. Do not invent a second visual language.",
            s["body"],
        )
    )
    story.append(
        kv_table(
            [
                ("Colors", "pit #14181F, bone #EEEAE2, amber #E09A3D, stitch #8A6A4B, ink #1A1714, ceiling #C0392B, deal #2E6B4F, fog #C9CDD3"),
                ("Type", "Syne display, Figtree sans, IBM Plex Mono"),
                ("Corners", "Sharp. Dossier, not consumer chat."),
                ("Entry", "Home Ops button, chat header Ops, /ops nav."),
            ],
            s,
        )
    )

    story.append(Paragraph("14. HTTP map (ops + product)", s["h1"]))
    story.append(
        kv_table(
            [
                ("GET /health", "Provider, mock flag, chat and reasoning models, company, port."),
                ("GET /api/catalog", "RFQs and public part listings."),
                ("POST /api/sessions", "Start a desk for a part_id."),
                ("POST /api/chat/stream", "SSE tokens, session, insights, price, done."),
                ("POST /api/demo/vendor-turn", "Vendor bot for Test mode."),
                ("GET /api/sessions/{id}", "Public session + transcript."),
                ("GET /api/sessions/{id}/insights", "SKODA insight log for a live session."),
                ("GET /api/sessions/{id}/log", "Audit turns, insights, lessons, label."),
                ("GET /api/lessons", "Playbook memory."),
                ("GET /api/labels", "All train/reject rows. Optional ?quality=."),
                ("GET /api/logs/sessions", "Session snapshots for the Data dashboard."),
                ("GET /api/logs/recent", "Last 80 turns for the Logs dashboard."),
                ("GET /api/ops/overview", "Health + counts + recent desks + pipeline snapshot."),
            ],
            s,
        )
    )
    story.append(
        Paragraph(
            "Frontend proxies /backend/:path* to the API using BACKEND_PORT or BACKEND_INTERNAL_URL. "
            "Client fetch base is NEXT_PUBLIC_API_URL or /backend.",
            s["body"],
        )
    )

    story.append(Paragraph("15. How to run", s["h1"]))
    story.append(Paragraph("Backend (port 8000 is often taken by an unrelated service — do not kill it)", s["h2"]))
    story.append(
        Paragraph(
            "cd backend<br/>"
            "$env:USE_IN_MEMORY = \"true\"<br/>"
            "$env:BACKEND_PORT = \"8001\"<br/>"
            "$env:BACKEND_HOST = \"127.0.0.1\"<br/>"
            "python -m app.main",
            s["mono"],
        )
    )
    story.append(Paragraph("Frontend", s["h2"]))
    story.append(
        Paragraph(
            "cd frontend<br/>"
            "$env:BACKEND_PORT = \"8001\"<br/>"
            "$env:BACKEND_INTERNAL_URL = \"http://127.0.0.1:8001\"<br/>"
            "npm run dev",
            s["mono"],
        )
    )
    story.append(
        Paragraph(
            "UI http://localhost:3000 · API http://127.0.0.1:8001/health · tests: cd backend; python -m pytest -q",
            s["body"],
        )
    )

    story.append(Paragraph("16. What this product does not do", s["h1"]))
    story.append(
        bullets(
            [
                "It does not fine-tune o4-mini.",
                "It does not put walk-away, target, or authorization limits in vendor chat or training voice.",
                "It does not auto-submit a paid job from Run checks or Export.",
                "It does not replace a human buyer when the ₹10L total gate trips or the engine hands off.",
                "It does not document or print OPENAI_API_KEY.",
            ],
            s["body"],
        )
    )

    story.append(Spacer(1, 12))
    story.append(
        Paragraph(
            "End of feature guide. Dashboards: /ops · /ops/data · /ops/logs · /ops/finetune.",
            s["caption"],
        )
    )

    doc.build(story, onFirstPage=cover_page, onLaterPages=header_footer)
    return OUT


if __name__ == "__main__":
    path = build()
    print(path)
