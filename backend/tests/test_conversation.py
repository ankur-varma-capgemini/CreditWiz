"""The conversation intent gate: small talk answered directly, for nothing;
a greeting in front of a request set aside; only a task goes on."""

import pytest
from fastapi.testclient import TestClient

from app import database
from app.hub import conversation, guardrails, llm, pillars
from app.journeys.intent import classify
from app.main import app

client = TestClient(app)
RM = {"persona": "relationship_manager"}


def _ask(q: str, **extra) -> dict:
    response = client.post("/api/ask", json={"q": q, **RM, **extra})
    assert response.status_code == 200, response.text
    return response.json()


def _recorded() -> int:
    with database.connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM hub_sessions").fetchone()[0]


@pytest.fixture
def spies(monkeypatch):
    """Records every costly step the gate is meant to keep small talk out of."""
    monkeypatch.setenv("CREDITWIZ_DISABLE_LLM", "0")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    calls: list[str] = []
    monkeypatch.setattr(llm, "plan", lambda *a, **k: calls.append("model") or None)
    monkeypatch.setattr(llm, "write", lambda *a, **k: calls.append("model") or None)
    # A natural reply is allowed; returning nothing here keeps the fixed line.
    monkeypatch.setattr(llm, "converse", lambda *a, **k: calls.append("converse") or None)
    for module, name in (
        (guardrails, "check"),
        (pillars, "prompts"),
        (pillars, "marketplace"),
        (pillars, "learning"),
        (pillars, "community"),
    ):
        original = getattr(module, name)

        def spy(*args, _name=name, _original=original, **kwargs):
            calls.append(_name)
            return _original(*args, **kwargs)

        monkeypatch.setattr(module, name, spy)
    return calls


# -------------------------------------------------------------------- gate


@pytest.mark.parametrize(
    ("query", "kind"),
    [
        # Greetings, as people actually type them.
        ("Hi!", "greeting"),
        ("  HELLO  ", "greeting"),
        ("hy", "greeting"),
        ("hii", "greeting"),
        ("hiiii!!", "greeting"),
        ("heyy", "greeting"),
        ("heyyy there", "greeting"),
        ("helloo", "greeting"),
        ("helo", "greeting"),
        ("hlo", "greeting"),
        ("hai", "greeting"),
        ("yo", "greeting"),
        ("sup", "greeting"),
        ("gm", "greeting"),
        ("hello there", "greeting"),
        ("Good morning", "greeting"),
        ("morning!", "greeting"),
        ("hwllo", "greeting"),
        # Asking how the assistant is.
        ("Hey, how are you?", "greeting"),
        ("how r u", "greeting"),
        ("how are u", "greeting"),
        ("how's your day going?", "greeting"),
        ("what's up", "greeting"),
        # Small talk.
        ("i'm good", "small_talk"),
        ("im fine thanks, how are you", "small_talk"),
        ("tell me a joke", "small_talk"),
        ("lol", "small_talk"),
        ("hahaha", "small_talk"),
        ("hmm", "small_talk"),
        ("ok", "small_talk"),
        ("okkk", "small_talk"),
        ("cool", "small_talk"),
        ("test", "small_talk"),
        ("are you there?", "small_talk"),
        # Thanks and goodbyes.
        ("thanks!", "thanks"),
        ("Thank you so much", "thanks"),
        ("thank u", "thanks"),
        ("thx", "thanks"),
        ("ty", "thanks"),
        ("tysm", "thanks"),
        ("thnaks", "thanks"),
        ("bye", "goodbye"),
        ("byeee", "goodbye"),
        ("cya", "goodbye"),
        ("see ya", "goodbye"),
        ("ttyl", "goodbye"),
        ("good night", "goodbye"),
        ("Thanks, that's all", "goodbye"),
        # What the assistant is and can do.
        ("Help", "help"),
        ("What can you do?", "help"),
        ("Hi, what can you do?", "help"),
        ("Can you help me?", "help"),
        ("who are you", "help"),
        ("what's your name?", "help"),
        ("are you a bot", "help"),
    ],
)
def test_small_talk_is_recognised_after_normalising(query, kind):
    gate = conversation.read(query)
    assert gate.kind == kind and gate.task_query == ""


