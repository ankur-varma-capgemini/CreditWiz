"""Viva Engage, live.

Microsoft Graph lists communities (Community.Read.All) but carries no posts,
and works only for networks in native mode. Conversations therefore come from
the Viva Engage REST API at https://www.yammer.com/api/v1, called with the
person's Entra token for https://www.yammer.com/.default.

Both tokens are the signed-in person's own, from "Sign in with Microsoft"
(entra.py), so Viva Engage applies that person's permissions. A developer can
stand in tokens through the environment instead:

    VIVA_ENGAGE_GRAPH_TOKEN   Graph token with Community.Read.All
    VIVA_ENGAGE_TOKEN         Entra token for https://www.yammer.com/.default

Until one or the other is there, the hub shows its sample community.
"""

from __future__ import annotations

import base64
import json
import os
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlencode

from .. import auth, entra, http
from ..identity import DirectoryProfile
from .models import Community, CommunityHome, Connection, Feed, Person, Post, PostKind, Reply, Thread

GRAPH = "https://graph.microsoft.com/v1.0"
ENGAGE = "https://www.yammer.com/api/v1"
SERVICE = "Viva Engage"
CONNECTION = Connection(source="viva_engage", connected=True, notice="Live from Viva Engage.")
_KIND: dict[str, PostKind] = {"announcement": "announcement", "praise": "praise"}


_ENV = {"graph": "VIVA_ENGAGE_GRAPH_TOKEN", "engage": "VIVA_ENGAGE_TOKEN"}


def _env_tokens() -> bool:
    return all(os.environ.get(name, "").strip() for name in _ENV.values())


def configured() -> bool:
    """Live when there are tokens to call with: the person's own, or a developer's."""
    return _env_tokens() or entra.signed_in(auth.current_id.get())


def _token(which: Literal["graph", "engage"]) -> str:
    if _env_tokens():
        return os.environ[_ENV[which]].strip()
    token = entra.token_for(auth.current_id.get(), which)
    if not token:
        raise http.ExternalError(SERVICE, None, "No Microsoft token: sign in with Microsoft first.")
    return token


def _get(url: str, which: Literal["graph", "engage"]) -> dict:
    response = http.send(SERVICE, "GET", url, headers={"Authorization": f"Bearer {_token(which)}"})
    return response.json() or {}


# Hub user id -> their Viva Engage user id. It never changes for a person.
_engage_ids: dict[str, str] = {}


def _me() -> str:
    """The signed-in person's Viva Engage id: how a post's likes show which are theirs."""
    key = auth.current_id.get() or ""
    if not _engage_ids.get(key):
        found = str(_get(f"{ENGAGE}/users/current.json", "engage").get("id") or "")
        if not found:
            return ""
        _engage_ids[key] = found
    return _engage_ids[key]


def engage_group_id(community_id: str) -> str:
    """A Graph community id is base64 of {"_type":"Group","id":"<Engage group id>"}."""
    try:
        decoded = base64.urlsafe_b64decode(community_id + "=" * (-len(community_id) % 4))
        return str(json.loads(decoded)["id"])
    except (ValueError, KeyError, TypeError):
        return community_id


def _when(value: str) -> datetime:
    # Viva Engage writes "2026/09/22 10:00:00 +0000".
    try:
        return datetime.strptime(value, "%Y/%m/%d %H:%M:%S %z")
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            return datetime.now(UTC)


def _people(references: list[dict]) -> dict[str, Person]:
    return {
        str(r["id"]): Person(id=str(r["id"]), name=r.get("full_name") or r.get("name") or "Viva Engage member", title=r.get("job_title") or "")
        for r in references
        if r.get("type") == "user" and "id" in r
    }


def _reply_counts(references: list[dict]) -> dict[str, int]:
    # A thread's "updates" counts every message in it, the first one included.
    return {
        str(r["id"]): max(int((r.get("stats") or {}).get("updates", 1)) - 1, 0)
        for r in references
        if r.get("type") == "thread" and "id" in r
    }


def _author(message: dict, people: dict[str, Person]) -> Person:
    sender = str(message.get("sender_id", ""))
    return people.get(sender) or Person(id=sender, name="Viva Engage member")


def _post(message: dict, people: dict[str, Person], replies: dict[str, int], communities: dict[str, str], me: str = "") -> Post:
    thread_id = str(message.get("thread_id") or message["id"])
    # liked_by carries the count and the ids of the people who liked it.
    liked_by = message.get("liked_by") or {}
    return Post(
        id=str(message["id"]),
        thread_id=thread_id,
        community_id=communities.get(str(message.get("group_id", "")), ""),
        author=_author(message, people),
        created_at=_when(message.get("created_at", "")),
        kind=_KIND.get(message.get("message_type", ""), "discussion"),
        title=message.get("title") or "",
        body=(message.get("body") or {}).get("plain", ""),
        like_count=int(liked_by.get("count", 0)),
        liked_by_me=bool(me) and me in {str(n.get("user_id")) for n in liked_by.get("names") or []},
        reply_count=replies.get(thread_id, 0),
        web_url=message.get("web_url") or "",
    )


