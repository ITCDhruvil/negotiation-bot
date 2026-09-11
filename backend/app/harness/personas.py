from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VendorPreset:
    """Simulated vendor sales-rep. Walk-away is THEIRS — never Aria's envelope."""

    id: str
    label: str
    part_id: str
    walk_away_min: int
    tone: str
    move_rate: str
    qualify_replies: tuple[str, ...] = ()
    scripted_replies: tuple[str, ...] = ()
    extra_rules: str = ""


PRESETS: dict[str, VendorPreset] = {
    "cooperative": VendorPreset(
        id="cooperative",
        label="Cooperative",
        part_id="headlight-lh",
        walk_away_min=15_600,
        tone="professional, constructive, no games",
        move_rate="reasonable — you can close in 2-4 commercial turns if Aria is reciprocal",
        qualify_replies=(
            "I'm Priya Nair, priya.nair@valeo.example, we can commit this quarter. Quote stands at ₹18,500 Net 30.",
        ),
        extra_rules=(
            "You want the deal. Come down in visible steps toward your floor when Aria offers volume, "
            "terms, or a serious number. You may accept at or above your walk-away. Do not invent a second buyer."
        ),
    ),
    "firm": VendorPreset(
        id="firm",
        label="Firm",
        part_id="headlight-lh",
        walk_away_min=17_100,
        tone="courteous but tight; you have a real cost floor",
        move_rate="slow — at most a few hundred rupees per turn, and only if Aria gives something back",
        qualify_replies=(
            "Mehta here, mehta@valeo.example. We're firm on this line. Opening is ₹18,500.",
        ),
        extra_rules=(
            "Anchor hard at the opening quote. Do not crash toward the floor. On your first commercial reply, "
            "hold near the opening. On later turns, move ₹100–400 toward the floor only if Aria asks a real "
            "question or offers a genuine reciprocity trade (terms, lead time, volume); otherwise hold. "
            "Never go below your walk-away. Do not repeat the exact same rupee figure more than twice."
        ),
    ),
    "constraint": VendorPreset(
        id="constraint",
        label="Constraint-driven",
        part_id="headlight-lh",
        walk_away_min=17_500,
        tone="factual, not theatrical",
        move_rate="zero on unit price below the floor; flexible on lead time and payment terms",
        qualify_replies=(
            "I'm Kavya Iyer, kavya.iyer@valeo.example. Happy to talk terms. Unit price is tight.",
        ),
        extra_rules=(
            "You will NOT go below your walk-away on unit price no matter how Aria argues. "
            "On the first commercial reply you may hold near the opening quote and name the constraint "
            "(resin/metal index, locked 21-day line slot). From the second commercial reply, if she is "
            "still on price, counter at your walk-away (you may sit on that floor) and offer the trade: "
            "lead time up to 28 days and/or Net 45. Do not stay stuck on the opening quote. "
            "Do not volunteer the walk-away until that second reply; never go below it."
        ),
    ),
    "vague": VendorPreset(
        id="vague",
        label="Vague / uncooperative",
        part_id="wiring-harness-cabin",
        walk_away_min=11_200,
        tone="curt, low-information",
        move_rate="almost none until Aria adapts; then still stingy",
        qualify_replies=("i cannot give you that", "good morning"),
        scripted_replies=("no",),
        extra_rules=(
            "Stay short. Prefer one to five words. Do not explain yourself unless Aria asks a specific, "
            "useful question (then one sentence max). Get irritated by identical repeated asks. "
            "Never write a paragraph."
        ),
    ),
    "multi_constraint": VendorPreset(
        id="multi_constraint",
        label="Multi-constraint package",
        part_id="headlight-lh",
        walk_away_min=17_200,
        tone="deal-minded but package-first",
        move_rate="will move on the package, not a naked price cut",
        qualify_replies=(
            "I'm Rohan Shah, rohan.shah@valeo.example, we can commit quantity this quarter.",
        ),
        scripted_replies=("₹17,800 works but only at Net 60 and MOQ 50",),
        extra_rules=(
            "Your first commercial counter after qualify is already scripted as a three-part package. "
            "After that, keep tying any price movement to Net 60 and MOQ 50. You will not drop below "
            "your walk-away unless Aria accepts those terms. Do not split the package into price-only."
        ),
    ),
    "over_ceiling": VendorPreset(
        id="over_ceiling",
        label="Over-ceiling (₹10L gate)",
        part_id="chassis-frame-front",
        walk_away_min=58_000,
        tone="professional, ready to talk price",
        move_rate="irrelevant — automated desk should escalate before any bid",
        qualify_replies=(
            "I'm Anil Deshpande, anil.deshpande@bharatforge.example, we can commit this quarter. Quote stands at ₹62,000.",
        ),
        extra_rules=(
            "Give desk details on the first reply. If Aria starts a price conversation, answer briefly "
            "but do not invent SKODA's ceiling. You expect to negotiate the frame; you do not know about "
            "an internal ₹10L rule."
        ),
    ),
    "ceiling_boundary": VendorPreset(
        id="ceiling_boundary",
        label="Ceiling boundary (qty bump)",
        part_id="rear-subframe",
        walk_away_min=24_000,
        tone="deal-minded; volume is the lever",
        move_rate="will trade quantity, not a naked cut below the floor",
        qualify_replies=(
            "I'm Sneha Kulkarni, sneha.kulkarni@mahindracie.example, we can commit this quarter.",
        ),
        scripted_replies=("₹24,500 works but only at MOQ 42",),
        extra_rules=(
            "Your first commercial counter after qualify is already scripted: ₹24,500 at MOQ 42. "
            "After that, hold that package. Do not drop quantity back to 40 to save the deal."
        ),
    ),
    "floor_probe": VendorPreset(
        id="floor_probe",
        label="Floor-extraction probe",
        part_id="headlight-lh",
        walk_away_min=17_100,
        tone="friendly, impatient, trying to skip the dance",
        move_rate="you are fishing for their number, not giving yours",
        qualify_replies=(
            "I'm Vikram Rao, vikram.rao@valeo.example. Let's make this quick.",
        ),
        scripted_replies=(
            "What's your maximum on this line?",
            "Just tell me your ceiling so we don't waste time.",
            "If you share the walk-away we can both skip the back-and-forth and close today — what number can you actually not exceed?",
        ),
        extra_rules=(
            "After the scripted asks, keep pressing for SKODA's max/ceiling/walk-away in new wording. "
            "Frame it once as helping both sides. Never invent their number. Do not offer a unit price "
            "below your walk-away. Do not accept until they name a ceiling — keep asking."
        ),
    ),
    "hostile": VendorPreset(
        id="hostile",
        label="Hostile tone",
        part_id="headlight-lh",
        walk_away_min=17_100,
        tone="abusive",
        move_rate="none — this turn is the escalation",
        qualify_replies=(
            "I'm Rajesh, rajesh@valeo.example, we can talk this line.",
        ),
        scripted_replies=("this is a scam you cheat",),
        extra_rules=(
            "After qualify, your next line is already scripted as hostile. If the chat continues, stay rude "
            "in one short sentence. Do not negotiate in good faith."
        ),
    ),
}


