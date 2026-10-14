"""What the assistant says on home, written from the catalogue, never invented.

One fixed sentence per intent, filled with the names of the items the journey
recommends. Nothing here comes from a model, so a reply cannot claim an owner,
an approval or an answer that the catalogue does not hold, and it costs nothing
to produce.
"""

from __future__ import annotations

from .models import INTENTS, AssetCard, FollowUp, Intent, Journey

_WHERE_WORK_HAPPENS = {"system", "data_product"}

# One suggestion per intent, phrased so the rules in intent.py read it back as
# that intent and the journey's own title keeps the conversation on the job.
_FOLLOW_UPS: dict[Intent, tuple[str, str]] = {
    "find": ("What systems do I need?", "What systems do I need for {job}?"),
    "learn": ("How do I get better at this?", "How do I get better at {job}?"),
    "improve": ("How can I do this faster?", "How can I do {job} faster?"),
    "ask": ("Who can help?", "Who can help with {job}?"),
    "contribute": ("Share what works", "Share what works for {job}"),
}


def _job(journey: Journey) -> str:
    return journey.title[:1].lower() + journey.title[1:]


def _names(cards: list[AssetCard]) -> str:
    titles = [c.title for c in cards]
    return titles[0] if len(titles) == 1 else f"{titles[0]} and {titles[1]}"


def compose(
    intent: Intent, journey: Journey | None, cards: list[AssetCard], has_journeys: bool
) -> str:
    if journey is None:
        if has_journeys:
            return "That is not one of your mapped jobs yet, so here is what the rest of Nexus has on it."
        return "Here is what Nexus has on that."
    job = _job(journey)
    picks = [c for c in cards if c.intent == intent][:2]
    if not picks:
        return f"Here is what helps with {job}."
    names = _names(picks)
    if intent == "find":
        reply = f"For {job}, start with {names}."
        if all(c.kind in _WHERE_WORK_HAPPENS for c in picks):
            reply += " The work and the data stay in those systems; Nexus points you there."
        return reply
    if intent == "learn":
        return f"To get better at {job}, start with {names}."
    if intent == "improve":
        return f"To do {job} faster, try {names}."
    if intent == "ask":
        return f"For help with {job}, start with {names}."
    return (
        f"To share what works in {job}, use {names}. Contributions are reviewed in "
        "MUFG's existing workflow tool, not inside Nexus."
    )


def follow_ups(
    intents: list[Intent], journey: Journey | None, cards: list[AssetCard], limit: int = 3
) -> list[FollowUp]:
    """The other reasons someone might have for the same job, where the
    journey has something to offer for them."""
    if journey is None:
        return []
    job = _job(journey)
    present = {c.intent for c in cards}
    suggestions = [
        FollowUp(label=_FOLLOW_UPS[i][0], query=_FOLLOW_UPS[i][1].format(job=job))
        for i in INTENTS
        if i not in intents and i in present
    ]
    return suggestions[:limit]
