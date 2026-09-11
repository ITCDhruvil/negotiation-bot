from __future__ import annotations

import re

from app.models import NegotiationSession

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?:\+91[\s-]?)?[6-9]\d{9}")
_NAME = re.compile(
    r"(?:i(?:['’]?m| am)|my name is|this is)\s+"
    r"([A-Za-z][A-Za-z.'-]{1,30}(?:\s+(?!from\b|at\b|with\b)[A-Za-z][A-Za-z.'-]{1,30})?)",
    re.I,
)
_NAME_HERE = re.compile(
    r"^([A-Za-z][A-Za-z.'-]{1,30})(?:\s+([A-Za-z][A-Za-z.'-]{1,30}))?\s+here\b",
    re.I,
)
_COMPANY = re.compile(
    r"\b(?:from|at|with|represent(?:ing)?|company(?:\s+is)?)\s+"
    r"([A-Za-z][A-Za-z0-9&.\-]{1,40}(?:\s+[A-Za-z][A-Za-z0-9&.\-]{1,30}){0,3})",
    re.I,
)
_ACCEPT = re.compile(
    r"\b(deal|agreed|let'?s do it|we can do that|that works|sounds good|lock it in|go ahead|accepted)\b",
    re.I,
)
_CONTACT_REFUSAL = re.compile(
    r"\b(i\s+)?(can'?t|cannot|won'?t|will not|not going to|refuse|unable to)\b.{0,48}"
    r"\b(name|email|phone|contact|number|that|personal|details|it)\b"
    r"|\b(prefer not to|won'?t share|no contact|not sharing)\b",
    re.I,
)
_COMPANY_STOP = {
    "you",
    "that",
    "this",
    "the",
    "my",
    "our",
    "a",
    "an",
    "net",
    "yes",
    "no",
}


_BARE_DECLINE = re.compile(r"^\s*(no|nope|nah|not sharing|still no)\s*[.!]?\s*$", re.I)


def looks_like_contact_refusal(text: str) -> bool:
    return bool(_CONTACT_REFUSAL.search(text or ""))


def is_bare_decline(text: str) -> bool:
    return bool(_BARE_DECLINE.match(text or ""))


def apply_qualification(session: NegotiationSession, text: str) -> NegotiationSession:
    email = _EMAIL.search(text)
    if email:
        session.vendor_rep_contact = email.group(0)
    phone = _PHONE.search(text.replace(" ", "").replace("-", ""))
    if not phone:
        phone = _PHONE.search(text)
    if phone:
        session.vendor_rep_contact = phone.group(0)

    named = _NAME.search(text)
    if named:
        session.vendor_rep_name = named.group(1).strip().title()
    elif not session.vendor_rep_name:
        here = _NAME_HERE.search(text.strip())
        if here:
            session.vendor_rep_name = " ".join(part for part in here.groups() if part).title()
        else:
            stripped = text.strip()
            words = stripped.split()
            if 1 <= len(words) <= 3 and all(word.replace(".", "").isalpha() for word in words):
                if not _ACCEPT.search(stripped) and stripped.lower() not in {
                    "yes",
                    "no",
                    "ok",
                    "net",
                    "hi",
                    "hello",
                    "hey",
                    "good morning",
                    "good afternoon",
                    "good evening",
                }:
                    session.vendor_rep_name = stripped.title()

    company = _COMPANY.search(text)
    if company:
        raw = company.group(1).strip(" .,")
        first = raw.split()[0].lower() if raw else ""
        if first not in _COMPANY_STOP:
            session.vendor_company = raw

    lowered = text.lower()
    if re.search(r"\bnet\s*60\b", lowered):
        session.payment_terms = "Net 60"
    elif re.search(r"\bnet\s*45\b", lowered):
        session.payment_terms = "Net 45"
    elif re.search(r"\bnet\s*30\b", lowered):
        session.payment_terms = "Net 30"

    if re.search(r"\b(12[- ]month|annual|blanket|longer (release|term)|higher volume)\b", lowered):
        session.volume_commitment = "extended_release"
    return session


def is_qualified(session: NegotiationSession) -> bool:
    return bool(session.vendor_rep_name and session.vendor_rep_contact)


def can_proceed_without_contact(session: NegotiationSession) -> bool:
    if session.contact_refusal_count >= 2:
        return True
    if session.contact_refusal_count >= 1 and session.vendor_rep_name and session.vendor_company:
        return True
    return False


def looks_like_acceptance(text: str) -> bool:
    return bool(_ACCEPT.search(text))
