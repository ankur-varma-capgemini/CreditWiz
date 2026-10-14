"""Journeys and the asset catalogue, read from data/journeys.json and
data/assets.json, and turned into the cards a journey shows."""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path

from .models import Asset, AssetCard, AssetRef, Journey, PersonaJourneys, Trust

_DATA_DIR = Path(
    os.environ.get("CREDITWIZ_DATA_DIR", Path(__file__).resolve().parents[2] / "data")
)
_RELOAD_SECONDS = 5.0

_AGENT_STATUS = {
    "production": "Production",
    "pilot": "Pilot",
    "beta": "Beta",
    "in_development": "In development",
    "deprecated": "Deprecated",
}
_WHO_CAN_USE = {
    "open": "All employees",
    "request": "Employees with an approved access request",
    "restricted": "Approved users named by the owning team",
}
_LEARNING_TYPE = {
    "video": "Video",
    "course": "Course",
    "guide": "Guide",
    "quick-reference": "Quick reference",
    "best-practice": "Best practice",
    "documentation": "Documentation",
    "confluence": "Confluence page",
}
# Feedback is recorded by Nexus today; nothing routes it to owners yet.
_FEEDBACK = "Recorded by Nexus. Routing to the owning team is to be confirmed."


def _first_sentence(text: str, limit: int = 160) -> str:
    sentence = re.split(r"(?<=[.!?])\s", text.strip(), maxsplit=1)[0]
    return sentence if len(sentence) <= limit else sentence[: limit - 1].rstrip() + "…"


def _read_json(name: str):
    with open(_DATA_DIR / name, encoding="utf-8") as fh:
        return json.load(fh)


class JourneyStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loaded_at = 0.0
        self._sets: list[PersonaJourneys] = []
        self._assets: dict[str, Asset] = {}

    def _refresh(self) -> None:
        now = time.monotonic()
        if now - self._loaded_at < _RELOAD_SECONDS and self._sets:
            return
        with self._lock:
            if now - self._loaded_at < _RELOAD_SECONDS and self._sets:
                return
            sets = [PersonaJourneys.model_validate(s) for s in _read_json("journeys.json")]
            assets = [Asset.model_validate(a) for a in _read_json("assets.json")]
            ids = [j.id for s in sets for j in s.journeys]
            if len(set(ids)) != len(ids):
                raise ValueError("Duplicate journey id")
            if len({a.id for a in assets}) != len(assets):
                raise ValueError("Duplicate asset id")
            self._sets = sets
            self._assets = {a.id: a for a in assets}
            self._loaded_at = now

    def for_persona(self, persona_id: str) -> PersonaJourneys | None:
        self._refresh()
        return next((s for s in self._sets if s.persona == persona_id), None)

    def journey(self, journey_id: str) -> tuple[str, Journey] | None:
        """The journey and the persona it belongs to."""
        self._refresh()
        for s in self._sets:
            for j in s.journeys:
                if j.id == journey_id:
                    return s.persona, j
        return None

    @property
    def all_journeys(self) -> list[Journey]:
        self._refresh()
        return [j for s in self._sets for j in s.journeys]

    @property
    def all_assets(self) -> dict[str, Asset]:
        self._refresh()
        return dict(self._assets)


store = JourneyStore()


class CardBuilder:
    """Resolves refs to cards for the signed-in user.

    Built once per request: it reads the learning catalogue once, and every
    record passes the same visibility rule the rest of Nexus applies. A ref
    the user may not see is left out, not shown locked.
    """

    def __init__(self) -> None:
        from ..learning.router import _load

        _, items = _load()
        self._learning = {i.id: i for i in items}

    def card(self, ref: AssetRef) -> AssetCard | None:
        kind, record_id = ref.ref.split(":", 1)
        if kind == "agent":
            return self._agent(ref, record_id)
        if kind == "learning":
            return self._learning_item(ref, record_id)
        return self._asset(ref, record_id)

    def cards(self, refs: list[AssetRef]) -> list[AssetCard]:
        return [c for c in (self.card(r) for r in refs) if c is not None]

    def _agent(self, ref: AssetRef, agent_id: str) -> AssetCard | None:
        from ..marketplace.store import store as agents

        a = agents.agent(agent_id)
        if a is None:
            return None
        return AssetCard(
            ref=ref.ref,
            kind="agent",
            title=a.name,
            summary=a.tagline,
            intent=ref.intent,
            why=ref.why,
            status=_AGENT_STATUS.get(a.status, a.status),
            provided_by=a.platform,
            action_label="View agent",
            action_url=f"/marketplace/agents/{a.id}",
            trust=Trust(
                owner_team=a.owner.team,
                owner_name=a.owner.name,
                purpose=a.problem_solved or a.tagline,
                who_can_use=_WHO_CAN_USE.get(a.access.type, ""),
                how_to_access=a.access.how,
                feedback=_FEEDBACK,
            ),
            source_kind=a.source_kind,
        )

    def _learning_item(self, ref: AssetRef, item_id: str) -> AssetCard | None:
        item = self._learning.get(item_id)
        if item is None:
            return None
        return AssetCard(
            ref=ref.ref,
            kind="learning",
            title=item.title,
            summary=_first_sentence(item.description),
            intent=ref.intent,
            why=ref.why,
            status=_LEARNING_TYPE.get(item.type, item.type),
            action_label="Open",
            action_url=f"/learning/items/{item.id}",
            trust=Trust(
                owner_team=item.owner,
                purpose=_first_sentence(item.description),
                approved_on=item.reviewed_at,
                who_can_use="All employees",
                how_to_access="Open it in Learning.",
                feedback=_FEEDBACK,
            ),
            source_kind=item.source_kind,
        )

    def _asset(self, ref: AssetRef, asset_id: str) -> AssetCard | None:
        from ..permissions import visible

        asset = store.all_assets.get(asset_id)
        if asset is None or not visible(asset):
            return None
        return AssetCard(
            ref=ref.ref,
            kind=asset.kind,
            title=asset.title,
            summary=asset.summary,
            intent=ref.intent,
            why=ref.why,
            provided_by=asset.provided_by,
            action_label=asset.action_label,
            action_url=asset.action_url,
            trust=asset.trust,
            source_kind=asset.source_kind,
        )


def validate_refs() -> list[str]:
    """Refs that point at no record, as readable problems. Empty when sound.

    Checks the authored files as written, before anyone's visibility applies,
    so a ref is not reported broken just because a test user cannot see it.
    """
    from ..learning.router import _raw
    from ..marketplace.store import store as agents

    known = {
        "agent": {a.id for a in agents.all_agents},
        "learning": {i["id"] for i in _raw()["items"]},
        "asset": set(store.all_assets),
    }
    problems = []
    for journey in store.all_journeys:
        for ref in journey.assets:
            kind, record_id = ref.ref.split(":", 1)
            if record_id not in known[kind]:
                problems.append(f"{journey.id}: {ref.ref} points at nothing")
    return problems
