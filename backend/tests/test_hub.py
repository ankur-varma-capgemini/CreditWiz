"""The home assistant's graph: privacy first, rules before the model, a
deterministic governance gate, pillars in parallel, and telemetry that keeps
ids and measures, never what was asked."""

import json
import time

import pytest
from fastapi.testclient import TestClient

from app import database
from app.hub import guardrails, llm, pillars, planner, synthesis
from app.hub.guardrails import check, entitlements
from app.main import app
from app.prompts.store import store as prompt_store

client = TestClient(app)
RM = {"persona": "relationship_manager"}


def _ask(q: str, **extra) -> dict:
    response = client.post("/api/ask", json={"q": q, **RM, **extra})
    assert response.status_code == 200, response.text
    return response.json()


def _row(turn_id: str) -> dict:
    with database.connect() as conn:
        return dict(conn.execute("SELECT * FROM hub_sessions WHERE id=?", (turn_id,)).fetchone())


@pytest.fixture
def model(monkeypatch):
    """A stand-in for the two model calls that records what each was sent."""
    monkeypatch.setenv("CREDITWIZ_DISABLE_LLM", "0")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    sent: dict[str, list] = {"plan": [], "write": []}

    def plan(sanitized, persona, journeys, earlier, history=()):
        sent["plan"].append(sanitized)
        return llm.ModelPlan(small_talk=False, 
            intents=["find", "learn"],
            objective="Get ready for the meeting",
            activity="meeting-prep",
            needs=["Recent news"],
            sensitivity="client_confidential",
            sensitivity_reason="Names a client.",
            subqueries=[
                llm.PlannedQuery(pillar="prompts", query="client meeting brief", reformulated=True),
                llm.PlannedQuery(pillar="learning", query="client advisory skills", reformulated=True),
            ],
        )

    def write(request, intents, job, items, on_delta=None):
        sent["write"].append((request, items))
        return f"Start with {items[0][1]} before you see [CLIENT]."

    monkeypatch.setattr(llm, "plan", plan)
    monkeypatch.setattr(llm, "write", write)
    return sent


# ------------------------------------------------------------------ privacy


def test_names_accounts_and_emails_are_masked_before_anything_else_sees_them():
    p = check("Prep the Starbucks meeting: account 12345678, cfo@starbucks.com", None)
    assert "starbucks" not in p.masked.lower() and "12345678" not in p.masked
    assert p.masked == "Prep the [CLIENT] meeting: account [ACCOUNT], [EMAIL]"
    assert p.sensitivity == "client_confidential"
    # The prototype policy for client-confidential requests: the model gets the masked form.
    assert p.model_access == "masked" and p.model_view == p.masked


@pytest.mark.parametrize(
    ("query", "masked", "kept"),
    [
        # Found in the first live run: a client after "of" reached the model.
        ("I need a covenant scan before my review of Acme Holdings", "Acme Holdings", None),
        ("A memo regarding Globex for the credit committee", "Globex", None),
        ("Pricing against Initech on the refinancing", "Initech", None),
        # And a standard was masked as if it were a client.
        ("Training on IFRS 9 before the Q3 close", None, "IFRS 9"),
        ("An RWA and DSCR check for FY26", None, "RWA and DSCR check for FY26"),
    ],
)
def test_what_the_detector_masks_and_what_it_leaves(query, masked, kept):
    sanitized = check(query, None).masked
    if masked:
        assert masked not in sanitized and "[CLIENT]" in sanitized
    if kept:
        assert kept in sanitized and "[CLIENT]" not in sanitized


def test_the_conversations_client_is_masked_even_when_typed_in_lower_case():
    p = check("what about starbucks wallet share", "Starbucks")
    assert "starbucks" not in p.masked.lower()
    assert p.subject.name == "Starbucks" and p.subject_carried_over


def test_policy_decides_what_the_model_receives(model, monkeypatch):
    # If MUFG's policy lets client names go to the approved model, they go as typed.
    as_typed = guardrails.Policy(
        model_access={
            "public": "as_typed",
            "internal": "as_typed",
            "client_confidential": "as_typed",
            "confidential": "none",
        }
    )
    monkeypatch.setattr(guardrails, "policy", lambda: as_typed)
    body = _ask("Find a pitch prompt and a course to prepare for the Starbucks meeting")
    assert model["plan"] == ["Find a pitch prompt and a course to prepare for the Starbucks meeting"]
    assert body["plan"]["model_access"] == "as_typed"
    # Searches and the usage log get the masked form whatever the model policy says.
    assert body["plan"]["sanitized_query"] == "Find a pitch prompt and a course to prepare for the [CLIENT] meeting"
    assert body["task"]["loggable_query"] == body["plan"]["sanitized_query"]
    assert all("Starbucks" not in s["query"] for s in body["plan"]["subqueries"])
    assert any("as typed" in n and "to be confirmed" in n for n in body["plan"]["governance"])