@pytest.mark.parametrize(
    ("query", "opening", "routed"),
    [
        ("Hi, can you find me a KYC agent?", "Hi", "find me a KYC agent?"),
        (
            "Good morning, I have a Starbucks meeting. Find me tools and teach me how to use them.",
            "Good morning",
            "I have a Starbucks meeting. Find me tools and teach me how to use them.",
        ),
        ("Find me a KYC agent, thanks!", "", "Find me a KYC agent"),
        ("hy, find me a sanctions agent", "hy", "find me a sanctions agent"),
        ("ok thx, now show me a covenant prompt", "ok thx", "now show me a covenant prompt"),
        # Not greetings at all.
        ("Hiring plan for the KYC team", "", "Hiring plan for the KYC team"),
        ("Morning meeting prep for the coverage team", "", "Morning meeting prep for the coverage team"),
        ("Help with KYC for onboarding", "", "Help with KYC for onboarding"),
        ("Fine-tuning a model for KYC", "", "Fine-tuning a model for KYC"),
        ("GM approval for the facility", "", "GM approval for the facility"),
        ("Supply chain finance for a client", "", "Supply chain finance for a client"),
        ("KYC", "", "KYC"),
        ("sanctions", "", "sanctions"),
    ],
)
def test_a_greeting_in_front_of_a_request_is_set_aside(query, opening, routed):
    gate = conversation.read(query)
    assert gate.kind == "task"
    assert gate.opening == opening and gate.task_query == routed


# ---------------------------------------------------------------- answers


def test_a_greeting_is_answered_with_no_search_no_model_and_no_record(spies):
    before = _recorded()
    body = _ask("Hello!")
    first = body["user"]["display_name"].split()[0]
    assert body["kind"] == "greeting"
    assert body["reply"] == f"Hi {first}! How can I help you today?"
    assert body["task"] is None and body["plan"] is None and body["pillars"] == []
    assert body["turn_id"] is None
    # Something to try next: the persona's own example requests.
    assert [f["query"] for f in body["follow_ups"]][:1] == ["Prepare for a client meeting"]
    assert not {"model", "prompts", "marketplace", "learning", "community"} & set(spies)
    assert _recorded() == before


def test_the_reply_matches_the_greeting():
    assert _ask("Good morning")["reply"].startswith("Good morning, ")
    assert "Doing well" in _ask("Hey, how are you?")["reply"]
    assert "Doing well" in _ask("how r u")["reply"]
    assert _ask("hy")["reply"].startswith("Hi ")
    assert _ask("thx")["reply"].startswith("You're welcome")
    assert _ask("cya")["reply"].startswith("Goodbye")
    assert _ask("i'm good")["reply"].startswith("Glad to hear it")
    assert "jokes to your colleagues" in _ask("tell me a joke")["reply"]
    assert _ask("test")["reply"].startswith("I'm here and working")
    assert _ask("lol")["reply"].startswith("Anything else I can help with")
    assert _ask("who are you")["reply"].startswith("I'm the Nexus assistant")


def test_small_talk_costs_nothing_either(spies):
    before = _recorded()
    for q in ("hy", "how r u", "lol", "tell me a joke", "thx", "cya"):
        body = _ask(q)
        assert body["kind"] != "task" and body["pillars"] == [], q
    assert not {"model", "prompts", "marketplace", "learning", "community"} & set(spies)
    assert _recorded() == before


def test_something_the_hub_has_nothing_for_gets_what_it_can_do(spies):
    body = _ask("xyzzy plugh")
    assert body["kind"] == "task"
    assert body["reply"].startswith("I didn't find anything in Nexus for that")
    assert [c["intent"] for c in body["capabilities"]] == ["learn", "find", "improve", "ask", "contribute"]
    # A task, so the model was asked to read it; it returned nothing here.
    assert "model" in spies
    assert body["plan"]["plan_source"] == "rules"


@pytest.fixture
def talk(monkeypatch):
    """A model that answers conversation, recording what it was told."""
    monkeypatch.setenv("CREDITWIZ_DISABLE_LLM", "0")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    heard: list[tuple] = []

    def converse(message, situation, name, role, earlier, on_delta=None):
        heard.append((message, situation, name, role, earlier))
        text = f"Doing great, thanks {name}! What are you working on today?"
        if on_delta:
            on_delta(text)
        return text

    monkeypatch.setattr(llm, "converse", converse)
    return heard


