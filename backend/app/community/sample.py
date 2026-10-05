"""Sample community: data/community.json, plus the replies and likes people make
in the hub while Viva Engage is not connected.

Those replies and likes are kept in this hub's own database and go nowhere
else. Each one is marked, so the page can say so.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from .. import database
from ..identity import DirectoryProfile
from .models import (
    Community,
    CommunityHome,
    Connection,
    Expert,
    Feed,
    Person,
    Post,
    PostKind,
    Reply,
    Thread,
)

CONNECTION = Connection(
    source="sample",
    connected=False,
    notice="Sample content. Viva Engage isn't connected here, so replies and likes stay in the hub.",
)
SUGGESTED = 3


def _data_dir() -> Path:
    return Path(os.environ.get("CREDITWIZ_DATA_DIR", Path(__file__).resolve().parents[2] / "data"))


@lru_cache(maxsize=4)
def _read(path: str, modified: float) -> dict:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    validate(raw)
    return raw


def validate(raw: dict) -> None:
    """Every author and community a post names exists, and no id repeats."""
    people = {p["id"] for p in raw["people"]}
    communities = {c["id"] for c in raw["communities"]}
    if len(people) != len(raw["people"]) or len(communities) != len(raw["communities"]):
        raise ValueError("Duplicate person or community id in community.json")
    ids: set[str] = set()
    for post in raw["posts"]:
        if post["community_id"] not in communities:
            raise ValueError(f"Post {post['id']} names an unknown community")
        for message in [post, *post.get("replies", [])]:
            if message["author"] not in people:
                raise ValueError(f"Message {message['id']} names an unknown author")
            if message["id"] in ids:
                raise ValueError(f"Duplicate message id {message['id']}")
            ids.add(message["id"])
    for expert in raw["experts"]:
        if expert["person"] not in people or not set(expert["community_ids"]) <= communities:
            raise ValueError("An expert names an unknown person or community")


def _raw() -> dict:
    path = _data_dir() / "community.json"
    return _read(str(path), path.stat().st_mtime)


def _when(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _hub_person(user_id: str, profile: dict) -> Person:
    # Never the hub's own user id: other people see this author.
    return Person(
        id="hub-" + hashlib.sha256(user_id.encode()).hexdigest()[:12],
        name=profile.get("name", "AI Hub user"),
        title=profile.get("job_title", ""),
    )


class SampleCommunity:
    def __init__(self, reason: str = "") -> None:
        # The reason live Viva Engage was not used, when it was tried and refused.
        self.connection = CONNECTION.model_copy(update={"notice": reason}) if reason else CONNECTION
        raw = _raw()
        self._people = {p["id"]: Person(**p) for p in raw["people"]}
        self._communities = [Community(**c) for c in raw["communities"]]
        self._posts = {p["id"]: p for p in raw["posts"]}
        self._experts = raw["experts"]

    # ---------------------------------------------------------- who sees what

    def _visible(self, persona_id: str) -> list[Community]:
        return [c for c in self._communities if c.privacy == "public" or persona_id in c.personas]

    def _community(self, persona_id: str, community_id: str) -> Community:
        found = next((c for c in self._visible(persona_id) if c.id == community_id), None)
        if found is None:
            raise LookupError("Community not found")
        return found

    def _raw_post(self, persona_id: str, post_id: str) -> dict:
        raw = self._posts.get(post_id)
        if raw is None:
            raise LookupError("Conversation not found")
        self._community(persona_id, raw["community_id"])
        return raw

    # ------------------------------------------------------------ local state

    @staticmethod
    def _local(user_id: str) -> tuple[dict[str, int], set[str], dict[str, int]]:
        with database.connect() as conn:
            likes = {r["post_id"]: r["n"] for r in conn.execute("SELECT post_id, COUNT(*) AS n FROM community_likes GROUP BY post_id")}
            mine = {r["post_id"] for r in conn.execute("SELECT post_id FROM community_likes WHERE user_id=?", (user_id,))}
            replies = {
                r["thread_id"]: r["n"]
                for r in conn.execute("SELECT thread_id, COUNT(*) AS n FROM community_replies GROUP BY thread_id")
            }
        return likes, mine, replies

    def _post(self, raw: dict, local: tuple[dict[str, int], set[str], dict[str, int]]) -> Post:
        likes, mine, replies = local
        return Post(
            id=raw["id"],
            thread_id=raw["id"],
            community_id=raw["community_id"],
            author=self._people[raw["author"]],
            created_at=_when(raw["created_at"]),
            kind=raw.get("kind", "discussion"),
            title=raw.get("title", ""),
            body=raw["body"],
            topics=raw.get("topics", []),
            like_count=raw.get("likes", 0) + likes.get(raw["id"], 0),
            liked_by_me=raw["id"] in mine,
            reply_count=len(raw.get("replies", [])) + replies.get(raw["id"], 0),
        )

    # ------------------------------------------------------------------ reads

    def home(self, persona_id: str, user_id: str) -> CommunityHome:
        visible = self._visible(persona_id)
        mine = [c.id for c in visible if not c.personas or persona_id in c.personas]
        suggested = sorted(
            (c for c in visible if c.id not in mine and c.privacy == "public"),
            key=lambda c: -(c.member_count or 0),
        )[:SUGGESTED]
        seen = {c.id for c in visible}
        experts = [
            Expert(person=self._people[e["person"]], topics=e["topics"], community_ids=[i for i in e["community_ids"] if i in seen])
            for e in self._experts
            if seen & set(e["community_ids"])
        ]
        return CommunityHome(connection=self.connection, communities=visible, mine=mine, suggested=suggested, experts=experts)

    def feed(
        self, persona_id: str, user_id: str, community_id: str | None = None, kind: PostKind | None = None, q: str = ""
    ) -> Feed:
        community = self._community(persona_id, community_id) if community_id else None
        allowed = {c.id for c in self._visible(persona_id)}
        terms = q.lower().split()
        local = self._local(user_id)
        posts = []
        for raw in self._posts.values():
            if raw["community_id"] not in allowed or (community and raw["community_id"] != community.id):
                continue
            if kind and raw.get("kind", "discussion") != kind:
                continue
            post = self._post(raw, local)
            text = " ".join([post.title, post.body, post.author.name, *post.topics]).lower()
            if all(t in text for t in terms):
                posts.append(post)
        posts.sort(key=lambda p: p.created_at, reverse=True)
        return Feed(connection=self.connection, community=community, posts=posts)

    def thread(self, persona_id: str, user_id: str, thread_id: str) -> Thread:
        raw = self._raw_post(persona_id, thread_id)
        replies = [
            Reply(
                id=r["id"],
                thread_id=thread_id,
                author=self._people[r["author"]],
                created_at=_when(r["created_at"]),
                body=r["body"],
                like_count=r.get("likes", 0),
            )
            for r in raw.get("replies", [])
        ]
        with database.connect() as conn:
            rows = conn.execute(
                "SELECT r.id, r.user_id, r.body, r.created_at, u.profile FROM community_replies r "
                "JOIN users u ON u.id = r.user_id WHERE r.thread_id=? ORDER BY r.created_at",
                (thread_id,),
            ).fetchall()
        for row in rows:
            replies.append(
                Reply(
                    id=row["id"],
                    thread_id=thread_id,
                    author=_hub_person(row["user_id"], json.loads(row["profile"])),
                    created_at=_when(row["created_at"]),
                    body=row["body"],
                    local=True,
                )
            )
        replies.sort(key=lambda r: r.created_at)
        return Thread(post=self._post(raw, self._local(user_id)), replies=replies)

    # ----------------------------------------------------------------- writes

    def reply(self, persona_id: str, profile: DirectoryProfile, thread_id: str, body: str) -> Reply:
        self._raw_post(persona_id, thread_id)
        reply_id = f"local-{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC)
        with database.connect(write=True) as conn:
            conn.execute(
                "INSERT INTO community_replies (id, thread_id, user_id, body, created_at) VALUES (?,?,?,?,?)",
                (reply_id, thread_id, profile.id, body, now.isoformat()),
            )
        return Reply(
            id=reply_id,
            thread_id=thread_id,
            author=_hub_person(profile.id, profile.model_dump()),
            created_at=now,
            body=body,
            local=True,
        )

    def like(self, persona_id: str, user_id: str, post_id: str, liked: bool) -> Post:
        """Like, or take a like back. Saying it twice changes nothing."""
        raw = self._raw_post(persona_id, post_id)
        with database.connect(write=True) as conn:
            if liked:
                conn.execute(
                    "INSERT OR IGNORE INTO community_likes (user_id, post_id, created_at) VALUES (?,?,?)",
                    (user_id, post_id, datetime.now(UTC).isoformat()),
                )
            else:
                conn.execute("DELETE FROM community_likes WHERE user_id=? AND post_id=?", (user_id, post_id))
        return self._post(raw, self._local(user_id))
