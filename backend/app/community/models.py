"""Community as the hub shows it: one shape, whichever system it came from.

Viva Engage is the system of record once it is connected. Until then the hub
shows sample content from data/community.json and says so on every page.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Source = Literal["viva_engage", "sample"]
PostKind = Literal["discussion", "question", "announcement", "praise"]


class Person(BaseModel):
    id: str
    name: str
    title: str = ""


class Community(BaseModel):
    id: str
    name: str
    description: str = ""
    privacy: Literal["public", "private"] = "public"
    # None when the source does not say: Microsoft Graph lists no member count.
    member_count: int | None = None
    topics: list[str] = []
    # Who it is for. Empty means everyone. Decides "Your communities" and the
    # suggestions; a private community is listed only to the people it is for.
    personas: list[str] = []
    web_url: str = ""


class Post(BaseModel):
    """A conversation's first message. Its id is the thread id."""

    id: str
    thread_id: str
    community_id: str
    author: Person
    created_at: datetime
    kind: PostKind = "discussion"
    title: str = ""
    body: str
    topics: list[str] = []
    like_count: int = 0
    liked_by_me: bool = False
    reply_count: int = 0
    web_url: str = ""


class Reply(BaseModel):
    id: str
    thread_id: str
    author: Person
    created_at: datetime
    body: str
    like_count: int = 0
    # True for a reply written in this hub while Viva Engage is not connected:
    # it was saved here and posted nowhere else.
    local: bool = False


class Thread(BaseModel):
    post: Post
    replies: list[Reply]


class Expert(BaseModel):
    person: Person
    topics: list[str]
    community_ids: list[str] = []


class Connection(BaseModel):
    source: Source
    connected: bool
    notice: str


class CommunityHome(BaseModel):
    connection: Connection
    communities: list[Community]
    # The person's own communities, by id, in display order.
    mine: list[str]
    suggested: list[Community]
    experts: list[Expert]


class Feed(BaseModel):
    connection: Connection
    community: Community | None = None
    posts: list[Post]


class ReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
