from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class AlternateQuote(BaseModel):
    vendor_id: str
    vendor_name: str
    unit_price: int


class PartListing(BaseModel):
    part_id: str
    part_name: str
    category: str
    vendor_id: str
    vendor_name: str
    vendor_quoted_unit_price: int
    quantity: int
    moq: int | None = None
    target_unit_price: int
    max_acceptable_unit_price: int  # buyer's walk-away — NEVER sent to the vendor UI
    lead_time_days: int
    payment_terms_default: str
    alternate_vendor_quotes: list[AlternateQuote] = Field(default_factory=list)
    spec_blurb: str = ""
    request_id: str
    request_title: str = ""
    plant: str = ""
    # Buyer envelopes on non-price dimensions — NEVER sent to the vendor UI
    target_lead_time_days: int | None = None
    max_acceptable_lead_time_days: int | None = None
    max_acceptable_moq: int | None = None
    preferred_payment_terms: str = "Net 60"
    fastest_payment_terms: str = "Net 30"
    min_warranty_months: int = 24


class ProcurementRequest(BaseModel):
    request_id: str
    title: str
    plant: str
    needed_by: str | None = None
    parts: list[PartListing] = Field(default_factory=list)


class PublicPartListing(BaseModel):
    """Vendor-facing listing. Target, walk-away, and alternate quotes are stripped."""

    part_id: str
    part_name: str
    category: str
    vendor_id: str
    vendor_name: str
    vendor_quoted_unit_price: int
    quantity: int
    moq: int | None = None
    lead_time_days: int
    payment_terms_default: str
    spec_blurb: str = ""
    request_id: str
    request_title: str = ""
    plant: str = ""


class NegotiationStage(str, Enum):
    GREET_AND_DISCLOSE = "greet_and_disclose"
    QUALIFY = "qualify"
    PRICE_ELIGIBILITY_CHECK = "price_eligibility_check"
    OPEN_OFFER = "open_offer"
    NEGOTIATE = "negotiate"
    AGREEMENT = "agreement"
    HANDOFF = "handoff"
    CLOSED = "closed"


class Interpretation(BaseModel):
    extracted_facts: dict = Field(default_factory=dict)
    intent: str = "small_talk"
    sentiment: str = "neutral"
    signal_confidence: str = "medium"


class InsightTurn(BaseModel):
    """SKODA-side only. Never rendered in the vendor chat."""

    round_number: int
    intent: str
    sentiment: str
    signal_confidence: str
    tactic: str | None = None
    situation: str | None = None
    reasoning: str | None = None
    extracted_facts: dict = Field(default_factory=dict)
    timestamp: datetime


class ConcessionEvent(BaseModel):
    round_number: int
    vendor_offer: int | None = None
    bot_offer: int
    justification_tactic: str
    timestamp: datetime
    reasoning: str | None = None
    interpreted_intent: str | None = None
    lead_time_days: int | None = None
    moq: int | None = None
    payment_terms: str | None = None


class NegotiationSession(BaseModel):
    session_id: str
    vendor_rep_name: str | None
    vendor_rep_contact: str | None
    part_id: str
    request_id: str
    stage: NegotiationStage
    anchor_price: int
    current_bot_offer: int
    current_vendor_offer: int | None
    concession_history: list[ConcessionEvent] = Field(default_factory=list)
    round_count: int = 0
    max_rounds: int = 5
    sentiment: str = "neutral"
    handoff_flag: bool = False
    handoff_reason: str | None = None
    payment_terms: str | None = None
    volume_commitment: str | None = None
    authorized_offer: int | None = None
    current_lead_time_days: int | None = None
    current_moq: int | None = None
    current_warranty_months: int | None = None
    last_interpretation: Interpretation | None = None
    insight_log: list[InsightTurn] = Field(default_factory=list)
    vendor_company: str | None = None
    contact_refusal_count: int = 0
    contact_followup_required: bool = False
    in_range_push_done: bool = False
    vendor_justified_floor: bool = False
    created_at: datetime
    updated_at: datetime


