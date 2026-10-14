"""TaskContext: what the person is doing right now, built per request.

Intent and activity come from intent.py. This module adds the rest: the
subject (a client or deal the request names), the task's sensitivity, and how
maturity orders the answer. Masking and what may be logged are in
hub/privacy.py. The subject lives for the conversation only; nothing here
writes to the person's profile.
"""

from __future__ import annotations

import re

from ..context.models import Maturity
from .models import Intent, Sensitivity, Subject
from .store import store

# Capitalised words that are never a client: Nexus's own vocabulary, and the
# finance acronyms a banker types. A client that is itself an acronym is still
# masked unless it is on this list, which is the safe way to be wrong.
_ACRONYMS = {
    "mufg", "ai", "kyc", "aml", "cip", "fatca", "ofac", "ubo", "rm", "fx", "esg", "crs", "sme", "hub", "i",
    "ifrs", "gaap", "cecl", "ecl", "cva", "dva", "var", "lcr", "nsfr", "rwa", "raroc", "dscr", "ebitda",
    "capex", "opex", "eps", "roe", "roa", "nim", "dcm", "ecm", "lbo", "ipo", "rfp", "cds", "clo", "irs",
    "sofr", "libor", "basel", "icaap", "ilaap", "ccar", "bcbs", "mnpi", "pd", "lgd", "ead", "sox",
    "cfo", "ceo", "cro", "coo", "crm", "tmt", "apac", "emea", "uk", "us", "eu", "sql", "api", "llm",
    "pdf", "xlsx", "csv",
}
# A reporting period, not a name: Q3, H1, FY24, CY2026.
_PERIOD = re.compile(r"(?:Q[1-4]|H[12]|FY\d{2,4}|CY\d{2,4})", re.IGNORECASE)

_NAME = r"[A-Z][\w&'.-]*(?:\s+(?:&\s+)?[A-Z][\w&'.-]*)*"
# "meeting with Starbucks", "for the Starbucks relationship", "review of Acme Holdings"
_AFTER = re.compile(
    rf"\b(?i:for|with|on|about|at|to|from|of|by|regarding|re|against|versus|vs)\s+(?:(?i:the)\s+)?({_NAME})"
)
# "the Starbucks meeting", "Acme deal"
_BEFORE = re.compile(
    rf"\b({_NAME})\s+(meeting|call|visit|review|pitch|deal|renewal|account|relationship|wallet)\b"
)
_DEAL_WORDS = {"deal", "pitch"}

_CONFIDENTIAL_CUES = (
    "confidential",
    "mnpi",
    "non-public",
    "nonpublic",
    "inside information",
    "deal team",
    "restricted list",
)


def _known_terms() -> set[str]:
    from .. import personas

    terms = set(_ACRONYMS)
    terms.update(a.title.lower() for a in store.all_assets.values())
    for journey in store.all_journeys:
        terms.add(journey.title.lower())
        terms.update(k.lower() for k in journey.keywords)
    terms.update(p.label.lower() for p in personas.all_personas())
    return terms


def _is_known(name: str, terms: set[str]) -> bool:
    low = name.lower()
    if all(w in _ACRONYMS or _PERIOD.fullmatch(w) for w in low.split()):
        return True
    word = re.compile(rf"\b{re.escape(low)}\b")
    return any(word.search(t) for t in terms)


def find_subjects(query: str) -> list[Subject]:
    """Every capitalised name in a client position that is not one of the
    hub's own words, in the order found. Rules, so they run before any model
    sees the request and can mask what it would otherwise read."""
    terms = _known_terms()
    found: list[Subject] = []
    for pattern in (_AFTER, _BEFORE):
        for match in pattern.finditer(query):
            name = match.group(1).rstrip(".'-& ")
            if name and not _is_known(name, terms) and all(s.name != name for s in found):
                deal = pattern is _BEFORE and match.group(2).lower() in _DEAL_WORDS
                found.append(Subject(name=name, kind="deal" if deal else "client"))
    return found


def extract_subject(query: str) -> Subject | None:
    """The request's subject: the first name in a client position."""
    subjects = find_subjects(query)
    return subjects[0] if subjects else None


def classify_sensitivity(query: str, subject: Subject | None) -> tuple[Sensitivity, str]:
    if subject is not None:
        return (
            "client_confidential",
            f"Names a {subject.kind}. The name is used for this conversation only and kept out of usage logs.",
        )
    low = query.lower()
    if any(cue in low for cue in _CONFIDENTIAL_CUES):
        return "confidential", "Mentions confidential material, so the request is kept out of usage logs."
    return "internal", "Names no client and no confidential material."


def maturity_rank(maturity: Maturity, intent: Intent) -> int:
    """Secondary order after what the person asked for: learning early for a
    beginner, last for someone experienced."""
    if maturity == "beginner":
        return 0 if intent == "learn" else 1
    if maturity == "experienced":
        return 1 if intent == "learn" else 0
    return 0


def ordering_note(maturity: Maturity) -> str:
    return {
        "beginner": "What you asked for first, then learning, because your maturity is inferred as beginner.",
        "experienced": "What you asked for first and learning last, because your maturity is inferred as experienced.",
        "developing": "What you asked for first, then the rest of the job in its usual order.",
    }[maturity]
