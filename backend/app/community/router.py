"""The Community pillar's API. The hub owns the page; Viva Engage owns the conversations.

    GET  /api/community                          communities, yours, suggestions, experts
    GET  /api/community/feed                     posts, newest first (?community, ?kind, ?q)
    GET  /api/community/threads/{id}             one conversation with its replies
    POST /api/community/threads/{id}/replies     reply to it
    POST /api/community/posts/{id}/like          like it
    DELETE /api/community/posts/{id}/like        take the like back

Live Viva Engage is used when the person has signed in with Microsoft (or a
developer has set tokens). If it refuses a read, the page still answers from
the sample content and says exactly why; the Integrations page keeps the
reason. A write is never redirected: it either reaches Viva Engage or says why
it did not.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from fastapi import APIRouter, HTTPException

from .. import http, integrations
from ..context import store as context_store
from ..hub import guardrails
from ..identity import load_profile
from ..permissions import resolve_persona
from . import vivaengage
from .models import CommunityHome, Feed, Post, PostKind, Reply, ReplyIn, Thread
from .sample import SampleCommunity

router = APIRouter(prefix="/api/community", tags=["community"])
T = TypeVar("T")
Source = SampleCommunity | vivaengage.VivaEngage
CLIENT_DATA = (
    "Take out client names, account numbers and email addresses before you post. "
    "Everyone in the community can read it."
)


def _read(call: Callable[[Source], T]) -> T:
    uid = load_profile().id
    try:
        if not vivaengage.configured():
            return call(SampleCommunity())
        try:
            found = call(vivaengage.VivaEngage())
        except http.ExternalError as e:
            reason = integrations.explain(e)
            integrations.record_error("viva_engage", uid, reason)
            return call(SampleCommunity(reason=f"Showing sample content because {reason}"))
        integrations.clear_error("viva_engage", uid)
        return found
    except LookupError as e:
        raise HTTPException(404, str(e)) from None


def _write(call: Callable[[Source], T]) -> tuple[T, str]:
    uid = load_profile().id
    src: Source = vivaengage.VivaEngage() if vivaengage.configured() else SampleCommunity()
    try:
        return call(src), src.connection.source
    except LookupError as e:
        raise HTTPException(404, str(e)) from None
    except http.ExternalError as e:
        reason = integrations.explain(e)
        integrations.record_error("viva_engage", uid, reason)
        raise HTTPException(502, f"Not posted: {reason}") from None


def _footprint(action: str, subject_id: str, subject_type: str, persona_id: str, source: str) -> None:
    # What was done and where, never what was written.
    context_store.record_event(
        {
            "pillar": "community",
            "type": "collaborate",
            "subject_id": subject_id,
            "subject_type": subject_type,
            "persona": persona_id,
            "topics": [],
            "meta": {"action": action, "source": source},
        }
    )


@router.get("", response_model=CommunityHome)
def home(persona: str | None = None) -> CommunityHome:
    p = resolve_persona(persona)
    uid = load_profile().id
    return _read(lambda src: src.home(p.id, uid))


@router.get("/feed", response_model=Feed)
def feed(community: str | None = None, kind: PostKind | None = None, q: str = "", persona: str | None = None) -> Feed:
    p = resolve_persona(persona)
    uid = load_profile().id
    return _read(lambda src: src.feed(p.id, uid, community, kind, q[:200]))


@router.get("/threads/{thread_id}", response_model=Thread)
def thread(thread_id: str, persona: str | None = None) -> Thread:
    p = resolve_persona(persona)
    uid = load_profile().id
    return _read(lambda src: src.thread(p.id, uid, thread_id))


@router.post("/threads/{thread_id}/replies", response_model=Reply, status_code=201)
def reply(thread_id: str, body: ReplyIn, persona: str | None = None) -> Reply:
    p = resolve_persona(persona)
    text = body.body.strip()
    if not text:
        raise HTTPException(422, "Write a reply first.")
    # The community's own rule: no client data in posts. The hub's guardrails
    # find client and deal names, account numbers and email addresses.
    guard = guardrails.check(text, None)
    if guard.names or guard.identifiers:
        raise HTTPException(422, CLIENT_DATA)
    profile = load_profile()
    made, source = _write(lambda src: src.reply(p.id, profile, thread_id, text))
    _footprint("reply", thread_id, "thread", p.id, source)
    return made


def _like(post_id: str, liked: bool, persona: str | None) -> Post:
    p = resolve_persona(persona)
    uid = load_profile().id
    post, source = _write(lambda src: src.like(p.id, uid, post_id, liked))
    _footprint("like" if liked else "unlike", post_id, "post", p.id, source)
    return post


@router.post("/posts/{post_id}/like", response_model=Post)
def like(post_id: str, persona: str | None = None) -> Post:
    return _like(post_id, True, persona)


@router.delete("/posts/{post_id}/like", response_model=Post)
def unlike(post_id: str, persona: str | None = None) -> Post:
    return _like(post_id, False, persona)