def _reply(message: dict, people: dict[str, Person], thread_id: str) -> Reply:
    return Reply(
        id=str(message["id"]),
        thread_id=thread_id,
        author=_author(message, people),
        created_at=_when(message.get("created_at", "")),
        body=(message.get("body") or {}).get("plain", ""),
        like_count=int((message.get("liked_by") or {}).get("count", 0)),
    )


class VivaEngage:
    connection = CONNECTION

    def _communities(self) -> list[Community]:
        url = f"{GRAPH}/employeeExperience/communities?$top=100&$orderby=displayName"
        found: list[Community] = []
        while url and len(found) < 300:
            page = _get(url, "graph")
            for c in page.get("value", []):
                found.append(
                    Community(
                        id=c["id"],
                        name=c.get("displayName", ""),
                        description=c.get("description") or "",
                        privacy="private" if c.get("privacy") == "private" else "public",
                    )
                )
            url = page.get("@odata.nextLink", "")
        return found

    def _by_group(self) -> dict[str, str]:
        return {engage_group_id(c.id): c.id for c in self._communities()}

    def home(self, persona_id: str, user_id: str) -> CommunityHome:
        communities = self._communities()
        # Graph lists the network's communities, not the person's membership.
        return CommunityHome(connection=CONNECTION, communities=communities, mine=[], suggested=[], experts=[])

    def feed(
        self, persona_id: str, user_id: str, community_id: str | None = None, kind: PostKind | None = None, q: str = ""
    ) -> Feed:
        communities = self._communities()
        community = next((c for c in communities if c.id == community_id), None) if community_id else None
        if community_id and community is None:
            raise LookupError("Community not found")
        page = self._search(q, community_id) if q.strip() else self._latest(community_id)
        references = page.get("references", [])
        people, replies = _people(references), _reply_counts(references)
        by_group = {engage_group_id(c.id): c.id for c in communities}
        me = _me()
        posts = [
            p
            for p in (_post(m, people, replies, by_group, me) for m in page.get("messages", []))
            if not kind or p.kind == kind
        ]
        return Feed(connection=CONNECTION, community=community, posts=posts)

    @staticmethod
    def _latest(community_id: str | None) -> dict:
        path = f"/messages/in_group/{engage_group_id(community_id)}.json" if community_id else "/messages.json"
        return _get(f"{ENGAGE}{path}?threaded=true&limit=20", "engage")

    @staticmethod
    def _search(q: str, community_id: str | None) -> dict:
        """Viva Engage's own search, across everything the person can read.

        Its documentation names what comes back (messages, users, topics and
        groups) but not the layout, so messages are read in the layout every
        other message call uses, or as a bare list. Only conversations' opening
        posts are kept: a post card likes, opens and replies to a conversation.
        """
        params = {"search": q.strip(), "num_per_page": 20}
        if community_id:
            params["search_group"] = engage_group_id(community_id)
        found = _get(f"{ENGAGE}/search.json?{urlencode(params)}", "engage")
        messages = found.get("messages") or []
        page = messages if isinstance(messages, dict) else {"messages": messages, "references": found.get("references", [])}
        openers = [m for m in page.get("messages") or [] if str(m.get("thread_id") or m.get("id")) == str(m.get("id"))]
        return {"messages": openers, "references": page.get("references") or []}

    def thread(self, persona_id: str, user_id: str, thread_id: str) -> Thread:
        if not thread_id.isdigit():
            raise LookupError("Conversation not found")
        page = _get(f"{ENGAGE}/messages/in_thread/{thread_id}.json", "engage")
        messages = page.get("messages", [])
        references = page.get("references", [])
        people = _people(references)
        first = next((m for m in messages if str(m.get("id")) == str(thread_id)), None)
        if first is None:
            raise LookupError("Conversation not found")
        others = [m for m in messages if m is not first]
        post = _post(first, people, {str(thread_id): len(others)}, self._by_group(), _me())
        replies = sorted((_reply(m, people, str(thread_id)) for m in others), key=lambda r: r.created_at)
        return Thread(post=post, replies=replies)

    def reply(self, persona_id: str, profile: DirectoryProfile, thread_id: str, body: str) -> Reply:
        response = http.send(
            SERVICE,
            "POST",
            f"{ENGAGE}/messages.json",
            headers={"Authorization": f"Bearer {_token('engage')}"},
            form={"body": body, "replied_to_id": thread_id},
        )
        page = response.json() or {}
        messages = page.get("messages", [])
        if not messages:
            raise http.ExternalError(SERVICE)
        return _reply(messages[0], _people(page.get("references", [])), str(thread_id))

    def like(self, persona_id: str, user_id: str, post_id: str, liked: bool) -> Post:
        """Like a conversation, or take the like back, as the signed-in person."""
        if not post_id.isdigit():
            raise LookupError("Conversation not found")
        http.send(
            SERVICE,
            "POST" if liked else "DELETE",
            f"{ENGAGE}/messages/liked_by/current.json?message_id={post_id}",
            headers={"Authorization": f"Bearer {_token('engage')}"},
        )
        # Read it back, so the count shown is Viva Engage's own.
        return self.thread(persona_id, user_id, post_id).post
