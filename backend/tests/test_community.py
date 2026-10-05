"""Community: sample content while Viva Engage is not connected, live mapping
when it is, and an honest fallback when Viva Engage refuses."""

import json

import pytest
from fastapi.testclient import TestClient

from app import http
from app.community import vivaengage
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def no_viva_engage(monkeypatch):
    for name in ("VIVA_ENGAGE_GRAPH_TOKEN", "VIVA_ENGAGE_TOKEN", "ENTRA_TENANT_ID", "ENTRA_CLIENT_ID", "ENTRA_CLIENT_SECRET"):
        monkeypatch.delenv(name, raising=False)


def test_home_says_it_is_sample_content_and_lists_the_persona_s_communities():
    home = client.get("/api/community").json()
    assert home["connection"] == {
        "source": "sample",
        "connected": False,
        "notice": "Sample content. Viva Engage isn't connected here, so replies and likes stay in the hub.",
    }
    ids = {c["id"] for c in home["communities"]}
    # u-1001 is a Compliance Analyst: their private community, not the RMs'.
    assert "compliance-ai" in ids and "rm-ai-champions" not in ids
    assert {"compliance-ai", "responsible-ai", "ai-hub"} <= set(home["mine"])
    assert all(c["id"] not in home["mine"] and c["privacy"] == "public" for c in home["suggested"])
    assert home["experts"] and all(e["community_ids"] for e in home["experts"])


def test_a_private_community_is_shown_only_to_the_people_it_is_for():
    developer = client.get("/api/community", params={"persona": "developer"}).json()
    assert "compliance-ai" not in {c["id"] for c in developer["communities"]}
    assert client.get("/api/community/feed", params={"community": "compliance-ai", "persona": "developer"}).status_code == 404
    assert client.get("/api/community/threads/t-107", params={"persona": "developer"}).status_code == 404


def test_the_feed_is_newest_first_and_filters_by_community_kind_and_words():
    posts = client.get("/api/community/feed").json()["posts"]
    times = [p["created_at"] for p in posts]
    assert times == sorted(times, reverse=True)
    assert "rm-ai-champions" not in {p["community_id"] for p in posts}

    one = client.get("/api/community/feed", params={"community": "copilot-builders"}).json()
    assert one["community"]["name"] == "Copilot Studio Builders"
    assert {p["community_id"] for p in one["posts"]} == {"copilot-builders"}

    announcements = client.get("/api/community/feed", params={"kind": "announcement"}).json()["posts"]
    assert announcements and {p["kind"] for p in announcements} == {"announcement"}

    found = client.get("/api/community/feed", params={"q": "copilot studio"}).json()["posts"]
    assert found and all("copilot studio" in f"{p['title']} {p['body']} {' '.join(p['topics'])}".lower() for p in found)


def test_a_reply_is_kept_in_the_hub_marked_local_and_counted():
    before = next(p for p in client.get("/api/community/feed").json()["posts"] if p["id"] == "t-101")
    made = client.post("/api/community/threads/t-101/replies", json={"body": "Following this one."})
    assert made.status_code == 201
    reply = made.json()
    assert reply["local"] is True and reply["author"]["name"] == "Sai Vivek"
    assert not reply["author"]["id"].startswith("u-")  # the hub's own user id is never shown

    thread = client.get("/api/community/threads/t-101").json()
    assert thread["replies"][-1]["body"] == "Following this one."
    after = next(p for p in client.get("/api/community/feed").json()["posts"] if p["id"] == "t-101")
    assert after["reply_count"] == before["reply_count"] + 1


@pytest.mark.parametrize(
    "body", ["Email me at jane.doe@client-example.com", "Their account 1234 5678 9012 is the one", "   "]
)
def test_a_reply_with_client_data_or_nothing_in_it_is_refused(body):
    response = client.post("/api/community/threads/t-101/replies", json={"body": body})
    assert response.status_code == 422
    assert len(client.get("/api/community/threads/t-101").json()["replies"]) == 3


@pytest.mark.parametrize(
    "body",
    [
        "Thanks, this helped a lot.",
        "Raise it as an AI Request so governance reviews it first.",
        "I tried the prompt in Copilot Studio and it worked.",
    ],
)
def test_ordinary_replies_are_not_mistaken_for_client_data(body):
    assert client.post("/api/community/threads/t-104/replies", json={"body": body}).status_code == 201


