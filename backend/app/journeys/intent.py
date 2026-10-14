"""Why someone came to Nexus, and which of their jobs they are doing.

Rules, not a model, for now: they answer instantly, can be tested, and say
exactly which words decided. This is the seam Nexus's router agent replaces
later; the response shape stays the same.
"""

from __future__ import annotations

import re

from ..text import subject_stems, word_starts
from .models import Intent, Journey

# Checked in this order: the first intent with a cue in the query wins, and
# Find is what someone wants when they say none of these. Cues are whole words
# or phrases, so "wallet share" is not a request to share something.
_CUES: tuple[tuple[Intent, tuple[str, ...]], ...] = (
    (
        "contribute",
        (
            "contribute",
            "share a",
            "share my",
            "share our",
            "share what",
            "submit",
            "publish",
            "suggest",
            "propose",
            "upload",
            "request a new",
            # Asking for a prompt to be written is contributing one.
            "write a prompt",
            "write me a prompt",
            "draft a prompt",
            "draft me a prompt",
            "create a prompt",
            "build a prompt",
            "new prompt",
        ),
    ),
    (
        "learn",
        (
            "learn",
            "how do i",
            "how to",
            "how does",
            "get better at",
            "training",
            "course",
            "tutorial",
            "guide",
            "understand",
            "what is",
            "what are",
            "explain",
        ),
    ),
    (
        "improve",
        ("improve", "faster", "quicker", "better", "automate", "speed up", "streamline", "save time", "reduce"),
    ),
    (
        "ask",
        ("who knows", "who can", "who owns", "expert", "ask", "question", "advice", "allowed", "policy"),
    ),
)


# Find is the default, so its cues only matter when a request also asks for
# something else: "find an agent for adverse media and a course on it".
_FIND_CUES = ("find", "show me", "where is", "where can i", "look up", "looking for", "search for")


def classify_all(query: str) -> list[tuple[Intent, str]]:
    """Every intent the request carries a cue for, primary first, each with
    the words that decided it. Find, with no cue, when it names none."""
    text = f" {re.sub(r'[^a-z0-9]+', ' ', query.lower()).strip()} "
    found: list[tuple[Intent, str]] = []
    for intent, cues in (*_CUES, ("find", _FIND_CUES)):
        present = [c for c in cues if f" {c} " in text]
        if present:
            found.append((intent, present[0]))
            # Words that decided one intent are not a cue for the next: "get
            # better at" is learning, not a request to do something better.
            for c in present:
                text = text.replace(f" {c} ", " ")
    return found or [("find", "")]


def classify(query: str) -> tuple[Intent, str]:
    """The intent behind a request, and the words that decided it."""
    return classify_all(query)[0]


# Words that say where to look or how to ask, never which job it is.
ROUTING_STEMS = frozenset(
    "find help prompt template agent tool cours training video tutorial expert communit forum".split()
)


def match_journey(query: str, journeys: list[Journey]) -> Journey | None:
    """The journey whose title and keywords carry most of the request's words.

    Only the words a person would use for the job count, not its description,
    so a request lands on the job it names rather than on one that mentions it.
    It must be the clear winner and carry at least half of what the request is
    about: one incidental word ("account" in a request about covenant breaches
    in management accounts) names no job, and a tie names none either.
    """
    stems = [s for s in subject_stems(query) if s not in ROUTING_STEMS]
    starts = word_starts(stems)
    needed = max(1, -(-len(stems) // 2))
    scored = sorted(
        ((sum(bool(p.search(" ".join([j.title, *j.keywords]).lower())) for p in starts), j) for j in journeys),
        key=lambda sj: -sj[0],
    )
    if not scored or scored[0][0] < needed:
        return None
    if len(scored) > 1 and scored[1][0] == scored[0][0]:
        return None
    return scored[0][1]
