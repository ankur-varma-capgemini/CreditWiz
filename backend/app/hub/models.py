"""What the home assistant receives and returns."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from ..context.models import UserContext
from ..journeys.models import AssetCard, FollowUp, Intent, TaskContext
from ..prompts.models import Draft

Pillar = Literal["prompts", "marketplace", "learning", "community"]
PILLARS: tuple[Pillar, ...] = ("prompts", "marketplace", "learning", "community")
Source = Literal["claude", "rules"]
# What the conversation gate made of a request. Only a task goes on to the
# privacy check, the model and the pillars.
ConversationKind = Literal["greeting", "small_talk", "thanks", "goodbye", "help", "task"]


class Capability(BaseModel):
    """One of the hub's five capabilities, as the help answer presents it."""

    intent: Intent
    label: str
    what: str
    # A request to try, the persona's own where it has one.
    example: str


class SubQuery(BaseModel):
    pillar: Pillar
    # What that pillar is asked: the masked request, or the planner's rewrite of it.
    query: str
    # True when the planner rewrote the request for this pillar's catalogue.
    reformulated: bool


class PillarHit(BaseModel):
    # agent:<id> | prompt:<id> | learning:<id> | asset:<id> | page:<path>
    ref: str
    kind: str
    title: str
    summary: str
    # Blank when the owning team has not confirmed where it lives.
    href: str
    # Why it matched, from the catalogue, never from a model.
    why: str = ""
    # How the pillar's agent judged it against the request: "strong" or
    # "partial" (the closest thing, or part of what was asked). None when the
    # model was not asked (the data policy) or its call failed.
    fit: Literal["strong", "partial"] | None = None
    # A line of facts: rating and uses, provider and length, status.
    meta: str = ""


class PillarGroup(BaseModel):
    pillar: Pillar
    label: str
    # Where the full pillar search lives.
    href: str
    # What this pillar was asked.
    query: str
    hits: list[PillarHit]
    ms: int
    # How the pillar's agent found them: "hybrid" is meaning (Chroma) and
    # exact words (BM25) fused by rank, "keyword" is BM25 alone while the
    # vector index is unavailable, "words" is word matching, for a pillar
    # with no agent yet.
    retrieval: Literal["hybrid", "keyword", "words"] = "words"
    # True when the model read the shortlist against the request and ordered it.
    reranked: bool = False


class Plan(BaseModel):
    """How the answer was put together, for "How this was chosen"."""

    # A greeting or thanks set aside by the conversation gate, as typed.
    opening: str = ""
    # What every search and the usage log saw: names, accounts and emails masked.
    sanitized_query: str
    # What the data policy let the model receive for this request.
    model_access: Literal["as_typed", "masked", "none"]
    subqueries: list[SubQuery]
    selected_pillars: list[Pillar]
    plan_source: Source
    plan_reason: str
    reply_source: Source
    reply_reason: str
    # The governance gate's decisions, in plain words.
    governance: list[str]
    # Per node, plus "pillars (parallel)" and "total".
    timings_ms: dict[str, int]
    # The model used for either call; blank when none was.
    model: str = ""
    # A follow-up with no topic of its own ("any agents too?") is read with
    # the topic of the conversation's earlier request: that topic, as typed.
    # Shown back to the person who typed it; blank when nothing carried over.
    follows_on: str = ""


class AskRequest(BaseModel):
    """Sent in the body, not the URL: a request can name a client, and URLs
    end up in server and proxy access logs."""

    q: str = Field(min_length=1, max_length=500)
    persona: str | None = None
    # The job and the subject the conversation was on, for follow-ups that
    # name neither. Session context: sent by the client, never stored here.
    journey: str | None = None
    subject: str | None = Field(default=None, max_length=120)
    # The conversation's earlier requests, oldest first, for a follow-up to be
    # read with ("is there a quick reference for it?"). Session context like
    # the two above: held in the browser, sent with each request, never stored.
    history: list[Annotated[str, Field(max_length=500)]] = Field(default=[], max_length=8)
    # The conversation, for telemetry. A new one starts when this is absent.
    session: str | None = Field(default=None, pattern=r"^[a-f0-9-]{8,64}$")


class AskResponse(BaseModel):
    kind: ConversationKind
    # None for small talk, which is answered directly and not recorded.
    turn_id: str | None
    session_id: str
    query: str
    user: UserContext
    # A task's context and plan. None for small talk: nothing was planned.
    task: TaskContext | None = None
    plan: Plan | None = None
    # The job's own toolkit, when the request is one of the person's jobs.
    recommended: list[AssetCard] = []
    # What each pillar found, in the order they were asked.
    pillars: list[PillarGroup] = []
    # A prompt written from validated ones, when they asked for one.
    draft: Draft | None = None
    # For help, and for a request nothing in the hub matched: what the hub
    # can do, each with a request to try.
    capabilities: list[Capability] = []
    reply: str
    # Who wrote the reply: the model, or the catalogue's or conversation's fixed line.
    reply_source: Source = "rules"
    follow_ups: list[FollowUp] = []
    took_ms: int


class TurnFeedback(BaseModel):
    helpful: bool


class TurnSelection(BaseModel):
    ref: str = Field(min_length=3, max_length=300)