def test_a_like_is_given_and_taken_back_and_saying_it_twice_changes_nothing():
    start = next(p for p in client.get("/api/community/feed").json()["posts"] if p["id"] == "t-102")
    liked = client.post("/api/community/posts/t-102/like").json()
    assert liked["liked_by_me"] is True and liked["like_count"] == start["like_count"] + 1
    assert client.post("/api/community/posts/t-102/like").json()["like_count"] == liked["like_count"]
    unliked = client.delete("/api/community/posts/t-102/like").json()
    assert unliked["liked_by_me"] is False and unliked["like_count"] == start["like_count"]
    assert client.delete("/api/community/posts/t-102/like").json()["like_count"] == start["like_count"]


def test_an_unknown_conversation_is_not_found():
    assert client.get("/api/community/threads/t-999").status_code == 404
    assert client.post("/api/community/threads/t-999/replies", json={"body": "Hello"}).status_code == 404


def test_a_refusal_from_viva_engage_falls_back_to_samples_and_says_why(monkeypatch):
    monkeypatch.setenv("VIVA_ENGAGE_GRAPH_TOKEN", "graph-token")
    monkeypatch.setenv("VIVA_ENGAGE_TOKEN", "engage-token")

    def refuse(service, method, url, **kwargs):
        raise http.ExternalError("Viva Engage", 403, "Authorization_RequestDenied: Insufficient privileges")

    monkeypatch.setattr(http, "send", refuse)
    home = client.get("/api/community").json()
    assert home["connection"]["source"] == "sample"
    assert "Viva Engage returned 403" in home["connection"]["notice"]

    status = {i["id"]: i for i in client.get("/api/integrations").json()}
    assert status["viva_engage"]["state"] == "blocked"
    assert "Insufficient privileges" in status["viva_engage"]["blocking"]

    # A write is never quietly kept here instead: it says why it was not posted.
    response = client.post("/api/community/threads/12345/replies", json={"body": "Hello"})
    assert response.status_code == 502 and "403" in response.json()["detail"]


GROUP_ID = "eyJfdHlwZSI6Ikdyb3VwIiwiaWQiOiIxOTAzMzYyMTIyMTAifQ"


def test_a_graph_community_id_carries_the_engage_group_id():
    assert vivaengage.engage_group_id(GROUP_ID) == "190336212210"
    assert vivaengage.engage_group_id("not-base64-json") == "not-base64-json"


def test_live_viva_engage_responses_map_to_the_hub_s_shapes(monkeypatch):
    monkeypatch.setenv("VIVA_ENGAGE_GRAPH_TOKEN", "graph-token")
    monkeypatch.setenv("VIVA_ENGAGE_TOKEN", "engage-token")
    seen = []

    def answer(service, method, url, **kwargs):
        seen.append((method, url, kwargs.get("headers", {}).get("Authorization")))
        if url.startswith(vivaengage.GRAPH):
            body = {"value": [{"id": GROUP_ID, "displayName": "AI Builders", "description": "Build things", "privacy": "public"}]}
        else:
            body = {
                "messages": [
                    {
                        "id": 501,
                        "thread_id": 501,
                        "group_id": 190336212210,
                        "sender_id": 7,
                        "created_at": "2026/09/22 10:00:00 +0000",
                        "message_type": "announcement",
                        "title": "Welcome",
                        "body": {"plain": "Hello builders"},
                        "liked_by": {"count": 12},
                        "web_url": "https://engage.cloud.microsoft/main/threads/501",
                    }
                ],
                "references": [
                    {"type": "user", "id": 7, "full_name": "Test Person", "job_title": "Engineer"},
                    {"type": "thread", "id": 501, "stats": {"updates": 9}},
                ],
            }
        return http.Response(200, json.dumps(body))

    monkeypatch.setattr(http, "send", answer)
    feed = client.get("/api/community/feed", params={"community": GROUP_ID}).json()
    assert feed["connection"]["source"] == "viva_engage"
    post = feed["posts"][0]
    assert post["community_id"] == GROUP_ID
    assert post["author"] == {"id": "7", "name": "Test Person", "title": "Engineer"}
    assert post["kind"] == "announcement" and post["like_count"] == 12 and post["reply_count"] == 8
    assert post["created_at"].startswith("2026-09-22T10:00:00")
    assert any(u.endswith("/messages/in_group/190336212210.json?threaded=true&limit=20") for _, u, _ in seen)
    assert {auth for _, _, auth in seen} == {"Bearer graph-token", "Bearer engage-token"}