def test_confidential_material_never_reaches_a_model(model):
    body = _ask("Summarise the confidential board pack and find a course on it")
    assert model["plan"] == [] and model["write"] == []
    assert body["plan"]["plan_source"] == "rules" and body["plan"]["reply_source"] == "rules"
    assert body["task"]["loggable_query"] == "[confidential request]"
    assert any("confidential" in n for n in body["plan"]["governance"])


# ---------------------------------------------------------- rules and model


def test_every_task_is_planned_and_answered_by_the_model(model):
    # Even one the rules could have read on their own.
    body = _ask("Who can help with a credit request?")
    assert model["plan"] == ["Who can help with a credit request?"]
    assert len(model["write"]) == 1
    assert body["plan"]["plan_source"] == "claude" and body["plan"]["reply_source"] == "claude"
    assert body["plan"]["model"]


def test_two_intents_are_decomposed_by_the_model_which_never_sees_the_client(model):
    body = _ask("Find a pitch prompt and a course to prepare for the Starbucks meeting")
    assert model["plan"] == ["Find a pitch prompt and a course to prepare for the [CLIENT] meeting"]
    assert body["plan"]["plan_source"] == "claude"
    assert body["task"]["intents"] == ["find", "learn"]
    assert body["task"]["activity"]["id"] == "meeting-prep"
    assert {s["pillar"]: s["reformulated"] for s in body["plan"]["subqueries"]} == {"prompts": True, "learning": True}
    # The model wrote the reply from masked text; the person sees their client.
    assert body["plan"]["reply_source"] == "claude"
    assert all("Starbucks" not in sanitized for sanitized, _ in model["write"])
    assert "Starbucks" in body["reply"] and "[CLIENT]" not in body["reply"]


def test_a_request_asked_again_is_read_again(model):
    q = "Find a pitch prompt and a course for coverage planning"
    _ask(q)
    body = _ask(q)
    assert len(model["plan"]) == 2 and len(model["write"]) == 2
    assert body["plan"]["plan_source"] == "claude"


def test_a_failed_model_call_falls_back_to_rules(model, monkeypatch):
    monkeypatch.setattr(llm, "plan", lambda *args: None)
    body = _ask("Find a pitch prompt and a course for onboarding")
    assert body["plan"]["plan_source"] == "rules"
    assert body["task"]["intents"] == ["learn", "find"]


def test_a_model_reply_that_names_nothing_found_is_not_used(model, monkeypatch):
    monkeypatch.setattr(llm, "write", lambda *args, **kwargs: "Try the Acme Super Agent at https://example.com")
    body = _ask("Find a pitch prompt and a course to prepare for the Starbucks meeting")
    assert body["plan"]["reply_source"] == "rules"
    assert "example.com" not in body["reply"]


# ------------------------------------------------------------- governance


def test_the_gate_says_what_it_did_and_retrieval_never_sees_the_name():
    body = _ask("Prepare for a client meeting with Starbucks")
    assert body["plan"]["sanitized_query"] == "Prepare for a client meeting with [CLIENT]"
    notes = " ".join(body["plan"]["governance"])
    assert "masked" in notes and "access rules" in notes and "to be confirmed" in notes
    assert body["plan"]["model_access"] == "masked"
    for s in body["plan"]["subqueries"]:
        assert "Starbucks" not in s["query"] and "[CLIENT]" not in s["query"]


def test_high_risk_prompts_stay_with_their_own_desk():
    # The default test user is a compliance analyst, on no prompt desk.
    ents = entitlements()
    assert ents.desk is None
    assert all(p.risk != "High" for p in ents.prompts)
    high = [p for p in prompt_store.library.prompts if p.risk == "High"]
    assert high and ents.withheld_prompts == len(high)


def test_a_desk_sees_its_own_high_risk_prompts():
    client.cookies.clear()
    assert client.post("/api/auth/demo", json={"user_id": "demo-risk"}).status_code == 200
    from app import auth

    token = auth.current_id.set("demo-risk")
    try:
        ents = entitlements()
    finally:
        auth.current_id.reset(token)
    own_high = [p for p in prompt_store.library.prompts if p.risk == "High" and p.desk == "risk-analyst"]
    assert own_high and all(p in ents.prompts for p in own_high)


def test_catalogue_words_route_the_request_but_do_not_count_against_matches():
    body = _ask("Find a prompt for a covenant scan")
    queries = {s["pillar"]: s["query"] for s in body["plan"]["subqueries"]}
    assert queries["prompts"] == "covenant scan"
    assert body["pillars"][0]["hits"], "the covenant prompts are found"


