"""The relationship manager slice: persona, journeys, intent, context, trust."""

import pytest
from fastapi.testclient import TestClient

from app import identity
from app.journeys.store import validate_refs
from app.main import app

client = TestClient(app)
RM = {"persona": "relationship_manager"}

RM_JOURNEYS = [
    "coverage-planning",
    "wallet-share",
    "meeting-prep",
    "deal-origination",
    "client-onboarding",
    "credit-request",
    "cross-sell",
    "portfolio-review",
]

COMPLIANCE_JOURNEYS = [
    "kyc-review",
    "identity-verification",
    "sanctions-screening",
    "adverse-media",
    "beneficial-ownership",
    "tax-classification",
    "client-outreach",
    "policy-questions",
]


def _ask(q: str, **extra) -> dict:
    response = client.post("/api/ask", json={"q": q, **RM, **extra}, headers={"X-CreditWiz-Request": "1"})
    assert response.status_code == 200, response.text
    return response.json()


def test_a_question_travels_in_the_body_not_the_url():
    # URLs land in server and proxy access logs; a question can name a client.
    # There is no GET route; the app's catch-all refuses /api/ paths it does not serve.
    assert client.get("/api/ask", params={"q": "Prepare for a meeting with Starbucks"}).status_code in (404, 405)


def test_the_client_stays_for_the_rest_of_the_conversation():
    t = _ask("Who can help?", journey="meeting-prep", subject="Starbucks")["task"]
    assert t["subject"] == {"name": "Starbucks", "kind": "client"}
    assert t["subject_carried_over"] is True
    assert t["sensitivity"] == "client_confidential"
    assert "Starbucks" not in t["loggable_query"]


def test_a_relationship_manager_is_their_own_persona():
    profile = identity.DirectoryProfile(
        id="rm",
        name="Morgan Blake",
        first_name="Morgan",
        initials="MB",
        job_title="Relationship Manager",
        department="Corporate Banking",
    )
    assert identity.derive_persona(profile).id == "relationship_manager"


def test_the_relationship_manager_demo_account_is_offered():
    users = client.get("/api/auth/options").json()["users"]
    assert any(u["role"] == "Relationship Manager" for u in users)


def test_each_role_sees_its_own_journeys_and_a_role_without_any_sees_none():
    body = client.get("/api/journeys", params=RM).json()
    assert body["persona_label"] == "Relationship Manager"
    assert [j["id"] for j in body["journeys"]] == RM_JOURNEYS
    assert len(body["examples"]) == 4
    # The default test user is a compliance analyst.
    mine = client.get("/api/journeys").json()
    assert [j["id"] for j in mine["journeys"]] == COMPLIANCE_JOURNEYS
    assert len(mine["examples"]) == 4
    assert client.get("/api/journeys", params={"persona": "developer"}).json()["journeys"] == []


def test_every_journey_points_at_real_records():
    assert validate_refs() == []


def test_a_journey_says_where_the_work_happens():
    page = client.get("/api/journeys/meeting-prep", params=RM).json()
    assert [s["system"] for s in page["systems"]] == ["Customer 360", "Market intelligence", "Salesforce"]
    intents = [a["intent"] for a in page["assets"]]
    assert intents == sorted(intents, key=["find", "learn", "improve", "ask", "contribute"].index)


def test_unconfirmed_trust_is_left_blank_not_invented():
    page = client.get("/api/journeys/meeting-prep", params=RM).json()
    c360 = next(a for a in page["assets"] if a["ref"] == "asset:customer-360")
    assert c360["provided_by"] == "Customer 360"
    assert c360["trust"]["owner_team"] == ""
    assert c360["trust"]["approved_by"] == ""
    assert c360["action_url"] == ""


@pytest.mark.parametrize(
    ("query", "intent", "journey"),
    [
        ("Prepare for a client meeting", "find", "meeting-prep"),
        ("Make my portfolio review faster", "improve", "portfolio-review"),
        ("Who can help with a credit request?", "ask", "credit-request"),
        ("Share a prompt I use for account plans", "contribute", "coverage-planning"),
        ("How do I raise a credit request?", "learn", "credit-request"),
        ("What's our wallet share with this client?", "find", "wallet-share"),
    ],
)
def test_the_home_search_reads_intent_and_the_job(query, intent, journey):
    body = _ask(query)
    assert body["task"]["intent"] == intent
    assert body["task"]["activity"]["id"] == journey
    # What they came for comes first.
    assert body["recommended"][0]["intent"] == intent