class HandoffRecord(BaseModel):
    session_id: str
    reason: str
    transcript_summary: str
    negotiation_summary: dict
    notified_at: datetime


class ChatMessage(BaseModel):
    role: str
    content: str
    timestamp: datetime
    validated_price: int | None = None
    tactic: str | None = None
    reasoning: str | None = None
    interpreted_intent: str | None = None
    situation: str | None = None


class StartSessionRequest(BaseModel):
    part_id: str


class StartSessionResponse(BaseModel):
    session_id: str
    stage: NegotiationStage
    listing: PublicPartListing
    greeting: str
    llm_provider: str
    llm_model: str = ""


class ChatRequest(BaseModel):
    session_id: str
    message: str


class DemoVendorRequest(BaseModel):
    session_id: str
    persona: str | None = None


class AlternateQuoteDraft(BaseModel):
    vendor_id: str = ""
    vendor_name: str = ""
    unit_price: int | None = None


class RfqPartDraft(BaseModel):
    part_id: str = ""
    part_name: str = ""
    category: str = ""
    vendor_id: str = ""
    vendor_name: str = ""
    vendor_quoted_unit_price: int | None = None
    quantity: int | None = None
    moq: int | None = None
    target_unit_price: int | None = None
    max_acceptable_unit_price: int | None = None
    lead_time_days: int | None = None
    payment_terms_default: str = ""
    spec_blurb: str = ""
    target_lead_time_days: int | None = None
    max_acceptable_lead_time_days: int | None = None
    max_acceptable_moq: int | None = None
    preferred_payment_terms: str = ""
    fastest_payment_terms: str = ""
    min_warranty_months: int | None = None
    alternate_vendor_quotes: list[AlternateQuoteDraft] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


class RfqDraft(BaseModel):
    request_id: str = ""
    title: str = ""
    plant: str = ""
    needed_by: str | None = None
    parts: list[RfqPartDraft] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source: str = "form"
    filename: str | None = None


class CreateRfqRequest(BaseModel):
    request_id: str = ""
    title: str
    plant: str = "Pune"
    needed_by: str | None = None
    parts: list[RfqPartDraft]


class PublicSession(BaseModel):
    session_id: str
    stage: NegotiationStage
    part_id: str
    request_id: str
    vendor_rep_name: str | None
    current_bot_offer: int | None
    current_vendor_offer: int | None
    round_count: int
    handoff_flag: bool
    handoff_reason: str | None
    payment_terms: str | None = None
    current_lead_time_days: int | None = None
    current_moq: int | None = None
    contact_followup_required: bool = False


def to_public_listing(listing: PartListing) -> PublicPartListing:
    return PublicPartListing(
        part_id=listing.part_id,
        part_name=listing.part_name,
        category=listing.category,
        vendor_id=listing.vendor_id,
        vendor_name=listing.vendor_name,
        vendor_quoted_unit_price=listing.vendor_quoted_unit_price,
        quantity=listing.quantity,
        moq=listing.moq,
        lead_time_days=listing.lead_time_days,
        payment_terms_default=listing.payment_terms_default,
        spec_blurb=listing.spec_blurb,
        request_id=listing.request_id,
        request_title=listing.request_title,
        plant=listing.plant,
    )


def to_public_session(session: NegotiationSession) -> PublicSession:
    return PublicSession(
        session_id=session.session_id,
        stage=session.stage,
        part_id=session.part_id,
        request_id=session.request_id,
        vendor_rep_name=session.vendor_rep_name,
        current_bot_offer=session.current_bot_offer
        if session.stage
        not in {
            NegotiationStage.GREET_AND_DISCLOSE,
            NegotiationStage.QUALIFY,
            NegotiationStage.PRICE_ELIGIBILITY_CHECK,
        }
        else None,
        current_vendor_offer=session.current_vendor_offer,
        round_count=session.round_count,
        handoff_flag=session.handoff_flag,
        handoff_reason=session.handoff_reason,
        payment_terms=session.payment_terms,
        current_lead_time_days=session.current_lead_time_days,
        current_moq=session.current_moq,
        contact_followup_required=session.contact_followup_required,
    )
