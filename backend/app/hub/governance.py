"""Governance on the plan: deterministic, after the plan and before anything runs.

The guardrails (guardrails.py) settled who may see what and what the model may
receive. This enforces them on what the planner proposed:

    which pillars       only ones this person's hub shows them
    which job           only one of this persona's own
    what each pillar    the request without client details, links or
      is asked          placeholders, and without the words that only chose the pillar
    how sensitive       the stricter of the guardrails and the plan; the model
                        writes the reply only if the policy for that class allows

Every decision that changed something is written down in plain words, so the
answer can say how it was chosen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .. import data
from ..identity import is_admin, load_profile
from ..journeys.intent import match_journey
from ..journeys.models import Journey, Sensitivity
from ..text import subject_stems
from . import guardrails
from .guardrails import Guard, ModelAccess, for_retrieval, stricter
from .models import Pillar
from .planner import NAMED, PlanDraft

LABEL: dict[str, str] = {
    "prompts": "the prompt library",
    "marketplace": "Discover",
    "learning": "Learning",
    "community": "Community",
}
MAX_PILLARS = 4
_MAX_QUERY = 200
_URL = re.compile(r"https?://\S+")
# Words that say which pillar to ask, not what the request is about. Routing
# has already used them; left in, they would count against every item in a
# "half of the words" match, so "find a prompt for a covenant scan" would miss
# the covenant prompts. Only the kinds the request was routed to count as
# catalogue words: in "a course on prompt engineering", "prompt" is the topic.
_FIND_WORDS = re.compile(r"\b(?:find|show me|looking for|search for|look up)\b", re.IGNORECASE)
_KIND_WORDS = dict(NAMED)
# How a request opens, before it says what it is about.
_ASKING = re.compile(
    r"^(?:(?:i|we)\s+(?:need|want|would like|am looking for|are looking for)"
    r"|(?:is|are)\s+there|do\s+(?:we|you|i)\s+have|(?:can|could)\s+(?:you|i)(?:\s+(?:find|get|recommend|suggest))?"
    r"|please|help\s+me(?:\s+(?:find|with))?|get\s+me|give\s+me|make\s+(?:my|our)|who\s+(?:is|are|can|knows))\s+",
    re.IGNORECASE,
)
# Cues that are what the request is about, not how it is put: "what is our
# policy on gifts" is about policy.
_SUBJECT_CUES = frozenset({"policy", "allowed"})
# The small words those leave stranded at either end: "a for a covenant scan".
_FILLER = r"(?:a|an|the|and|or|for|on|in|to|with|about|of|me|some|any)"
_LEADING = re.compile(rf"^(?:{_FILLER}\s+)+", re.IGNORECASE)
_TRAILING = re.compile(rf"(?:\s+{_FILLER})+$", re.IGNORECASE)
_CLASS: dict[str, str] = {
    "public": "public",
    "internal": "internal",
    "client_confidential": "client-confidential",
    "confidential": "confidential",
}


@dataclass(frozen=True)
class Gate:
    journey: Journey | None
    carried_over: bool
    pillars: list[Pillar]
    subqueries: dict[str, str]
    reformulated: set[str]
    # What retrieval matches first: the request with client details removed.
    retrieval_query: str
    sensitivity: Sensitivity
    sensitivity_reason: str
    # What the model may receive to write the reply, under the final sensitivity.
    reply_access: ModelAccess
    reply_view: str | None
    notes: list[str]


def _clean(query: str, names: tuple[str, ...], pillars: list[Pillar], cue: str = "") -> str:
    """What a pillar is asked: no links, no client details, and none of the
    words that only chose the intent or the pillars, unless those are all the
    request has. "I need a prompt for a credit memo" asks the prompt library
    for "credit memo", and "make my portfolio review faster" asks for
    "portfolio review"."""
    text = for_retrieval(" ".join(_URL.sub(" ", query).split()), names)
    subject = _FIND_WORDS.sub(" ", text)
    if cue and cue not in _SUBJECT_CUES:
        subject = re.sub(rf"\b{re.escape(cue)}\b", " ", subject, flags=re.IGNORECASE)
    for p in pillars:
        subject = _KIND_WORDS[p].sub(" ", subject)
    subject = _ASKING.sub("", " ".join(subject.split()))
    subject = _TRAILING.sub("", _LEADING.sub("", subject))
    return (subject if subject_stems(subject) else text)[:_MAX_QUERY]


def gate(
    plan: PlanDraft,
    guard: Guard,
    journeys: list[Journey],
    earlier: str | None,
    withheld_prompts: int,
) -> Gate:
    notes: list[str] = []
    by_id = {j.id: j for j in journeys}
    journey = by_id.get(plan.activity) if plan.activity else None
    if plan.activity and journey is None:
        notes.append("The plan named a job that is not one of yours, so it was set aside.")
    carried = (
        journey is not None
        and journey.id == earlier
        and match_journey(guard.masked, journeys) is None
    )

    sensitivity = stricter(guard.sensitivity, plan.sensitivity)
    reason = guard.reason
    if sensitivity != guard.sensitivity:
        reason = plan.sensitivity_reason or "The planner judged the request more sensitive than the rules did."
    reply_access = guardrails.policy().model_access[sensitivity]
    if reply_access == "none" or guard.model_view is None:
        reply_view = None
    else:
        reply_view = guard.masked if reply_access == "masked" else guard.model_view

    shown = {p.id for p in data.PILLARS if not p.admin_only or is_admin(load_profile())}
    pillars: list[Pillar] = []
    asked = {}
    for s in plan.subqueries:
        if s.pillar in asked or len(pillars) == MAX_PILLARS:
            continue
        if s.pillar not in shown:
            notes.append(f"{LABEL[s.pillar][:1].upper()}{LABEL[s.pillar][1:]} is not available to you, so it was not searched.")
            continue
        pillars.append(s.pillar)
        asked[s.pillar] = s
    retrieval = _clean(guard.masked, guard.names, pillars, plan.cue)
    subqueries: dict[str, str] = {}
    reformulated: set[str] = set()
    for p in pillars:
        subqueries[p] = _clean(asked[p].query, guard.names, pillars, plan.cue) or retrieval
        if asked[p].reformulated and subqueries[p] != retrieval:
            reformulated.add(p)

    if withheld_prompts and "prompts" in pillars:
        notes.append("High-risk prompts are shown only to their own desk.")
    notes.append("Every result passed Nexus's access rules for your directory groups.")
    pending = "" if guard.policy_confirmed else ", a prototype default to be confirmed by MUFG's data policy"
    kind = _CLASS[sensitivity]
    if reply_access == "none":
        notes.append(f"Data policy for {kind} requests: no model call{pending}. Rules planned and wrote this answer.")
    elif guard.names or guard.identifiers:
        how = "with client names, accounts and emails masked" if guard.model_access == "masked" else "as typed"
        notes.append(f"Data policy for {kind} requests: the model receives them {how}{pending}.")
        notes.append(
            "Searches and usage logs got the request with client details masked; "
            "nothing about the client is saved to your profile."
        )

    return Gate(
        journey=journey,
        carried_over=carried,
        pillars=pillars,
        subqueries=subqueries,
        reformulated=reformulated,
        retrieval_query=retrieval,
        sensitivity=sensitivity,
        sensitivity_reason=reason,
        reply_access=reply_access,
        reply_view=reply_view,
        notes=notes,
    )