@pytest.mark.parametrize(
    ("query", "intent", "journey"),
    [
        ("Where does a client's KYC review stand?", "find", "kyc-review"),
        ("Speed up sanctions screening", "improve", "sanctions-screening"),
        ("Who can help with beneficial ownership?", "ask", "beneficial-ownership"),
        ("How do I verify a client's identity?", "learn", "identity-verification"),
    ],
)
def test_a_compliance_analysts_examples_land_on_their_jobs(query, intent, journey):
    response = client.post("/api/ask", json={"q": query}, headers={"X-CreditWiz-Request": "1"})
    body = response.json()
    assert body["task"]["intent"] == intent
    assert body["task"]["activity"]["id"] == journey
    assert body["recommended"][0]["intent"] == intent


def test_a_community_whose_owner_is_unconfirmed_says_nothing_about_one():
    page = client.get("/api/journeys/sanctions-screening").json()
    community = next(a for a in page["assets"] if a["ref"] == "asset:compliance-ai")
    assert community["action_url"] == "/community?c=compliance-ai"
    assert community["trust"]["owner_team"] == ""
    assert community["trust"]["guardrails"] == []


def test_a_request_outside_any_journey_gets_intent_but_no_journey():
    body = _ask("football results")
    assert body["task"]["intent"] == "find"
    assert body["task"]["activity"] is None and body["recommended"] == []
    assert body["follow_ups"] == []


def test_the_reply_names_only_what_the_journey_recommends():
    body = _ask("Who can help with a credit request?")
    assert body["reply"] == "For help with credit requests, start with Credit risk partner."
    # Asking who can help brings the job's people, not its agents too.
    assert "Credit risk partner" in {a["title"] for a in body["recommended"]}
    assert {a["kind"] for a in body["recommended"]} <= {"expert", "community"}


def test_follow_ups_stay_on_the_same_job_with_a_new_reason():
    body = _ask("Who can help with a credit request?")
    assert body["follow_ups"]
    for follow_up in body["follow_ups"]:
        nxt = _ask(follow_up["query"])
        assert nxt["task"]["activity"]["id"] == "credit-request"
        assert nxt["task"]["intent"] != "ask"


def test_a_follow_up_that_names_no_job_stays_on_the_last_one():
    body = _ask("And who owns it?", journey="credit-request")
    assert body["task"]["intent"] == "ask"
    assert body["task"]["activity"]["id"] == "credit-request"
    assert body["task"]["carried_over"] is True


# ---------------------------------------------------------------- context


def test_the_task_names_the_client_for_this_conversation_only():
    body = _ask("Prepare for a client meeting with Starbucks")
    t = body["task"]
    assert t["subject"] == {"name": "Starbucks", "kind": "client"}
    assert t["activity"]["id"] == "meeting-prep"
    assert t["objective"] == "Prepare for a client meeting"
    assert t["needs"] == ["Existing products and relationship", "Recent news and events", "Cross-sell opportunities"]
    assert t["sensitivity"] == "client_confidential"
    # The name never reaches the usage log.
    assert t["loggable_query"] == "Prepare for a client meeting with [CLIENT]"
    # Nor the profile.
    assert "Starbucks" not in str(body["user"])


@pytest.mark.parametrize(
    ("query", "subject"),
    [
        ("Prep me for the Starbucks meeting", "Starbucks"),
        ("What's our wallet share with Starbucks?", "Starbucks"),
        ("What systems do I need for Customer 360?", None),
        ("Who can help with a credit request?", None),
        ("Share a prompt I use for account plans", None),
        ("Help with KYC for onboarding", None),
    ],
)
def test_only_a_name_in_a_client_position_is_a_subject(query, subject):
    found = _ask(query)["task"]["subject"]
    assert (found or {}).get("name") == subject


def test_confidential_material_is_kept_out_of_the_log():
    t = _ask("Summarise the confidential board pack")["task"]
    assert t["sensitivity"] == "confidential"
    assert t["loggable_query"] == "[confidential request]"


def test_an_ordinary_request_is_internal_and_logged_as_typed():
    t = _ask("Who can help with a credit request?")["task"]
    assert t["sensitivity"] == "internal"
    assert t["loggable_query"] == "Who can help with a credit request?"


def test_user_context_carries_function_maturity_and_entitlements():
    user = client.get("/api/context/me").json()
    # Department, then business unit, as the directory states them.
    assert user["function"] == "Compliance, Americas Financial Crime Compliance"
    assert user["maturity"] in {"beginner", "developing", "experienced"}
    assert user["maturity_basis"].startswith("Inferred from learning progress")
    assert "AI-Hub-Users" in user["entitlements"]
    assert user["role_interests"]


def test_an_admin_preview_changes_the_role_and_nothing_else():
    user = _ask("Prepare for a client meeting")["user"]
    assert user["persona"] == "relationship_manager"
    assert user["persona_rule"] == "admin preview of this role"
    # Department, then business unit, as the directory states them.
    assert user["function"] == "Compliance, Americas Financial Crime Compliance"
