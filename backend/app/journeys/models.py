"""Journeys: what a persona actually does, and what helps at each job.

    persona -> journeys -> steps
                        -> systems of record (where the work really happens)
                        -> asset refs, each tagged with the intent it serves

An asset ref points at the record of truth for that asset: an agent in
agents.json, a learning item in learning.json, or an entry in assets.json for
the kinds that have no pillar of their own yet (systems, data products,
prompts, experts, communities, use cases). Nothing is copied between them.

A request is answered from two contexts kept apart on purpose:

    UserContext  who the person is: role, function, interests, maturity,
                 entitlements (context/models.py, stable across a session)
    TaskContext  what they are doing now: intent, objective, activity,
                 subject, needs, sensitivity (below, built per request)
"""

from typing import Literal

from pydantic import BaseModel, Field

Intent = Literal["find", "learn", "improve", "ask", "contribute"]
INTENTS: tuple[Intent, ...] = ("find", "learn", "improve", "ask", "contribute")

AssetKind = Literal["system", "data_product", "prompt", "expert", "community", "use_case"]

Sensitivity = Literal["public", "internal", "confidential", "client_confidential"]

_SLUG = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


class Trust(BaseModel):
    """What someone needs to know before relying on an asset.

    A blank field means the owning team has not confirmed it. The page says
    "To be confirmed" instead of guessing.
    """

    owner_team: str = ""
    owner_name: str = ""
    purpose: str = ""
    approved_by: str = ""
    approved_on: str = ""
    who_can_use: str = ""
    how_to_access: str = ""
    guardrails: list[str] = []
    feedback: str = ""


class Asset(BaseModel):
    id: str = Field(pattern=_SLUG)
    kind: AssetKind
    title: str
    summary: str
    # The system where the work happens. Blank when the asset is used in Nexus.
    provided_by: str = ""
    action_label: str = ""
    action_url: str = ""
    trust: Trust = Trust()
    audience_groups: list[str] = ["AI-Hub-Users"]
    active: bool = True
    review_status: Literal["draft", "approved", "retired"] = "approved"
    source_kind: Literal["sample", "enterprise"] = "sample"


class JourneyStep(BaseModel):
    title: str
    detail: str


class SystemRole(BaseModel):
    system: str
    does: str


class AssetRef(BaseModel):
    ref: str = Field(pattern=r"^(agent|learning|asset):[a-z0-9]+(?:-[a-z0-9]+)*$")
    intent: Intent
    why: str


class Journey(BaseModel):
    id: str = Field(pattern=_SLUG)
    title: str
    summary: str
    # What someone doing this job is trying to achieve, in their words.
    objective: str
    # What they need to get it done; shown back as the task's needs.
    needs: list[str]
    keywords: list[str]
    steps: list[JourneyStep]
    systems: list[SystemRole]
    assets: list[AssetRef]


class PersonaJourneys(BaseModel):
    persona: str
    # Requests this persona might type, shown as search examples on home.
    examples: list[str] = []
    journeys: list[Journey]


# ---------------------------------------------------------------- responses


class AssetCard(BaseModel):
    """One asset as a journey shows it, whichever store it came from."""

    ref: str
    kind: str
    title: str
    summary: str
    intent: Intent
    why: str
    # Lifecycle for an agent, content type for a learning item.
    status: str = ""
    provided_by: str = ""
    action_label: str
    action_url: str = ""
    trust: Trust
    source_kind: Literal["sample", "enterprise"]


class JourneySummary(BaseModel):
    id: str
    title: str
    summary: str
    systems: list[str]
    asset_count: int


class JourneysHome(BaseModel):
    persona: str
    persona_label: str
    examples: list[str]
    journeys: list[JourneySummary]


class JourneyPage(BaseModel):
    id: str
    persona: str
    persona_label: str
    title: str
    summary: str
    steps: list[JourneyStep]
    systems: list[SystemRole]
    assets: list[AssetCard]


class Subject(BaseModel):
    """A client or deal the request names. Lives for the conversation only."""

    name: str
    kind: Literal["client", "deal"]


class TaskContext(BaseModel):
    """What the person is doing right now, built per request (hub/graph.py)."""

    # The primary intent, and every intent the request carries, primary first.
    intent: Intent
    intents: list[Intent] = []
    # The words that decided the intent. Blank when nothing did and Find applies.
    intent_cue: str
    objective: str = ""
    # The job the request belongs to.
    activity: JourneySummary | None = None
    # True when the activity came from the conversation, not from these words.
    carried_over: bool = False
    subject: Subject | None = None
    # True when the subject came from earlier in the conversation.
    subject_carried_over: bool = False
    needs: list[str] = []
    sensitivity: Sensitivity = "internal"
    sensitivity_reason: str = ""
    # The only form of the request that may be written to usage logs.
    loggable_query: str
    # How the recommendations were ordered, and why.
    ordering: str = ""


class FollowUp(BaseModel):
    label: str
    query: str