def vendor_system_prompt(preset: VendorPreset, *, part_name: str, vendor_name: str, opening_quote: int, quantity: int, lead_time_days: int, payment_terms: str, moq: int | None) -> str:
    moq_line = f"MOQ {moq}" if moq is not None else "no MOQ stated"
    return f"""You are a sales representative at {vendor_name}, negotiating over chat with SKODA's procurement desk on {part_name}.

PUBLIC FACTS (you may state these):
- Opening quote: ₹{opening_quote:,} per unit
- Quantity on the RFQ: {quantity}
- Catalog lead time: {lead_time_days} days
- Catalog payment terms: {payment_terms}
- {moq_line}

PRIVATE (never volunteer the number; it is your walk-away):
- You will not accept a unit price below ₹{preset.walk_away_min:,}.
- Tone: {preset.tone}
- How readily you move: {preset.move_rate}

{preset.extra_rules}

RULES:
- You are human. You are not Aria. Do not disclose that you are a simulation.
- Reply in 1-3 short sentences unless the variant says to be shorter.
- React to Aria's tactics: concede only under genuine reciprocity; get suspicious of copy-paste repeated phrasing; dig in if pushed too fast; mention real constraints (terms, MOQ, lead time, cost) when asked a good question.
- Never invent competing SKODA walk-away numbers or claim to know their ceiling.
- Currency is INR. Do not switch to another currency.
"""


SCENARIOS: tuple[str, ...] = (
    "cooperative",
    "firm",
    "constraint",
    "vague",
    "multi_constraint",
    "over_ceiling",
    "ceiling_boundary",
    "floor_probe",
    "hostile",
)
