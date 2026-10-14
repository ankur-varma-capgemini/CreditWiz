"""Prompt library and contributions API.

    GET    /api/prompts                 the library, the viewer's desk first
    POST   /api/prompts/search          the Prompts & Skills agent, asked directly
    GET    /api/prompts/templates       scaffolds for a new prompt
    GET    /api/prompts/{id}            one prompt, in full
    PUT    /api/prompts/{id}/saved      save it to My library
    DELETE /api/prompts/{id}/saved      remove it
    POST   /api/prompts/draft           a draft built from validated prompts
    POST   /api/contributions           submit a prompt, video or agent for review,
                                        and ingest it into its agent's index
    GET    /api/contributions/mine      what the viewer has submitted
    POST   /api/contributions/{id}/review   a reviewer approves or returns it
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query

from .. import database
from ..auth import user_id
from ..context import store as context_store
from ..identity import is_admin, load_profile
from ..retrieval.ask import ask
from ..retrieval.models import AgentAnswer, AgentSearch
from . import contributions
from . import draft as drafting
from .agent import find as find_prompts
from .models import (
    Contribution,
    Desk,
    DeskRef,
    Draft,
    DraftRequest,
    LibraryPage,
    Prompt,
    PromptCard,
    PromptDetail,
    ReviewDecision,
    Risk,
    Safety,
    Scope,
    Sort,
    Submission,
    Template,
)
from .store import search, store

router = APIRouter(tags=["prompts"])

RELATED = 3

# What happens after submitting, as the design reference states it.
_REVIEW = {
    "prompt": "The Data Privacy Office reviews it within two working days.",
    "video": "The Data Privacy Office reviews it before it goes live.",
    "agent": "Agents need Model Risk approval before they run. Expect a two-week review.",
}


def _viewer() -> Desk | None:
    return store.desk_for(load_profile().job_title)


def _saved() -> set[str]:
    with database.connect() as conn:
        rows = conn.execute("SELECT prompt_id FROM saved_prompts WHERE user_id=?", (user_id(),))
        return {r["prompt_id"] for r in rows}


def _card(p: Prompt, viewer: Desk | None, saved: set[str]) -> PromptCard:
    desk = next(d for d in store.library.desks if d.id == p.desk)
    return PromptCard(
        id=p.id,
        desk=DeskRef(id=desk.id, label=desk.label),
        category=p.category,
        title=p.title,
        description=p.description,
        tags=p.tags,
        relation=p.scope if viewer and viewer.id == p.desk else "other",
        uses=p.uses,
        rating=p.rating,
        ratings=p.ratings,
        hours_saved=p.hours_saved,
        risk=p.risk,
        validated=p.validated,
        contributor=p.contributor,
        updated=p.updated,
        saved=p.id in saved,
        source_kind=p.source_kind,
    )


def cards(prompts: list[Prompt]) -> list[PromptCard]:
    """Cards for the signed-in viewer. Used by Nexus's prompts pillar too."""
    viewer, saved = _viewer(), _saved()
    return [_card(p, viewer, saved) for p in prompts]


@router.get("/api/prompts", response_model=LibraryPage)
def library(
    q: str = Query(default="", max_length=200),
    desk: str | None = None,
    category: str | None = None,
    relation: Scope | None = None,
    sort: Sort = "relevance",
) -> LibraryPage:
    lib = store.library
    viewer = _viewer()
    showing = desk or (viewer.id if viewer else "all")
    if showing != "all" and all(d.id != showing for d in lib.desks):
        raise HTTPException(422, "Unknown desk")
    if category and category not in lib.categories:
        raise HTTPException(422, "Unknown category")
    saved = _saved()

    pool = [
        p
        for p in lib.prompts
        if (showing == "all" or p.desk == showing)
        and (not category or p.category == category)
        and (not relation or (p.scope if viewer and viewer.id == p.desk else "other") == relation)
        and (sort != "saved" or p.id in saved)
    ]
    if q.strip():
        pool = [p for _, p in search(q, pool)]
    if sort == "used" or (sort == "relevance" and not q.strip()):
        pool.sort(key=lambda p: -p.uses)
    elif sort == "rated":
        pool.sort(key=lambda p: (-p.rating, -p.ratings))
    elif sort == "new":
        pool.sort(key=lambda p: p.created, reverse=True)

    return LibraryPage(
        desk=DeskRef(id=viewer.id, label=viewer.label) if viewer else None,
        showing=showing,
        desks=[DeskRef(id=d.id, label=d.label) for d in lib.desks],
        categories=lib.categories,
        total=len(pool),
        prompts=[_card(p, viewer, saved) for p in pool],
    )


@router.post("/api/prompts/search", response_model=AgentAnswer)
def ask_agent(body: AgentSearch) -> AgentAnswer:
    """The Prompts & Skills agent, over the prompts this person may use and
    the contributions they may see."""
    from ..hub.guardrails import entitlements

    ents = entitlements()
    return ask(
        "prompts",
        body.query,
        lambda searched, model_reads: find_prompts([searched], ents.prompts, desk=ents.desk, rerank_query=model_reads),
    )


@router.get("/api/prompts/templates", response_model=list[Template])
def templates() -> list[Template]:
    return store.library.templates


@router.post("/api/prompts/draft", response_model=Draft)
def draft(req: DraftRequest) -> Draft:
    # The goal can name a client; a draft carries the masked form, as a log would.
    from ..hub.guardrails import check

    profile = load_profile()
    return drafting.compose(
        drafting.goal_of(check(req.goal, None).masked),
        job_title=profile.job_title,
        department=profile.department,
        variant=req.variant,
    )


