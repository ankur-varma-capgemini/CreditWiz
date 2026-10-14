"""UserContext: who the person is, as Nexus understands them.

Stable across a session: role (the persona), function, interests, an inferred
maturity and entitlements. It is a profile, not a memory. What someone is doing
right now is TaskContext, built per request in journeys/task.py.
"""

from __future__ import annotations

from .. import personas as hub_personas
from ..identity import derive_persona, load_profile
from . import store
from .models import InterestSignal, Maturity, UserContext


def infer_maturity() -> tuple[Maturity, str]:
    """A first, labelled inference from learning progress alone. Repeat use,
    familiarity with tools, contribution history or declared proficiency can
    join it later; the basis string says what it rests on today."""
    from ..learning.router import my_learning

    progress = my_learning()
    if progress.completed == 0:
        level: Maturity = "beginner"
    elif progress.required_total and progress.required_completed >= progress.required_total:
        level = "experienced"
    else:
        level = "developing"
    basis = (
        f"Inferred from learning progress: {progress.required_completed} of "
        f"{progress.required_total} required items and {progress.completed} items in all completed."
    )
    return level, basis


def build_user_context(persona: hub_personas.Persona | None = None) -> UserContext:
    """`persona` is an admin's preview of another role; the rest of the
    context is still the person's own."""
    profile = load_profile()
    derived = derive_persona(profile)
    if persona is not None and persona.id != derived.id:
        role_id, role_label, rule = persona.id, persona.label, "admin preview of this role"
    else:
        role_id, role_label, rule = derived.id, derived.label, derived.rule
    role = hub_personas.get(role_id)
    level, basis = infer_maturity()
    evs = store.events()
    return UserContext(
        user_id=profile.id,
        display_name=profile.name,
        job_title=profile.job_title,
        department=profile.department,
        business_unit=profile.business_unit,
        persona=role_id,
        persona_label=role_label,
        persona_rule=rule,
        function=", ".join(v for v in (profile.department, profile.business_unit) if v),
        role_interests=role.interests.domains if role else [],
        interests=[InterestSignal(**i) for i in store.derive_interests()],
        maturity=level,
        maturity_basis=basis,
        entitlements=list(profile.groups),
        event_count=len(evs),
        pillars_seen=sorted({e.get("pillar", "hub") for e in evs}),
    )
