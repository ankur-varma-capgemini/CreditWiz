"""Shared user-context API. Every pillar uses these endpoints; none owns them.

ALL 9 PILLARS  ──write──>  /api/context/events, /api/context/feedback
                                    │
                           shared footprint store
                                    │
               /api/context/me  ──read──>  future personalisation
"""

from fastapi import APIRouter, HTTPException

from ..identity import derive_persona, load_profile
from . import store
from .models import (
    Ack,
    ContextSummary,
    EventIn,
    FeedbackIn,
    InterestSignal,
    UserContext,
)
from .user import build_user_context

router = APIRouter(prefix="/api/context", tags=["user context"])


@router.post("/events", response_model=Ack)
def post_event(ev: EventIn) -> Ack:
    """Record one interaction footprint from any pillar."""
    if ev.type == "learning_complete":
        raise HTTPException(
            422, "Completion events are recorded by the Learning progress endpoint"
        )
    payload = ev.model_dump()
    payload["persona"] = derive_persona(load_profile()).id
    return Ack(id=store.record_event(payload))


@router.post("/feedback", response_model=Ack)
def post_feedback(fb: FeedbackIn) -> Ack:
    """Record a 'did you find what you needed' answer from any pillar."""
    payload = fb.model_dump()
    payload["persona"] = derive_persona(load_profile()).id
    return Ack(id=store.record_feedback(payload))


@router.get("/me", response_model=UserContext)
def me() -> UserContext:
    """Who the person is, as Nexus understands them: profile, role, function,
    interests, inferred maturity and entitlements. Built in user.py.

    Interests come from footprints across every pillar. The MVP does not rank on
    them; they show what a cross-pillar personalisation service would consume.
    """
    return build_user_context()


@router.get("/interests", response_model=list[InterestSignal])
def interests() -> list[InterestSignal]:
    return [InterestSignal(**i) for i in store.derive_interests()]


@router.get("/events")
def events(limit: int = 50, pillar: str | None = None, type: str | None = None) -> list[dict]:
    """This user's own footprint trail, newest first.

    Scoped to the caller by the store, so one person cannot read another's
    trail. Useful for showing what a search actually did: the recorded meta
    carries the interpretation, the retrieval candidates and the final scores.
    """
    rows = store.events()
    if pillar:
        rows = [r for r in rows if r.get("pillar") == pillar]
    if type:
        rows = [r for r in rows if r.get("type") == type]
    return list(reversed(rows))[: max(1, min(limit, 200))]


@router.get("/summary", response_model=ContextSummary)
def summary() -> ContextSummary:
    return ContextSummary(**store.summary())
