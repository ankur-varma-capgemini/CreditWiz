"""Follow-ups, read with the conversation they continue.

"Is there a quick reference for it too?" means nothing on its own. The page
sends the conversation's earlier requests with each new one (session context,
held in the browser and never stored here), and a request that continues them
is read with the topic of the latest one that had a topic:

    Find a course on IFRS 9                 topic "IFRS 9"
    Is there a quick reference for it too?  read as "... too? — IFRS 9"
    And who can help with that?             read as "... that? — IFRS 9"

A request continues the conversation when it points back ("it", "that",
"them", "the same"), opens as a continuation ("what about", "and for"), or
names no topic of its own ("any agents too?"). The topic is carried across
when it names none, or points straight back with "it" or "them" and says
little else ("who owns it?", "make it faster"). A request with a topic of its
own keeps it ("an agent that screens sanctions"), and the planner hears the
earlier requests to read what "the same" means.

A topic is the earlier request's own words, from its first topic word to its
last, where a topic word says what the request is about rather than where to
look ("course", "agent"), what kind of thing is wanted ("quick reference") or
how it was asked ("find", "too"). Routing words are never carried, so adding
a topic changes what is searched for, never where. Rules only: instant, and
the same with or without a model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..journeys.intent import ROUTING_STEMS
from ..text import STOP_WORDS, stem
from . import conversation

# What kind of thing is wanted, not what it is about.
_KIND = frozenset(
    "course courses training video videos tutorial tutorials guide guides reference references "
    "checklist checklists cheatsheet cheatsheets runbook runbooks doc docs document documents "
    "documentation overview summary example examples sample samples walkthrough walkthroughs "
    "path paths module modules article articles faq faqs template templates prompt prompts tool "
    "tools expert experts person people someone anyone team teams contact contacts community "
    "communities forum forums resource resources material materials".split()
)
# Words a follow-up leans on that say nothing about its topic.
_FILLER = frozenset("too also else more other another again instead anything something similar related quick good best".split())
# Points back at what the conversation was on.
_BACK = re.compile(r"\b(?:this|that|it|its|them|these|those|same)\b", re.IGNORECASE)
# Points straight back. "This" and "that" are often not pointing at all: "this
# quarter", "an agent that screens".
_STRAIGHT_BACK = re.compile(r"\b(?:it|its|them|these|those)\b", re.IGNORECASE)
# How many words of its own a request pointing straight back can have and
# still be about the earlier topic: "who owns it?", "make it faster".
_FEW = 2
# Opens as a continuation of the last request.
_CONTINUES = re.compile(r"^\s*(?:and|also|plus|now|what\s+about|how\s+about|same\s+for)\b", re.IGNORECASE)
# A short code or number that belongs to the word before it: "IFRS 9", "Form W-8".
_CODE = re.compile(r"[A-Za-z0-9-]{1,5}")
_TOPIC_CHARS = 80
_HISTORY = 6


def _word(token: str) -> str:
    return re.sub(r"[^\w-]", "", token).lower()


def _is_topic(token: str) -> bool:
    word = _word(token)
    return (
        len(word) > 2
        and word not in STOP_WORDS
        and word not in _KIND
        and word not in _FILLER
        and stem(word) not in ROUTING_STEMS
    )


def own_topic(request: str) -> bool:
    """True when the request names something it is about."""
    return any(_is_topic(t) for t in request.split())


def follows_up(request: str) -> bool:
    """True when the request continues the conversation rather than starting
    a new one: it points back, opens as a continuation, or names no topic."""
    return bool(_BACK.search(request) or _CONTINUES.match(request)) or not own_topic(request)


def topic(request: str) -> str:
    """What a request is about, in its own words: "IFRS 9" from "Find a course
    on IFRS 9", "sanctions screening" from "Who can help with sanctions screening?"."""
    tokens = request.split()
    marks = [i for i, t in enumerate(tokens) if _is_topic(t)]
    if not marks:
        return ""
    first, last = marks[0], marks[-1]
    while last + 1 < len(tokens):
        code = tokens[last + 1].strip(",.;:?!")
        if not _CODE.fullmatch(code) or _word(code) in STOP_WORDS or not any(c.isdigit() or c.isupper() for c in code):
            break
        last += 1
    phrase = " ".join(tokens[first : last + 1]).strip(" ,.;:?!")
    if len(phrase) > _TOPIC_CHARS:
        phrase = phrase[:_TOPIC_CHARS].rsplit(" ", 1)[0]
    return phrase


@dataclass(frozen=True)
class Reading:
    # What the hub works from: the request, with the earlier topic when it
    # continues the conversation and names none of its own.
    text: str
    # The topic carried over, as typed; blank when none was.
    topic: str
    # The request continues the conversation, judged from its own words: the
    # job it was on carries over, and the planner hears the earlier requests.
    follows_up: bool
    # The conversation's earlier requests, oldest first, without small talk.
    earlier: tuple[str, ...]


def read(request: str, history: list[str]) -> Reading:
    follows = follows_up(request)
    # What was small talk then ("thanks") carries no topic now.
    earlier = tuple(
        gate.task_query
        for gate in (conversation.read(h) for h in history[-_HISTORY:] if h.strip())
        if gate.kind == "task" and gate.task_query
    )
    own = [t for t in request.split() if _is_topic(t)]
    about_earlier = not own or (bool(_STRAIGHT_BACK.search(request)) and len(own) <= _FEW)
    if not earlier or not follows or not about_earlier:
        return Reading(request, "", follows, earlier)
    # The latest earlier request with a topic of its own: a chain of
    # follow-ups ("any agents for it?") leads back to the one that set it.
    carried = next((t for t in (topic(e) for e in reversed(earlier)) if t), "")
    if not carried:
        return Reading(request, "", follows, earlier)
    return Reading(f"{request.rstrip()} — {carried}", carried, follows, earlier)
