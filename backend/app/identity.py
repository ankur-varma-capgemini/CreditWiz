"""Who is signed in, and which persona Nexus derives for them.

    Directory / user profile        (signed-in SQL profile; demo seeds in data/user.json)
            ↓
    role + department + business unit
            ↓
    persona mapping                 (data/persona-mapping.json)
            ↓
    derived persona                 -> curation, search boosts, recommendations

The profile deliberately has no persona field. When Active Directory is wired in,
replace `load_profile()`; the mapping and everything downstream stay the same.
"""

from __future__ import annotations

import json
import os
from contextvars import ContextVar
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from . import personas as hub_personas

_DATA_DIR = Path(
    os.environ.get("CREDITWIZ_DATA_DIR", Path(__file__).resolve().parents[1] / "data")
)


class DirectoryProfile(BaseModel):
    id: str
    name: str
    first_name: str
    initials: str
    email: str = ""
    job_title: str = ""
    department: str = ""
    business_unit: str = ""
    location: str = ""
    manager: str = ""
    groups: list[str] = []


class DerivedPersona(BaseModel):
    id: str
    label: str
    derived_from: Literal["role", "department", "business_unit", "default"]
    matched_value: str
    rule: str


def _read(name: str) -> dict:
    with open(_DATA_DIR / name, encoding="utf-8") as fh:
        raw = json.load(fh)
    raw.pop("$comment", None)
    return raw


# permissions.visible() is called once per record, and each call needs the
# profile: one /api/learning request read the same row 65 times. The profile
# cannot change mid-request, so hold it for the duration of one. Reset by the
# session middleware, so nothing leaks between requests or between users.
_current: ContextVar[tuple[str, DirectoryProfile] | None] = ContextVar(
    "creditwiz_profile", default=None
)


def reset_profile_cache():
    """Returns a token the caller passes to `identity.restore(token)`."""
    return _current.set(None)


def restore(token) -> None:
    _current.reset(token)


def load_profile() -> DirectoryProfile:
    from .auth import user_id
    from .database import connect

    uid = user_id()
    cached = _current.get()
    if cached is not None and cached[0] == uid:
        return cached[1]

    with connect() as conn:
        row = conn.execute(
            "SELECT profile FROM users WHERE id=? AND active=1", (uid,)
        ).fetchone()
    if row is None:
        from fastapi import HTTPException

        raise HTTPException(401, "Account unavailable")
    profile = DirectoryProfile.model_validate(json.loads(row[0]))
    _current.set((uid, profile))
    return profile


def load_mapping() -> dict:
    return _read("persona-mapping.json")


def _label(persona_id: str) -> str:
    return next(
        (p.label for p in hub_personas.all_personas() if p.id == persona_id), persona_id
    )


def derive_persona(
    profile: DirectoryProfile, mapping: dict | None = None
) -> DerivedPersona:
    m = mapping or load_mapping()
    by_role: dict[str, str] = m.get("by_role", {})
    by_dept: dict[str, str] = m.get("by_department", {})
    title = profile.job_title.strip()
    title_l = title.lower()

    # 1. exact job title
    for role, persona in by_role.items():
        if role.lower() == title_l:
            pid = hub_personas.persona_id(persona)
            return DerivedPersona(
                id=pid,
                label=_label(pid),
                derived_from="role",
                matched_value=title,
                rule=f'job title = "{role}"',
            )
    # 2. job title contains a mapped role (e.g. "Senior Compliance Analyst")
    for role, persona in sorted(by_role.items(), key=lambda kv: -len(kv[0])):
        if role.lower() in title_l:
            pid = hub_personas.persona_id(persona)
            return DerivedPersona(
                id=pid,
                label=_label(pid),
                derived_from="role",
                matched_value=title,
                rule=f'job title contains "{role}"',
            )
    # 3. department, 4. business unit
    for source, value in (
        ("department", profile.department),
        ("business_unit", profile.business_unit),
    ):
        v_l = value.strip().lower()
        for dept, persona in sorted(by_dept.items(), key=lambda kv: -len(kv[0])):
            if v_l and (dept.lower() == v_l or dept.lower() in v_l):
                pid = hub_personas.persona_id(persona)
                return DerivedPersona(
                    id=pid,
                    label=_label(pid),
                    derived_from=source,
                    matched_value=value,
                    rule=f'{source.replace("_", " ")} matches "{dept}"',
                )  # type: ignore[arg-type]
    pid = hub_personas.persona_id(m.get("default", "Business User"))
    return DerivedPersona(
        id=pid,
        label=_label(pid),
        derived_from="default",
        matched_value="",
        rule="no mapping matched; hub default",
    )


def is_admin(profile: DirectoryProfile, mapping: dict | None = None) -> bool:
    m = mapping or load_mapping()
    return any(g in profile.groups for g in m.get("admin_groups", []))