def _live(monkeypatch):
    monkeypatch.setenv("VIVA_ENGAGE_GRAPH_TOKEN", "graph-token")
    monkeypatch.setenv("VIVA_ENGAGE_TOKEN", "engage-token")


def _message(id, thread_id, likes, names=()):
    return {
        "id": id,
        "thread_id": thread_id,
        "group_id": 190336212210,
        "sender_id": 7,
        "created_at": "2026/09/22 10:00:00 +0000",
        "body": {"plain": "Copilot tips for credit memos"},
        "liked_by": {"count": likes, "names": [{"user_id": n, "full_name": "Someone"} for n in names]},
    }


def test_a_like_reaches_viva_engage_and_the_count_shown_is_viva_engage_s_own(monkeypatch):
    _live(monkeypatch)
    calls = []
    state = {"liked": False}

    def answer(service, method, url, **kwargs):
        calls.append((method, url))
        if url.startswith(vivaengage.GRAPH):
            return http.Response(200, json.dumps({"value": []}))
        if url.endswith("/users/current.json"):
            return http.Response(200, json.dumps({"id": 42, "full_name": "Sai Vivek"}))
        if "/messages/liked_by/current.json" in url:
            state["liked"] = method == "POST"
            return http.Response(201 if state["liked"] else 200, "")
        liked = state["liked"]
        return http.Response(200, json.dumps({"messages": [_message(501, 501, 3 + liked, [42] if liked else [])], "references": []}))

    monkeypatch.setattr(http, "send", answer)
    like = f"{vivaengage.ENGAGE}/messages/liked_by/current.json?message_id=501"

    post = client.post("/api/community/posts/501/like").json()
    assert ("POST", like) in calls
    assert post["liked_by_me"] is True and post["like_count"] == 4

    post = client.delete("/api/community/posts/501/like").json()
    assert ("DELETE", like) in calls
    assert post["liked_by_me"] is False and post["like_count"] == 3

    # Only a Viva Engage message id is ever sent to Viva Engage.
    assert client.post("/api/community/posts/t-102/like").status_code == 404


def test_a_refused_like_says_why_and_is_not_kept_in_the_hub(monkeypatch):
    _live(monkeypatch)

    def refuse(service, method, url, **kwargs):
        raise http.ExternalError("Viva Engage", 403, "Forbidden")

    monkeypatch.setattr(http, "send", refuse)
    response = client.post("/api/community/posts/501/like")
    assert response.status_code == 502 and response.json()["detail"] == "Not posted: Viva Engage returned 403: Forbidden"


def test_a_live_search_asks_viva_engage_and_keeps_the_conversations(monkeypatch):
    _live(monkeypatch)
    seen = []

    def answer(service, method, url, **kwargs):
        seen.append(url)
        if url.startswith(vivaengage.GRAPH):
            return http.Response(200, json.dumps({"value": [{"id": GROUP_ID, "displayName": "AI Builders", "privacy": "public"}]}))
        if url.endswith("/users/current.json"):
            return http.Response(200, json.dumps({"id": 42}))
        return http.Response(
            200,
            json.dumps(
                {
                    "messages": {
                        # A conversation's opening post, and a reply further down another one.
                        "messages": [_message(601, 601, 2, [42]), _message(702, 700, 0)],
                        "references": [{"type": "user", "id": 7, "full_name": "Test Person"}],
                    },
                    "users": [],
                    "groups": [],
                    "topics": [],
                }
            ),
        )

    monkeypatch.setattr(http, "send", answer)
    feed = client.get("/api/community/feed", params={"q": "copilot tips", "community": GROUP_ID}).json()
    assert [p["id"] for p in feed["posts"]] == ["601"]
    post = feed["posts"][0]
    assert post["liked_by_me"] is True and post["community_id"] == GROUP_ID and post["author"]["name"] == "Test Person"
    search = next(u for u in seen if "/search.json" in u)
    assert "search=copilot+tips" in search and "search_group=190336212210" in search and "num_per_page=20" in search
