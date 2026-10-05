from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from ..content_validation import safe_link

ItemType = Literal[
    "video",
    "course",
    "confluence",
    "guide",
    "documentation",
    "quick-reference",
    "best-practice",
]
Status = Literal["not_started", "in_progress", "completed"]


class LearningPath(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str
    blurb: str
    owner: str = "Learning team (sample mapping)"
    version: str = "1"
    steps: list[str] = []
    completed_steps: int = 0
    total_steps: int = 0
    next_item_id: str | None = None


class Lesson(BaseModel):
    """One part of a catalogue course, as its provider lists it."""

    title: str
    minutes: int = Field(ge=0)
    kind: Literal["Video", "Lecture", "Chapter"] = "Video"


class Item(BaseModel):
    """One piece of learning content, of any type."""

    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str
    type: ItemType
    description: str
    topics: list[str] = []
    capabilities: list[str] = []
    personas: list[str] = []
    required_for: list[str] = []
    path: str
    level: str = ""
    duration_seconds: int = 0
    tags: list[str] = []
    related_agents: list[str] = []
    url: str = ""
    youtube_id: str = ""
    poster_url: str = ""
    source: str = ""
    # Catalogue courses (Pluralsight, LinkedIn Learning, Udemy Business, MUFG
    # Learning): the provider's own id for provenance, who teaches it, its
    # lessons and what it teaches. Empty for hub-native content.
    provider_ref: str = ""
    instructor: str = ""
    lessons: list[Lesson] = []
    outcomes: list[str] = []
    # False when MUFG holds no licence for it yet.
    licensed: bool = True
    # in-app markdown for hub-native content; empty when the item links out
    body: str = ""
    audience_groups: list[str] = ["AI-Hub-Users"]
    active: bool = True
    review_status: Literal["draft", "approved", "retired"] = "approved"
    reviewed_at: str = ""
    owner: str = "AI Learning team"
    prerequisites: list[str] = []
    priority: int = 0
    source_kind: Literal["sample", "enterprise"] = "sample"

    _links = field_validator("url", "poster_url")(safe_link)

    @model_validator(mode="after")
    def reviewed_enterprise(self):
        if self.source_kind == "enterprise":
            if (
                not {
                    "audience_groups",
                    "review_status",
                    "active",
                    "owner",
                    "reviewed_at",
                }
                <= self.model_fields_set
            ):
                raise ValueError(
                    "Enterprise learning requires explicit ACL, publication and review metadata"
                )
            if not self.owner or not self.reviewed_at:
                raise ValueError(
                    "Enterprise learning requires an owner and review date"
                )
        return self


class ItemWithProgress(Item):
    status: Status = "not_started"
    progress: int = 0
    # Ratings are displayed, never ranked on. `rating_average` is withheld until
    # the item clears learning.ratings.MIN_SHOWN; `rating_weighted` is the
    # shrunk value a future rating-aware ranker would sort on.
    rating_count: int = 0
    rating_average: float | None = None
    rating_weighted: float | None = None
    my_rating: int | None = None
    required: bool = False
    recommendation_reason: str = ""
    blocked_by: list[str] = []
    prerequisite_unavailable: bool = False
    sequence: int | None = None
    # Where Start opens: a Pluralsight single-sign-on link (or a search while
    # Pluralsight is not connected), or the Microsoft Learn page.
    launch_url: str = ""
    # True when the content can be read inside the hub (Microsoft Learn).
    read_in_hub: bool = False
    # True when the provider's own API supplied the details just now.
    live: bool = False


class ItemDetail(ItemWithProgress):
    path_title: str
    related_items: list[ItemWithProgress]
    related_agent_names: dict[str, str]


class Section(BaseModel):
    """A landing-page section. Which sections appear depends on the persona and progress."""

    id: str
    title: str
    subtitle: str = ""
    items: list[ItemWithProgress]


class LearningHome(BaseModel):
    persona: str
    persona_label: str
    paths: list[LearningPath]
    sections: list[Section]
    item_count: int
    role_paths: list[LearningPath] = []


class ProviderResult(BaseModel):
    """A search result from a provider's own library, beyond the hub's catalogue."""

    title: str
    # Where it opens: a Microsoft Learn page (read in the hub), or Pluralsight.
    url: str
    excerpt: str = ""
    level: str = ""
    duration_seconds: int = 0
    read_in_hub: bool = False


class ProviderResults(BaseModel):
    provider: Literal["Pluralsight", "Microsoft Learn"]
    # live: searched just now. sample: not connected, so only the hub's catalogue
    # was searched. blocked: the provider refused or did not answer.
    state: Literal["live", "sample", "blocked"]
    note: str = ""
    results: list[ProviderResult] = []


class ProgressIn(BaseModel):
    item_id: str
    status: Status
    progress: int | None = Field(default=None, ge=0, le=100)


class RatingIn(BaseModel):
    item_id: str
    # null clears the learner's own rating
    stars: int | None = Field(default=None, ge=1, le=5)


class TopicCoverage(BaseModel):
    """Factual counts only. Deliberately NOT a proficiency score."""

    topic: str
    completed: int
    total: int


class MyLearning(BaseModel):
    persona: str
    persona_label: str
    completed: int
    in_progress: int
    not_started: int
    required_total: int
    required_completed: int
    items: list[ItemWithProgress]
    coverage: list[TopicCoverage]
    proficiency_note: str
