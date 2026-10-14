"""Marketplace data source: a static JSON metadata file.

MVP: backend/data/agents.json (or the directory named by CREDITWIZ_DATA_DIR).
Two record shapes are accepted and normalised into the canonical `Agent` model:

1. The canonical template (data/agent-metadata-template.json), snake_case.
2. The simple intake format agent owners can fill quickly, camelCase, e.g.
   {"agentId": "agent-001", "name": "...", "domain": "Compliance", "useCases": [...],
    "personas": ["Compliance User"], "owner": "KYC AI Team", "status": "Production", ...}

Replacing this file with an enterprise registry later means swapping `_read_json`
and, if the shape differs, adding one more branch in `normalize_agent`.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path

from .. import personas as hub_personas
from .models import Agent, CarouselDef, Persona

_DATA_DIR = Path(
    os.environ.get("CREDITWIZ_DATA_DIR", Path(__file__).resolve().parents[2] / "data")
)
_RELOAD_SECONDS = 5.0

_STATUS_ALIASES = {
    "production": "production",
    "prod": "production",
    "live": "production",
    "ga": "production",
    "pilot": "pilot",
    "beta": "beta",
    "preview": "beta",
    "in development": "in_development",
    "in_development": "in_development",
    "development": "in_development",
    "dev": "in_development",
    "draft": "in_development",
    "deprecated": "deprecated",
    "retired": "deprecated",
}

_PERSONA_ALIASES = {
    "business user": "business_user",
    "business": "business_user",
    "compliance user": "compliance_user",
    "compliance": "compliance_user",
    "risk analyst": "risk_analyst",
    "risk": "risk_analyst",
    "operations user": "operations_user",
    "operations": "operations_user",
    "ops": "operations_user",
    "developer": "developer",
    "engineer": "developer",
}

_DOMAIN_CATEGORY = {
    "compliance": "Compliance & Risk",
    "fraud & risk": "Compliance & Risk",
    "risk": "Compliance & Risk",
    "legal": "Document Intelligence",
    "onboarding": "Customer Operations",
    "collections": "Customer Operations",
    "cards": "Customer Operations",
    "customer service": "Customer Operations",
    "operations": "Customer Operations",
    "engineering": "Developer Tools",
    "knowledge": "Knowledge & Policy",
}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _first_sentence(text: str, limit: int = 110) -> str:
    sentence = re.split(r"(?<=[.!?])\s", text.strip(), maxsplit=1)[0]
    return sentence if len(sentence) <= limit else sentence[: limit - 1].rstrip() + "…"


def _as_list(value) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [v.strip() for v in re.split(r"[;,|]", value) if v.strip()]
    return [str(v).strip() for v in value if str(v).strip()]


def _persona_id(value: str) -> str:
    """Delegates to Nexus persona module; personas are not marketplace-owned."""
    return hub_personas.persona_id(value)


def normalize_agent(raw: dict) -> dict:
    """Map either accepted shape onto the canonical field names."""
    if (
        "agentId" not in raw
        and "useCases" not in raw
        and "id" in raw
        and "business_domains" in raw
    ):
        return raw  # already canonical

    r = dict(raw)
    domains = _as_list(
        r.get("business_domains")
        or r.get("domains")
        or r.get("domain")
        or r.get("businessDomain")
    )
    description = (r.get("description") or "").strip()
    owner_raw = r.get("owner") or {}
    if isinstance(owner_raw, str):
        owner = {
            "team": r.get("team") or owner_raw,
            "name": owner_raw if r.get("team") else "",
            "email": r.get("ownerEmail", ""),
        }
    else:
        owner = {
            "team": owner_raw.get("team") or r.get("team") or "",
            "name": owner_raw.get("name", ""),
            "email": owner_raw.get("email", r.get("ownerEmail", "")),
        }
    status_key = str(r.get("status", "production")).strip().lower()
    access_raw = r.get("access") or {}
    if isinstance(access_raw, str):
        access = {
            "type": "request",
            "how": access_raw,
            "launch_url": r.get("launchUrl", ""),
            "request_url": r.get("requestUrl", ""),
        }
    else:
        access = {
            "type": access_raw.get("type")
            or r.get("accessType")
            or (
                "open"
                if r.get("launchUrl") and not r.get("accessRequirements")
                else "request"
            ),
            "how": access_raw.get("how")
            or r.get("accessRequirements")
            or "Contact the owning team for access.",
            "launch_url": access_raw.get("launch_url") or r.get("launchUrl", ""),
            "request_url": access_raw.get("request_url") or r.get("requestUrl", ""),
        }
    category = r.get("category") or next(
        (_DOMAIN_CATEGORY[d.lower()] for d in domains if d.lower() in _DOMAIN_CATEGORY),
        "Customer Operations",
    )

    return {
        "id": r.get("id") or r.get("agentId") or _slug(r["name"]),
        "name": r["name"],
        "tagline": r.get("tagline")
        or r.get("shortDescription")
        or _first_sentence(description),
        "version": str(r.get("version", "")),
        "description": description,
        "problem_solved": r.get("problem_solved") or r.get("problemSolved", ""),
        "business_domains": domains,
        "use_cases": _as_list(
            r.get("use_cases") or r.get("useCases") or r.get("businessUseCase")
        ),
        "personas": [
            _persona_id(p)
            for p in _as_list(r.get("personas") or r.get("targetPersona"))
        ],
        "capabilities": _as_list(r.get("capabilities")),
        "services": _as_list(r.get("services")),
        "example_tasks": _as_list(r.get("example_tasks") or r.get("exampleTasks")),
        "tags": _as_list(r.get("tags") or r.get("keywords")),
        "category": category,
        "platform": r.get("platform", ""),
        "tools_services": _as_list(r.get("tools_services") or r.get("tools")),
        "models": _as_list(r.get("models")),
        "architecture_pattern": r.get("architecture_pattern")
        or r.get("architecturePattern", ""),
        "owner": owner,
        "status": _STATUS_ALIASES.get(status_key, "production"),
        "access": access,
        "documentation_url": r.get("documentation_url")
        or r.get("documentationUrl", ""),
        "architecture_url": r.get("architecture_url") or r.get("architectureUrl", ""),
        "documents": r.get("documents", []),
        "created_at": r.get("created_at") or r.get("createdDate", ""),
        "updated_at": r.get("updated_at")
        or r.get("updatedDate")
        or r.get("createdDate", ""),
        "featured": bool(r.get("featured", False)),
        "popularity": int(r.get("popularity", 0) or 0),
        "audience_groups": r.get(
            "audience_groups",
            [] if r.get("source_kind") == "enterprise" else ["AI-Hub-Users"],
        ),
        "active": r.get("active", True),
        "review_status": r.get(
            "review_status",
            "draft" if r.get("source_kind") == "enterprise" else "approved",
        ),
        "source_kind": r.get("source_kind", "sample"),
    }


def _read_json(name: str):
    with open(_DATA_DIR / name, encoding="utf-8") as fh:
        return json.load(fh)


class MarketplaceStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loaded_at = 0.0
        self._agents: list[Agent] = []
        # id -> agent, derived from whichever list `_agents` currently is. A
        # separately maintained dict can drift from the list (a test that swaps
        # `_agents` proved it, leaking a hidden agent); memoising on the list's
        # identity cannot.
        self._index_for: list[Agent] | None = None
        self._index: dict[str, Agent] = {}
        self._personas: list[Persona] = []
        self._carousels: list[CarouselDef] = []

    def _refresh(self) -> None:
        now = time.monotonic()
        if now - self._loaded_at < _RELOAD_SECONDS and self._agents:
            return
        with self._lock:
            if now - self._loaded_at < _RELOAD_SECONDS and self._agents:
                return
            self._agents = [
                Agent.model_validate(normalize_agent(a))
                for a in _read_json("agents.json")
            ]
            if len({a.id for a in self._agents}) != len(self._agents):
                raise ValueError("Duplicate agent id")
            self._personas = [
                Persona.model_validate(p) for p in _read_json("personas.json")
            ]
            self._carousels = [
                CarouselDef.model_validate(c) for c in _read_json("carousels.json")
            ]
            self._loaded_at = now

    @property
    def agents(self) -> list[Agent]:
        self._refresh()
        from ..permissions import visible

        return [a for a in self._agents if visible(a)]

    @property
    def all_agents(self) -> list[Agent]:
        """Every agent, before the per-user visibility filter.

        The semantic index is shared across users, so it is built from the whole
        catalogue; `visible()` is applied to retrieved candidates instead.
        """
        self._refresh()
        return list(self._agents)

    @property
    def personas(self) -> list[Persona]:
        self._refresh()
        return self._personas

    @property
    def carousels(self) -> list[CarouselDef]:
        self._refresh()
        return self._carousels

    def _by_id(self) -> dict[str, Agent]:
        if self._index_for is not self._agents:
            self._index = {a.id: a for a in self._agents}
            self._index_for = self._agents
        return self._index

    def agent(self, agent_id: str) -> Agent | None:
        """O(1) by id. Visibility is checked on the one record, not the list."""
        self._refresh()
        from ..permissions import visible

        found = self._by_id().get(agent_id)
        return found if found is not None and visible(found) else None

    def persona(self, persona_id: str | None) -> Persona | None:
        if not persona_id:
            return None
        return next((p for p in self.personas if p.id == persona_id), None)

    def domains(self) -> list[str]:
        seen: dict[str, None] = {}
        for a in self.agents:
            for d in a.business_domains:
                seen.setdefault(d, None)
        return sorted(seen)

    def metadata_template(self) -> dict:
        return _read_json("agent-metadata-template.json")


store = MarketplaceStore()