# --------------------------------------------------------------- fan-out


def test_the_pillars_fan_out_in_parallel_and_fan_in_once(monkeypatch):
    def slow(*args, **kwargs):
        time.sleep(0.3)
        return pillars.Run()

    for name in ("prompts", "learning", "marketplace"):
        monkeypatch.setattr(pillars, name, slow)
    body = _ask("Find an agent, a prompt and a course on covenant monitoring")
    t = body["plan"]["timings_ms"]
    assert set(body["plan"]["selected_pillars"]) == {"learning", "prompts", "marketplace"}
    assert all(t[f"pillar {p}"] >= 290 for p in body["plan"]["selected_pillars"])
    # Three 300 ms pillars one after another would take 900 ms.
    assert t["pillars (parallel)"] < 600
    assert [g["pillar"] for g in body["pillars"]] == body["plan"]["selected_pillars"]


def test_one_pillar_failing_costs_only_its_own_group(monkeypatch):
    def down(*args, **kwargs):
        raise RuntimeError("index unavailable")

    monkeypatch.setattr(pillars, "marketplace", down)
    body = _ask("Find an agent or a prompt for a covenant scan")
    groups = {g["pillar"]: g for g in body["pillars"]}
    assert groups["marketplace"]["hits"] == []
    assert groups["prompts"]["hits"]


def test_each_pillar_finds_its_own_kind_of_thing():
    body = _ask("Find a prompt and a course on covenant monitoring")
    groups = {g["pillar"]: g for g in body["pillars"]}
    assert groups["prompts"]["hits"][0]["title"] == "Covenant compliance monitor"
    assert all(h["ref"].startswith("prompt:") for h in groups["prompts"]["hits"])
    assert all(h["ref"].startswith("learning:") for h in groups["learning"]["hits"])


def test_the_jobs_own_toolkit_is_not_repeated_under_a_pillar():
    body = _ask("Prepare for a client meeting")
    toolkit = {c["ref"] for c in body["recommended"]}
    assert toolkit
    for g in body["pillars"]:
        assert not toolkit & {h["ref"] for h in g["hits"]}


# ------------------------------------------------------------------ draft


def test_asking_for_a_prompt_to_be_written_returns_a_draft_from_validated_ones():
    body = _ask("Write a prompt that summarises an annual review pack")
    assert "contribute" in body["task"]["intents"]
    draft = body["draft"]
    assert draft["learned_from"] and "CONSTRAINTS" in draft["body"]
    assert draft["goal"] == "summarises an annual review pack"


# --------------------------------------------------------------- telemetry


def test_telemetry_keeps_ids_and_measures_never_the_request():
    body = _ask("Prepare for a client meeting with Starbucks")
    row = _row(body["turn_id"])
    stored = json.dumps(row)
    assert "Starbucks" not in stored and "meeting with" not in stored
    assert json.loads(row["intents"]) == ["find"] and row["activity"] == "meeting-prep"
    assert row["session_id"] == body["session_id"]
    assert row["sensitivity"] == "client_confidential" and row["plan_source"] == "rules"
    assert json.loads(row["recommended_asset_ids"])
    assert row["latency_ms"] >= 0


def test_feedback_and_what_was_opened_are_recorded_against_the_answer():
    body = _ask("Who can help with a credit request?")
    ref = body["recommended"][0]["ref"]
    turn = body["turn_id"]
    assert client.post(f"/api/ask/turns/{turn}/feedback", json={"helpful": True}).status_code == 200
    assert client.post(f"/api/ask/turns/{turn}/selected", json={"ref": ref}).status_code == 200
    # Only what the answer showed can be recorded, so the column holds ids alone.
    assert client.post(f"/api/ask/turns/{turn}/selected", json={"ref": "agent:never-shown"}).status_code == 404
    row = _row(turn)
    assert row["feedback"] == "helpful"
    assert json.loads(row["selected_asset_ids"]) == [ref]


def test_someone_elses_answer_cannot_be_rated():
    body = _ask("Who can help with a credit request?")
    client.cookies.clear()
    assert client.post("/api/auth/demo", json={"user_id": "demo-rm"}).status_code == 200
    assert client.post(f"/api/ask/turns/{body['turn_id']}/feedback", json={"helpful": False}).status_code == 404


def test_a_conversation_keeps_one_session_across_turns():
    first = _ask("Who can help with a credit request?")
    second = _ask("And who owns it?", journey="credit-request", session=first["session_id"])
    assert second["session_id"] == first["session_id"]
    assert second["turn_id"] != first["turn_id"]