def test_conversation_is_answered_naturally_when_the_model_may_answer(talk):
    body = _ask("how are you doing today", journey="portfolio-review")
    assert body["kind"] == "greeting" and body["reply_source"] == "claude"
    assert body["reply"].startswith("Doing great, thanks ")
    message, situation, name, role, earlier = talk[0]
    assert situation == conversation.SITUATION["greeting"]
    # It knows who it is talking to and what the conversation was about.
    assert role == "Relationship Manager" and earlier == "Portfolio reviews"
    assert body["pillars"] == [] and body["turn_id"] is None


def test_a_reaction_is_conversation_not_a_request_about_the_last_job(talk):
    # "nice" after an answer once became "Ask about portfolio reviews".
    body = _ask("nice", journey="portfolio-review", subject="Globex")
    assert body["kind"] == "small_talk" and body["task"] is None
    assert talk[0][1] == conversation.SITUATION["small_talk"]


def test_the_same_small_talk_is_answered_afresh_each_time(talk):
    _ask("hy")
    _ask("hy")
    assert len(talk) == 2


def test_a_natural_reply_that_does_not_fit_falls_back_to_the_fixed_line(monkeypatch):
    monkeypatch.setenv("CREDITWIZ_DISABLE_LLM", "0")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(llm, "converse", lambda *a, **k: "- see https://example.com for jokes")
    body = _ask("hy")
    assert body["reply_source"] == "rules" and body["reply"].startswith("Hi ")


def test_the_model_can_read_a_message_the_rules_missed_as_conversation(monkeypatch):
    monkeypatch.setenv("CREDITWIZ_DISABLE_LLM", "0")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(
        llm,
        "plan",
        lambda *a: llm.ModelPlan(
            small_talk=True,
            intents=["find"],
            objective="",
            activity=None,
            needs=[],
            sensitivity="internal",
            sensitivity_reason="",
            subqueries=[],
        ),
    )
    monkeypatch.setattr(llm, "converse", lambda *a, **k: None)
    before = _recorded()
    # The model reads it, and reads it as conversation.
    body = _ask("that makes sense, carry on")
    assert body["kind"] == "small_talk"
    assert body["pillars"] == [] and body["task"] is None and body["turn_id"] is None
    assert _recorded() == before


def test_a_specific_request_that_finds_nothing_says_so_plainly():
    body = _ask("Find a course on underwater basket weaving")
    assert body["capabilities"] == []
    assert body["reply"].startswith("I searched")


def test_help_explains_the_five_capabilities_each_with_a_request_to_try(spies):
    body = _ask("What can you do?")
    caps = body["capabilities"]
    assert body["kind"] == "help"
    assert [c["intent"] for c in caps] == ["learn", "find", "improve", "ask", "contribute"]
    # Each example, sent back, is read as the intent it illustrates.
    assert all(classify(c["example"])[0] == c["intent"] for c in caps)
    # A relationship manager's own requests are used where they fit.
    assert "Who can help with a credit request?" in [c["example"] for c in caps]
    assert not {"model", "prompts", "marketplace", "learning", "community"} & set(spies)


def test_the_request_after_a_greeting_is_routed_on_its_own(spies):
    body = _ask("Hi, can you find me a KYC agent?")
    assert body["kind"] == "task"
    assert body["plan"]["opening"] == "Hi"
    assert body["plan"]["sanitized_query"] == "find me a KYC agent?"
    assert body["task"]["intents"] == ["find"]
    # It named an agent, so Discover answers it alone.
    assert body["plan"]["selected_pillars"] == ["marketplace"]
    assert body["plan"]["subqueries"][0]["query"] == "KYC"
    # The model was asked to plan the request; the greeting never reached it.
    assert "model" in spies


def test_a_greeting_never_reaches_the_model_and_the_client_is_still_masked(monkeypatch):
    monkeypatch.setenv("CREDITWIZ_DISABLE_LLM", "0")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    sent: list[str] = []
    monkeypatch.setattr(llm, "plan", lambda request, *a: sent.append(request) or None)
    monkeypatch.setattr(llm, "write", lambda *a, **k: None)
    body = _ask("Good morning, I have a Starbucks meeting. Find me tools and teach me how to use them.")
    assert sent == ["I have a [CLIENT] meeting. Find me tools and teach me how to use them."]
    assert body["plan"]["opening"] == "Good morning"
    # The model returned nothing, so rules routed it: tools to Discover, the how-to to Learning.
    assert body["task"]["intents"] == ["learn", "find"]
    assert set(body["plan"]["selected_pillars"]) == {"marketplace", "learning"}
