"""Conversation intent gate: small talk answered directly, a task sent on.

Runs after UserContext and before anything that costs: no guardrails, no
model, no search, no vector retrieval. It reads the request as a person would:

    "hy", "hiii", "Hello!", "gm"                 greeting     answered here
    "how r u", "i'm good", "lol", "test"         small talk   answered here
    "thx", "ty", "thank you so much"             thanks       answered here
    "bye", "cya", "that's all"                   goodbye      answered here
    "What can you do?", "who are you"            help         Nexus's five capabilities
    "Hi, can you find me a KYC agent?"           task         "find me a KYC agent?" goes on

People greet the way they type: "hy", "hiii", "heyyy there", "helo". The
patterns take stretched and misspelled forms, and a one-word message one
letter from a greeting counts as one. A greeting in front of a request is set
aside, never taken for the request. Deciding is rules, not a model: instant,
free, and exact about what matched.

The reply is natural (natural()): one short model call, streamed, with the
person's name, role and what the conversation was about, and within the same
data policy as any request. No search runs and nothing is recommended. The
fixed replies in answer() are the fallback when no model may or can answer.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Callable

from ..journeys.intent import classify
from ..journeys.models import FollowUp, Intent
from . import llm
from .models import Capability, ConversationKind

_I = re.IGNORECASE

# ---------------------------------------------------- openings, set aside
#
# Matched at the start of the message, as typed, and removed. Each ends where
# a word does, so "Hi" is not the start of "Hiring".

_END = r"(?![\w'])"
_SEP = r"[\s,.!?;:\-~]*"
_TO = r"(?:\s+(?:there|all|everyone|team|claude|hub|buddy|friend|mate|bot))?"
_GREETING = (
    r"(?:h+i+y*a*|h+y+|h+a+i+|h+e+y+a*|h+e+i+|hel+o+w?|hal+o+|hul+o+|h+l+o+|howdy|greetings|namaste|hola"
    r"|y+o+|su+p|wa+s+u+p|good\s+(?:morning|afternoon|evening|day)"
    # A bare "Morning" greets only on its own: "Morning meeting prep" is a task.
    r"|(?:morning|afternoon|evening)(?=\s*(?:[,.!]|$)))" + _TO
)
_HOW_ARE_YOU = (
    r"(?:how\s+(?:are|r)\s*(?:you|u|ya)(?:\s+doing)?(?:\s+today)?|how\s+ru"
    r"|how(?:'s|\s+is|s)\s+(?:it|everything|life|things|your\s+day)(?:\s+going)?"
    r"|how\s+(?:have|has)\s+(?:you|u)\s+been|how\s+was\s+your\s+day|how\s+do\s+you\s+do"
    r"|hope\s+(?:you(?:'re|\s+are)|u\s+r)\s+(?:well|good|doing\s+well)|nice\s+to\s+meet\s+(?:you|u)"
    r"|wh?at'?s\s+(?:up|new)|wassup)"
)
_THANKS = (
    r"(?:thank\s*(?:you|u|ya)(?:\s+(?:so|very)\s+much)?"
    r"|th(?:a|e)?n(?:k|x)s*(?:\s+(?:a\s+lot|so\s+much|very\s+much|again|in\s+advance|a\s+ton))?"
    r"|thx|thnx|tq|ty|tysm|many\s+thanks|cheers|much\s+appreciated|appreciate\s+(?:it|that))"
)
_GOODBYE = (
    r"(?:good\s*bye+|b+y+e+(?:\s+b+y+e+)?|see\s+(?:you|u|ya)(?:\s+(?:later|soon|tomorrow))?|cya|ttyl"
    r"|that(?:'s|\s+is)\s+all(?:\s+for\s+(?:now|today))?|talk\s+(?:to\s+you\s+)?(?:later|soon)|take\s+care"
    r"|catch\s+you\s+later|have\s+a\s+(?:good|great|nice)\s+(?:day|one|evening|weekend)|good\s*night)"
)
# Reactions safe to set aside in front of a request: "OK, find me...".
_ACK = r"(?:o+k+(?:a+y+)?|cool|great|nice|awesome|perfect|alright|got\s+it|lol|haha|hmm+)"
_LEAD = re.compile(
    rf"^{_SEP}(?:(?P<greeting>{_GREETING}){_END}|(?P<small>{_HOW_ARE_YOU}){_END}"
    rf"|(?P<goodbye>{_GOODBYE}){_END}|(?P<thanks>{_THANKS}){_END}|(?P<ack>{_ACK}){_END}){_SEP}",
    _I,
)
# "Find me a KYC agent, thanks!"
_TRAIL = re.compile(
    r"(?:[\s,.;:!\-]+(?:thanks(?:\s+(?:a\s+lot|so\s+much|in\s+advance))?"
    r"|thank\s*(?:you|u)(?:\s+(?:so|very)\s+much)?|thx|ty|cheers|please|pls|plz))+[\s.!]*$",
    _I,
)
# "Can you find me...": the request starts at "find".
_POLITE = re.compile(
    r"^(?:(?:can|could|would|will)\s+(?:you|u)\s+(?:please\s+|pls\s+)?|(?:please|pls|plz)\b[\s,]*"
    r"|i\s+(?:was\s+)?wondering\s+if\s+you\s+could\s+|i'?d\s+like\s+you\s+to\s+)",
    _I,
)

# ------------------------------------------------ whole messages, answered
#
# Matched against the whole message, lower-cased, punctuation gone and any
# letter stretched past two cut back ("coooool" -> "cool", "hiiii" -> "hii").

_HELP = re.compile(
    r"(?:help(?:\s+me)?(?:\s+please)?|i\s+need\s+help|what\s+can\s+(?:you|u)\s+do(?:\s+for\s+me)?"
    r"|what\s+can\s+you\s+help(?:\s+me)?\s+with|how\s+can\s+you\s+help(?:\s+me)?|what\s+do\s+you\s+do"
    r"|what\s+can\s+i\s+(?:ask|do)(?:\s+(?:you|here))?|what\s+should\s+i\s+ask|where\s+do\s+i\s+start"
    r"|how\s+(?:does|do)\s+(?:this|you|it)\s+work|how\s+do\s+i\s+use\s+(?:this|you|the\s+(?:ai\s+)?hub)"
    r"|what\s+is\s+this|what(?:'s|\s+is)\s+the\s+(?:ai\s+)?hub|who\s+are\s+(?:you|u)|what\s+are\s+you"
    r"|what(?:'s|\s+is)\s+your\s+name|who\s+(?:made|built|created|designed)\s+you"
    r"|are\s+you\s+(?:a\s+)?(?:bot|robot|human|real|ai|person|chatgpt|claude)"
    r"|tell\s+me\s+about\s+yourself|introduce\s+yourself|show\s+me\s+what\s+you\s+can\s+do|capabilities)",
    _I,
)
# Only ever on their own: as openings they could be the start of a request.
_WHOLE: tuple[tuple[ConversationKind, str, re.Pattern[str]], ...] = (
    ("greeting", "", re.compile(r"g\s*m", _I)),
    ("goodbye", "", re.compile(r"g\s*n|later|laters", _I)),
    (
        "small_talk",
        "fun",
        re.compile(
            r"tell\s+me\s+a\s+joke|(?:say|tell\s+me)\s+something\s+funny|make\s+me\s+laugh|i'?m\s+bored"
            r"|jokes?|sing\s+(?:me\s+)?a\s+song",
            _I,
        ),
    ),
    (
        "small_talk",
        "test",
        re.compile(r"test(?:ing)?(?:\s+\d+)*|hello\s+world|ping|are\s+you\s+there|anyone\s+there|you\s+there", _I),
    ),
    (
        "small_talk",
        "wellbeing",
        re.compile(
            r"(?:i'?m\s+|i\s+am\s+|im\s+|am\s+)?(?:good|fine|ok(?:ay)?|great|well|alright|doing\s+(?:good|well|great|fine)|not\s+bad)"
            r"(?:\s+(?:thanks|thank\s+you|thx))?(?:\s+(?:and\s+)?(?:you|u|how\s+(?:are|r)\s*(?:you|u)))?",
            _I,
        ),
    ),
    (
        "small_talk",
        "reaction",
        re.compile(
            r"o+k+(?:a+y+|e+y+)?|k+|cool|great|nice|awesome|perfect|alright|all\s+right|sure|got\s+it|i\s+see"
            r"|noted|lo+l+|lmao|rofl|(?:ha)+h?|(?:he)+h?|h+m+|a+h+|o+h+|wow|yay|ye+s+|yeah|yep|no+|nope"
            r"|interesting|thumbs\s+up|fine|good",
            _I,
        ),
    ),
)
# A one-word message this close to one of these is taken for it: "helo", "thnaks".
_NEAR: dict[str, ConversationKind] = {
    "hello": "greeting",
    "hey": "greeting",
    "hiya": "greeting",
    "howdy": "greeting",
    "morning": "greeting",
    "evening": "greeting",
    "thanks": "thanks",
    "goodbye": "goodbye",
}
_NEAR_CUTOFF = 0.8
_MAX_PLEASANTRIES = 4


@dataclass(frozen=True)
class Gate:
    kind: ConversationKind
    # The pleasantry set aside before routing, as typed: "Hi", "Good morning".
    opening: str
    # What goes on to the task flow. Blank for small talk.
    task_query: str
    # They asked how the assistant is doing.
    small_talk: bool = False
    # For small talk: what kind ("wellbeing", "fun", "test", "reaction").
    topic: str = ""


def _core(text: str) -> str:
    """Lower case, no punctuation, stretched letters cut back to two."""
    text = re.sub(r"(\w)\1{2,}", r"\1\1", text.lower())
    return " ".join(re.sub(r"[^\w'\s]", " ", text).split())


def read(query: str) -> Gate:
    typed = query.strip()
    text = typed
    kinds: list[str] = []
    small = False
    for _ in range(_MAX_PLEASANTRIES):
        match = _LEAD.match(text)
        if match is None:
            break
        kind = match.lastgroup or "greeting"
        if kind == "small":
            small, kind = True, "greeting"
        kinds.append(kind)
        text = text[match.end():]
    # Everything set aside, as typed: "ok thx", "Hey, how are you".
    opening = typed[: len(typed) - len(text)].strip(" ,.!?;:-~")

    trimmed = _TRAIL.sub("", text)
    if trimmed != text and not re.search(r"\w", trimmed):
        kinds.append("thanks")
    text = trimmed
    for _ in range(2):
        text = _POLITE.sub("", text, count=1)
    # What the pleasantries left dangling at the front goes; the request's own
    # ending, a question mark or full stop, stays as typed.
    text = text.lstrip(" ,.;:-!?~").rstrip(" ,;:-~")

    core = _core(text)
    if not core:
        # Nothing but pleasantries. A goodbye outranks thanks, thanks a greeting;
        # a message of nothing at all is taken as asking what Nexus does.
        for kind in ("goodbye", "thanks", "greeting"):
            if kind in kinds:
                return Gate(kind, opening, "", small)  # type: ignore[arg-type]
        if "ack" in kinds:
            return Gate("small_talk", opening, "", small, "reaction")
        return Gate("help", opening, "", small)
    if _HELP.fullmatch(core):
        return Gate("help", opening, "", small)
    for kind, topic, pattern in _WHOLE:
        if pattern.fullmatch(core):
            return Gate(kind, opening or text, "", small, topic)
    if re.fullmatch(r"[a-z]{3,8}", core):
        near = difflib.get_close_matches(core, _NEAR, n=1, cutoff=_NEAR_CUTOFF)
        if near:
            return Gate(_NEAR[near[0]], opening or text, "", small)
    return Gate("task", opening, text, small)


# ------------------------------------------------------------------ answers

# The order Nexus's capabilities are introduced in.
_ORDER: tuple[Intent, ...] = ("learn", "find", "improve", "ask", "contribute")
_LABEL: dict[Intent, str] = {
    "learn": "Learn",
    "find": "Find",
    "improve": "Improve",
    "ask": "Ask",
    "contribute": "Contribute",
}
_WHAT: dict[Intent, str] = {
    "learn": "Courses, videos and guides for the skills your role needs.",
    "find": "Validated prompts, approved agents, and the systems your work happens in.",
    "improve": "Ways to do a task you already do faster, with AI.",
    "ask": "The experts, communities and answers behind a topic.",
    "contribute": "Share a prompt, a skill video or an agent idea, reviewed before it goes live.",
}
# Used where the persona's own examples do not cover an intent.
_EXAMPLE: dict[Intent, str] = {
    "learn": "Find a course on IFRS 9",
    "find": "Find a prompt for a covenant scan",
    "improve": "Make my portfolio review faster",
    "ask": "Who can help with sanctions screening?",
    "contribute": "Write a prompt that summarises an annual review pack",
}
_SUGGESTED = 4

# When nothing in Nexus matched a request that named no task.
NOT_FOUND = "I didn't find anything in Nexus for that. Describe the task you're working on, or try one of these."

# What the model is told about the moment, for each kind of conversation.
SITUATION: dict[str, str] = {
    "greeting": "They greeted you or asked how you are.",
    "small_talk": "They made small talk or reacted to your last reply.",
    "thanks": "They thanked you.",
    "goodbye": "They said goodbye.",
    "help": (
        "They asked who you are or what you can do. Cards listing Nexus's five capabilities, "
        "each with an example request, appear under your reply: introduce them in one sentence "
        "without listing them."
    ),
    "not_found": (
        "Their message matched nothing in Nexus's catalogue. Cards listing what Nexus can do "
        "appear under your reply."
    ),
}
_MAX_NATURAL = 600


def _fits(text: str) -> bool:
    """A conversational reply: short, plain, no links, no lists."""
    return (
        0 < len(text) <= _MAX_NATURAL
        and "http" not in text.lower()
        and not re.search(r"(?m)^\s*(?:[-*•#]|\d+[.)])\s", text)
    )


def natural(
    situation: str,
    message: str,
    first_name: str,
    role: str,
    earlier: str | None,
    on_delta: Callable[[str], None] | None = None,
) -> str | None:
    """A natural reply from the model, or None when there is no model to ask
    or its reply does not fit a conversation. `message` is what the data
    policy lets the model receive. Not cached: every message is answered afresh."""
    if not llm.available():
        return None
    text = llm.converse(message, SITUATION[situation], first_name, role, earlier, on_delta=on_delta)
    if text is None or not _fits(text):
        return None
    return text


def capabilities(examples: list[str]) -> list[Capability]:
    """The five things Nexus does, each with a request to try: the persona's
    own example for that intent where there is one."""
    return [
        Capability(
            intent=intent,
            label=_LABEL[intent],
            what=_WHAT[intent],
            example=next((e for e in examples if classify(e)[0] == intent), _EXAMPLE[intent]),
        )
        for intent in _ORDER
    ]


def answer(gate: Gate, first_name: str, examples: list[str]) -> tuple[str, list[FollowUp], list[Capability]]:
    """The direct reply to small talk, the suggestions under it, and, for
    help, the capabilities."""
    you = f", {first_name}" if first_name else ""
    suggestions = [
        FollowUp(label=e, query=e)
        for e in (examples or [_EXAMPLE[i] for i in ("find", "learn", "ask")])[:_SUGGESTED]
    ]
    if gate.kind == "help":
        return (
            "I'm the Nexus assistant, and I can help with five kinds of things across Nexus. "
            "Describe the task in your own words, or try one of these.",
            [],
            capabilities(examples),
        )
    if gate.kind == "thanks":
        return f"You're welcome{you}. Anything else I can help with?", [], []
    if gate.kind == "goodbye":
        return f"Goodbye{you}. Come back any time.", [], []
    if gate.kind == "small_talk":
        if gate.topic == "wellbeing":
            return f"Glad to hear it{you}. What can I help you with today?", suggestions, []
        if gate.topic == "fun":
            return (
                "I'll leave the jokes to your colleagues. I'm better at finding the right prompt, "
                "agent or course for the work in front of you. What are you working on?",
                suggestions,
                [],
            )
        if gate.topic == "test":
            return f"I'm here and working{you}. Tell me what you're working on and I'll find what helps.", suggestions, []
        return f"Anything else I can help with{you}?", suggestions, []
    part = re.match(r"good\s+(morning|afternoon|evening|day)", gate.opening, re.IGNORECASE)
    hello = f"Good {part.group(1).lower()}{you}!" if part else f"Hi{' ' + first_name if first_name else ''}!"
    how = " Doing well, thanks for asking." if gate.small_talk else ""
    return f"{hello}{how} How can I help you today?", suggestions, []
