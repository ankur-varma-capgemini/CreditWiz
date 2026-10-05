"""Follow-ups read with the conversation they continue: "is there a quick
reference for it too?" after asking for a course on IFRS 9 is about IFRS 9."""

import pytest
from fastapi.testclient import TestClient

from app.hub import followup, llm
from app.main import app

client = TestClient(app)


def _ask(q: str, history: list[str] | None = None) -> dict:
    response = client.post("/api/ask", json={"q": q, "history": history or []})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize(
    ("request_", "about"),
    [
        ("Find a course on IFRS 9", "IFRS 9"),
        ("Who can help with sanctions screening?", "sanctions screening"),
        ("Is there a quick reference on Basel III?", "Basel III"),
        ("Find an agent", ""),
    ],
)
def test_a_topic_is_the_request_s_own_words_without_where_or_how_it_asked(request_, about):
    assert followup.topic(request_) == about


@pytest.mark.parametrize(
    ("request_", "history", "carried"),
    [
        # Names no topic of its own.
        ("Is there a quick reference for it too?", ["Find a course on IFRS 9"], "IFRS 9"),
        ("any agents too?", ["Find a course on IFRS 9"], "IFRS 9"),
        # Points straight back and says little else.
        ("Who owns it?", ["Who can help with sanctions screening?"], "sanctions screening"),
        # A chain of follow-ups leads back to the request that set the topic.
        ("And who can help with that?", ["Find a course on IFRS 9", "any agents for it?"], "IFRS 9"),
        # Small talk in between carries no topic.
        ("any courses on it?", ["Find a course on IFRS 9", "thanks!"], "IFRS 9"),
        # A topic of its own is kept: "that" here points at nothing.
        ("Find an agent that screens sanctions", ["Find a course on IFRS 9"], ""),
        ("what about Basel III?", ["Find a course on IFRS 9"], ""),
        # Nothing earlier, nothing to carry.
        ("Is there a quick reference for it too?", [], ""),
    ],
)
def test_a_follow_up_is_read_with_the_earlier_topic_only_when_it_has_none(request_, history, carried):
    reading = followup.read(request_, history)
    assert reading.topic == carried
    assert reading.text == (f"{request_} — {carried}" if carried else request_)


def test_continuing_is_judged_from_the_request_alone():
    # The job carries over on these with no history at all, as before.
    assert followup.follows_up("And who owns it?")
    assert followup.follows_up("any agents too?")
    assert followup.follows_up("what about Basel III?")
    assert not followup.follows_up("Find a course on IFRS 9")


def test_the_hub_answers_a_follow_up_about_the_earlier_topic():
    body = _ask("Is there a quick reference for it too?", ["Find a course on IFRS 9"])
    assert body["plan"]["follows_on"] == "IFRS 9"
    # A quick reference is Learning's, and Learning was asked about IFRS 9.
    assert body["plan"]["selected_pillars"] == ["learning"]
    learning = next(g for g in body["pillars"] if g["pillar"] == "learning")
    assert "IFRS 9" in learning["query"]
    assert any("IFRS 9" in h["title"] for h in learning["hits"])


def test_without_the_conversation_nothing_is_carried():
    body = _ask("Is there a quick reference for it too?")
    assert body["plan"]["follows_on"] == ""
    assert "IFRS" not in body["plan"]["sanitized_query"]


def test_a_carried_client_name_is_masked_like_one_typed():
    body = _ask("any agents for it?", ["Prepare for a client meeting with Starbucks"])
    assert "Starbucks" in body["plan"]["follows_on"]
    assert body["task"]["subject"]["name"] == "Starbucks"
    # Searches and the usage log never see the name, carried or typed.
    assert "Starbucks" not in body["plan"]["sanitized_query"]
    assert "Starbucks" not in body["task"]["loggable_query"]
    assert all("Starbucks" not in s["query"] for s in body["plan"]["subqueries"])


@pytest.fixture
def planner_model(monkeypatch):
    """A model planner that records what it was given and plans nothing, so rules answer."""
    monkeypatch.setenv("CREDITWIZ_DISABLE_LLM", "0")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(llm, "write", lambda *args, **kwargs: None)
    seen: list[tuple] = []

    def plan(*args):
        seen.append(args)
        return None

    monkeypatch.setattr(llm, "plan", plan)
    return seen


def test_the_model_planner_hears_the_earlier_requests_on_a_follow_up(planner_model):
    _ask("what about sanctions screening?", ["Find a course on IFRS 9"])
    request, _, _, _, history = planner_model[-1]
    # Its own topic is kept; the earlier request says what "what about" repeats.
    assert request == "what about sanctions screening?"
    assert history == ("Find a course on IFRS 9",)


def test_the_model_planner_does_not_hear_them_on_a_new_request(planner_model):
    _ask("Find a prompt for a credit memo", ["Find a course on IFRS 9"])
    assert planner_model[-1][4] == ()


def test_earlier_requests_reach_the_model_only_as_the_data_policy_allows(planner_model):
    _ask("what about the covenants?", ["Prepare for a client meeting with Starbucks"])
    history = planner_model[-1][4]
    assert history and all("Starbucks" not in h for h in history)
    assert "[CLIENT]" in history[0]


def test_the_history_is_bounded():
    too_many = client.post("/api/ask", json={"q": "any agents?", "history": ["Find a course on IFRS 9"] * 9})
    assert too_many.status_code == 422
    too_long = client.post("/api/ask", json={"q": "any agents?", "history": ["x" * 501]})
    assert too_long.status_code == 422