@router.get("/api/prompts/{prompt_id}", response_model=PromptDetail)
def prompt(prompt_id: str) -> PromptDetail:
    p = store.prompt(prompt_id)
    if p is None:
        raise HTTPException(404, "Prompt not found")
    viewer, saved = _viewer(), _saved()
    related = sorted(
        (o for o in store.library.prompts if o.id != p.id and o.desk == p.desk and o.category == p.category),
        key=lambda o: -o.uses,
    )[:RELATED]
    return PromptDetail(
        **_card(p, viewer, saved).model_dump(),
        views=p.views,
        repetition=p.repetition,
        narrative=p.narrative,
        created=p.created,
        risk_note=p.risk_note,
        tutorial=p.tutorial,
        inputs=p.inputs,
        guidelines=p.guidelines,
        body=p.body,
        sample_output=p.sample_output,
        reviews=p.reviews,
        collaborators=p.collaborators,
        related=[_card(o, viewer, saved) for o in related],
    )


def _require(prompt_id: str) -> None:
    if store.prompt(prompt_id) is None:
        raise HTTPException(404, "Prompt not found")


@router.put("/api/prompts/{prompt_id}/saved")
def save(prompt_id: str) -> dict:
    _require(prompt_id)
    with database.connect(write=True) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO saved_prompts(user_id,prompt_id,saved_at) VALUES (?,?,?)",
            (user_id(), prompt_id, datetime.now(UTC).isoformat(timespec="seconds")),
        )
    return {"saved": True}


@router.delete("/api/prompts/{prompt_id}/saved")
def unsave(prompt_id: str) -> dict:
    _require(prompt_id)
    with database.connect(write=True) as conn:
        conn.execute(
            "DELETE FROM saved_prompts WHERE user_id=? AND prompt_id=?", (user_id(), prompt_id)
        )
    return {"saved": False}


# ------------------------------------------------------------ contributions


def implied_risk(safety: Safety) -> Risk:
    """The rating a declaration implies, on the library's own scale."""
    if safety.mnpi or safety.feeds_control:
        return "High"
    if safety.client_data:
        return "Medium"
    return "Low"


def _contribution(row) -> Contribution:
    payload = json.loads(row["payload"])
    return Contribution(
        id=row["id"],
        kind=row["kind"],
        title=row["title"],
        description=payload.get("description", ""),
        status=row["status"],
        review=_REVIEW[row["kind"]],
        risk=implied_risk(Safety(**payload["safety"])) if row["kind"] == "prompt" else None,
        audience=row["audience"],
        created_at=row["created_at"],
    )


@router.post("/api/contributions", response_model=Contribution, status_code=201)
def submit(body: Submission) -> Contribution:
    """Record it, then ingest it: embedded into its agent's index, so its
    author finds it at once and its audience does once it is approved."""
    lib = store.library
    known = {p.id for p in lib.prompts}
    if body.kind == "prompt":
        if body.category not in lib.categories:
            raise HTTPException(422, "Unknown category")
        if any(i not in known for i in body.learned_from):
            raise HTTPException(422, "Unknown source prompt")
    if body.kind == "agent" and any(i not in known for i in body.chain):
        raise HTTPException(422, "Unknown prompt in the chain")

    cid = uuid.uuid4().hex
    author = contributions.viewer()
    risk = implied_risk(body.safety) if body.kind == "prompt" else None
    with database.connect(write=True) as conn:
        conn.execute(
            "INSERT INTO contributions(id,user_id,kind,status,title,payload,created_at,desk,department,audience) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                cid,
                author.id,
                body.kind,
                "in_review",
                body.title,
                json.dumps(body.model_dump(exclude={"kind", "title"}), ensure_ascii=False),
                datetime.now(UTC).isoformat(timespec="seconds"),
                author.desk,
                author.department,
                contributions.audience_of(body, risk),
            ),
        )
        row = conn.execute("SELECT * FROM contributions WHERE id=?", (cid,)).fetchone()
        # The footprint says that something was contributed, never what it says.
        context_store.record_event(
            {"pillar": "prompts", "type": "collaborate", "subject_id": cid, "subject_type": body.kind},
            conn=conn,
        )
    # After the commit: the index is derived, and rebuilt from the table at
    # boot if this fails.
    contributions.ingest(row)
    return _contribution(row)


@router.post("/api/contributions/{contribution_id}/review", response_model=Contribution)
def review(contribution_id: str, body: ReviewDecision) -> Contribution:
    """A reviewer's decision. Approval opens it to its audience; a returned
    one leaves search. Hub administrators stand in for the Data Privacy
    Office and Model Risk in this prototype."""
    if not is_admin(load_profile()):
        raise HTTPException(403, "Only reviewers can approve or return a contribution")
    with database.connect(write=True) as conn:
        if conn.execute("SELECT 1 FROM contributions WHERE id=?", (contribution_id,)).fetchone() is None:
            raise HTTPException(404, "Contribution not found")
        conn.execute("UPDATE contributions SET status=? WHERE id=?", (body.decision, contribution_id))
        row = conn.execute("SELECT * FROM contributions WHERE id=?", (contribution_id,)).fetchone()
    if body.decision == "returned":
        contributions.retire(row)
    else:
        contributions.ingest(row)
    return _contribution(row)


@router.get("/api/contributions/mine", response_model=list[Contribution])
def mine() -> list[Contribution]:
    with database.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM contributions WHERE user_id=? ORDER BY created_at DESC, rowid DESC",
            (user_id(),),
        ).fetchall()
    return [_contribution(r) for r in rows]
