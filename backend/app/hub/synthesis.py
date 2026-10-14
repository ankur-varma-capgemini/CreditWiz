"""The reply: written by the model from what the agents found.

Every task's reply is the model's, grounded in the items the agents returned
and the job's toolkit. The catalogue's own sentence is the fallback, used
when there is nothing to write about, when the data policy keeps the request
from the model, when no model is configured, and when the model's reply does
not name something that was actually found or carries a link.
"""

from __future__ import annotations

from typing import Callable

from ..journeys import reply as templates
from ..journeys.models import AssetCard, Intent, Journey, Subject
from . import llm
from .governance import LABEL
from .models import PillarGroup, Source

_NOUN: dict[str, tuple[str, str]] = {
    "prompts": ("prompt", "prompts"),
    "marketplace": ("agent", "agents"),
    "learning": ("learning item", "learning items"),
    "community": ("person or page", "people and pages"),
}
_MAX_REPLY = 900


def _join(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def catalogue_reply(
    intent: Intent,
    journey: Journey | None,
    toolkit: list[AssetCard],
    groups: list[PillarGroup],
    searched: list[str],
) -> str:
    if journey is not None:
        return templates.compose(intent, journey, toolkit, has_journeys=True)
    if not searched:
        return "Nothing in Nexus covers that yet, which is worth knowing."
    where = _join([LABEL[p] for p in searched])
    found = [g for g in groups if g.hits]
    if not found:
        return f"I searched {where}, and nothing covers that yet, which is worth knowing."
    counts = [f"{len(g.hits)} {_NOUN[g.pillar][len(g.hits) != 1]}" for g in found]
    return f"I searched {where} and found {_join(counts)}."


def _grounded(text: str, titles: list[str]) -> bool:
    low = text.lower()
    return (
        0 < len(text) <= _MAX_REPLY
        and "http" not in low
        and not text.lstrip().startswith(("#", "-", "*"))
        and any(t.lower() in low for t in titles)
    )


class _Restore:
    """Hands streamed text on with the person's client put back where the
    model wrote a placeholder, even when "[CLI" and "ENT]" arrive apart."""

    _LONGEST = len("[CLIENT]")

    def __init__(self, subject: Subject | None, emit: Callable[[str], None]) -> None:
        self._mark = f"[{subject.kind.upper()}]" if subject else ""
        self._name = subject.name if subject else ""
        self._emit = emit
        self._held = ""

    def feed(self, chunk: str) -> None:
        text = self._held + chunk
        self._held = ""
        if self._mark:
            text = text.replace(self._mark, self._name)
            cut = text.rfind("[")
            if cut != -1 and "]" not in text[cut:] and len(text) - cut < self._LONGEST:
                text, self._held = text[:cut], text[cut:]
        if text:
            self._emit(text)

    def flush(self) -> None:
        if self._held:
            self._emit(self._held)
            self._held = ""


def reply(
    *,
    model_view: str | None,
    restore: Subject | None,
    intents: list[Intent],
    journey: Journey | None,
    toolkit: list[AssetCard],
    groups: list[PillarGroup],
    searched: list[str],
    on_delta: Callable[[str], None] | None = None,
) -> tuple[str, Source, str]:
    """The reply, who wrote it, and why.

    `model_view` is what the data policy lets the model receive, None when it
    may receive nothing. `restore` is the client to put back where the model
    saw a placeholder. `on_delta` receives the reply as it is written.
    """
    fallback = catalogue_reply(intents[0], journey, toolkit, groups, searched)
    items = [(c.kind, c.title, c.summary, None) for c in toolkit[:4]] + [
        (h.kind, h.title, h.summary, h.fit) for g in groups for h in g.hits
    ]
    if not items:
        return fallback, "rules", "Nothing was found, so there was nothing for a model to write about."
    if model_view is None:
        return fallback, "rules", "Written from the catalogue: the data policy allows no model call for this request."
    if not llm.available():
        return fallback, "rules", "Written from the catalogue: no model is configured for Nexus."

    titles = [t for _, t, _, _ in items]
    stream = _Restore(restore, on_delta) if on_delta else None
    text = llm.write(
        model_view, list(intents), journey.title if journey else None, items,
        on_delta=stream.feed if stream else None,
    )
    if stream:
        stream.flush()
    # A streamed reply that fails here is replaced on the page by the final
    # reply the caller sends after this returns.
    if text is None:
        return fallback, "rules", "Written from the catalogue: the model did not return a reply."
    if not _grounded(text, titles):
        return fallback, "rules", "Written from the catalogue: the model's reply did not stick to what was found."
    # Where the model saw [CLIENT], the person sees their client, in this session only.
    if restore is not None:
        text = text.replace(f"[{restore.kind.upper()}]", restore.name)
    why = (
        "More than one intent, so the model wrote one reply covering each."
        if len(intents) > 1
        else "The model wrote the reply from what the agents found."
    )
    return text, "claude", why
