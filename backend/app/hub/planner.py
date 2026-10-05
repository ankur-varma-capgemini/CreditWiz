"""Understand the request: its intents, objective, job and needs, and what to
ask each pillar's agent.

The model reads every task and plans it. Rules read it too: their plan is the
first reading streamed while the model plans, and the plan whenever the model
may not or cannot be asked (the data policy allows no model call, no model is
configured, or the call fails). Whichever plans, the intents decide which
agents are asked: a single intent is never spread across every pillar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from ..journeys.intent import classify_all, match_journey
from ..journeys.models import Intent, Journey, Sensitivity
from . import followup, llm
from .models import Pillar, Source, SubQuery

# Which pillars answer which intent, when rules plan.
PILLARS_FOR: dict[Intent, tuple[Pillar, ...]] = {
    "find": ("prompts", "marketplace"),
    "improve": ("prompts", "marketplace"),
    "learn": ("learning",),
    "ask": ("community",),
    "contribute": ("prompts", "community"),
}
# The kinds of thing a request can name outright. For finding or improving,
# naming one is the routing: "find me a KYC agent" asks Discover, not the
# prompt library too.
_KINDS: dict[Pillar, str] = {
    "prompts": r"prompts?|templates?",
    "marketplace": r"agents?|tools?",
    # Quick references, cheat sheets, checklists and runbooks are Learning's.
    "learning": r"courses?|training|videos?|tutorials?|quick\s?references?|cheat\s?sheets?|checklists?|runbooks?",
    "community": r"experts?|communit(?:y|ies)|forums?",
}
NAMED: tuple[tuple[Pillar, re.Pattern[str]], ...] = tuple(
    (p, re.compile(rf"\b(?:{words})\b", re.IGNORECASE)) for p, words in _KINDS.items()
)
# A kind asked for as a thing, "a prompt" or "an expert", rather than used as
# a topic, as in "a course on prompt engineering".
_ASKED_FOR: tuple[tuple[Pillar, re.Pattern[str]], ...] = tuple(
    (
        p,
        re.compile(
            r"\b(?:a|an|the|any|some|my|our|which|what|good|best)\s+"
            rf"(?:(?!(?:on|for|about|in|of|with|and|to)\b)[\w-]+\s+)?(?:{words})\b",
            re.IGNORECASE,
        ),
    )
    for p, words in _KINDS.items()
)
# The intent that asking for each kind of thing carries.
_KIND_INTENT: dict[Pillar, Intent] = {"prompts": "find", "marketplace": "find", "learning": "learn", "community": "ask"}
_NARROWABLE = ("find", "improve")


def follows_up(sanitized: str) -> bool:
    """True when a request continues the conversation's job: it points back
    at it ("and who owns it?") or has no subject of its own ("who can help?").
    "Find me a compliance agent" after a question about coverage planning is a
    new request, not more of the last one. The same test decides when a
    follow-up is read with the conversation's topic (followup.py)."""
    return followup.follows_up(sanitized)


@dataclass
class PlanDraft:
    intents: list[Intent]
    # The words that decided the primary intent; blank when none did.
    cue: str
    objective: str
    # A journey id, validated by the governance gate.
    activity: str | None
    needs: list[str]
    subqueries: list[SubQuery]
    source: Source
    reason: str
    # The model's own judgement of sensitivity; the stricter one wins.
    sensitivity: Sensitivity | None = None
    sensitivity_reason: str = ""
    model: str = ""
    # True when the request's own words named the job.
    named_job: bool = field(default=False)
    # True when the model read it as conversation, not a request for work.
    small_talk: bool = False
    # True when the request named the kind of thing it wants to find, such
    # as "an agent": then only that kind is searched and recommended.
    narrowed: bool = False


def route(intents: list[Intent], sanitized: str) -> tuple[list[Pillar], bool]:
    """The pillars a request's intents call for, and whether it named the kind
    of thing it wants. Each intent asks only the places that serve it, so a
    request asks more than one kind of place only when it has more than one
    intent. For finding or improving, naming a kind is the routing: "is there
    an agent for sanctions screening" asks Discover alone, and "a course on
    prompt engineering" asks Learning alone, "prompt" there being the topic."""
    named = [p for p, pattern in NAMED if pattern.search(sanitized)]
    narrowed = bool(named) and any(i in _NARROWABLE for i in intents)
    pillars = list(
        dict.fromkeys(p for i in intents for p in (named if i in _NARROWABLE and named else PILLARS_FOR[i]))
    )
    return pillars, narrowed


def _asked_for(intents: list[Intent], cue: str, sanitized: str) -> tuple[list[Intent], str]:
    """The intents a request carries by asking for a kind of thing outright,
    and the words that asked. "I want a prompt for covenant monitoring and
    someone who knows covenants" asks for a prompt as well as a person. With no
    cue, find is only a default, and what was asked for replaces it."""
    out = list(intents) if cue else []
    first = ""
    if "contribute" not in out:  # "write a prompt" is contributing one
        for p, pattern in _ASKED_FOR:
            hit = pattern.search(sanitized)
            implied = _KIND_INTENT[p]
            if hit is None or implied in out or (implied == "find" and "improve" in out):
                continue
            out.append(implied)
            first = first or hit.group(0).lower()
    return (out, cue or first) if out else (intents, cue)


def rules_plan(sanitized: str, journeys: list[Journey], earlier: str | None, follows: bool | None = None) -> PlanDraft:
    """`follows` is whether the request as typed continues the conversation;
    judged from `sanitized` when not given. It is given when a follow-up was
    read with the conversation's topic, which `sanitized` then carries."""
    found = classify_all(sanitized)
    intents, cue = _asked_for(list(dict.fromkeys(i for i, _ in found)), found[0][1], sanitized)
    matched = match_journey(sanitized, journeys) if journeys else None
    pillars, narrowed = route(intents, sanitized)
    follows = follows_up(sanitized) if follows is None else follows
    return PlanDraft(
        intents=intents,
        cue=cue,
        objective="",
        activity=matched.id if matched else (earlier if follows else None),
        needs=[],
        subqueries=[SubQuery(pillar=p, query=sanitized, reformulated=False) for p in pillars],
        source="rules",
        reason="",
        named_job=matched is not None,
        narrowed=narrowed,
    )


def first_reading(
    masked: str, model_view: str | None, journeys: list[Journey], earlier: str | None, follows: bool | None = None
) -> PlanDraft | None:
    """The rules' plan while the model reads the request: what a streaming
    caller can show at once. None when no model call is coming, since then
    the rules' plan is the plan."""
    if model_view is None or not llm.available():
        return None
    return replace(rules_plan(masked, journeys, earlier, follows), reason="A first reading of your words, while the model plans.")


def plan(
    masked: str,
    model_view: str | None,
    persona_label: str,
    journeys: list[Journey],
    earlier: str | None,
    follows: bool | None = None,
    history: tuple[str, ...] = (),
) -> PlanDraft:
    """The model's plan for every task. It gets `model_view`, which is what
    the data policy lets it receive; rules plan instead when that is nothing,
    when no model is configured, and when the model does not return a plan.
    `history` is the conversation's earlier requests as the policy lets the
    model see them, for a follow-up to be read against."""
    rules = rules_plan(masked, journeys, earlier, follows)
    if model_view is None:
        return replace(rules, reason="Rules only: the data policy allows no model call for this request.")
    if not llm.available():
        return replace(rules, reason="Rules: no model is configured for the hub.")

    # The model hears about the last job, and the earlier requests, only when
    # this request follows them up.
    follows = follows_up(masked) if follows is None else follows
    earlier_title = next((j.title for j in journeys if j.id == earlier), None) if follows else None
    out = llm.plan(model_view, persona_label, journeys, earlier_title, history if follows else ())
    if out is None:
        return replace(rules, reason="Rules: the model did not return a plan, so rules planned it.")
    if out.small_talk:
        return replace(
            rules,
            source="claude",
            reason="The model read this as conversation, not a request for work.",
            model=llm.model(),
            small_talk=True,
        )
    why = (
        "More than one intent in one request, so the model decomposed it."
        if len(out.intents) > 1
        else "The model read the request and planned it."
    )
    # The model reads the request and may rewrite what each place is asked,
    # but which places are asked follows from the intents it found, as it
    # does for rules: a single intent is never spread across every pillar.
    pillars, narrowed = route(out.intents, masked)
    written = {s.pillar: s for s in out.subqueries}
    subqueries = [
        SubQuery(pillar=p, query=written[p].query, reformulated=written[p].reformulated)
        if p in written
        else SubQuery(pillar=p, query=masked, reformulated=False)
        for p in pillars
    ]
    passed_over = [p for p in written if p not in pillars]
    if passed_over:
        why += " Only the places its intents call for were searched."
    planned = PlanDraft(
        intents=out.intents,
        cue=rules.cue if out.intents[0] == rules.intents[0] else "",
        objective=out.objective.strip(),
        activity=out.activity,
        needs=[n.strip() for n in out.needs if n.strip()][:3],
        subqueries=subqueries,
        source="claude",
        reason=why,
        sensitivity=out.sensitivity,
        sensitivity_reason=out.sensitivity_reason.strip(),
        model=llm.model(),
        named_job=rules.named_job,
        narrowed=narrowed,
    )
    return planned
