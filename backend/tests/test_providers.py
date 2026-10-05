"""Learning providers, Microsoft sign-in and the Integrations page.

Pluralsight and Microsoft Entra need MUFG's credentials, so their live paths
are exercised against recorded response shapes. Microsoft Learn is public.
"""

import base64
import json
import time
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app import entra, http
from app.learning import mslearn
from app.main import app

client = TestClient(app)

MODULE = """![](/en-us/learn/achievements/generic-badge.svg)

# Explore Generative AI

- Module
- 9 Units

 Beginner

 Developer

Discover the fundamentals of generative AI and how this technology is transforming our approach to creativity and productivity.

## Learning objectives

By completing this module, you'll be able to:

- Distinguish between NLP, NLG and LLMs.
- Assess the differences between generative AI and traditional AI models.
- Evaluate how generative AI services like Microsoft Copilot can enhance creativity.

## Prerequisites

A basic understanding of AI concepts and technologies.

## Get started with Azure

Choose the Azure account that's right for you. [Sign up.](https://azure.microsoft.com/pricing/)

- [Introduction](1-introduction)
- [What is generative AI?](2-what-is-generative-ai)
- [Summary](9-summary)

Take the module assessment

Start
"""

PATH = """![](/en-us/training/achievements/generic-trophy.svg)

# Draft, analyze, and present with Microsoft Copilot

- Learning Path
- 7 Modules

## At a glance

- Level

[Beginner](/en-us/training/browse/?levels=beginner&amp;resource_type=learning%20path)
- Product

[Microsoft 365](/en-us/training/browse/?products=m365&amp;resource_type=learning%20path)

This course directs users to learn common prompt flows in Microsoft 365 apps.

## Modules in this learning path

[![](/en-us/training/achievements/generic-badge.svg)](../../modules/get-ready-work-microsoft-365-copilot/)

[Get ready to work with Microsoft Copilot](../../modules/get-ready-work-microsoft-365-copilot/)

Explore how Microsoft Copilot grounds responses.
"""

UNIT = """# What is generative AI?

Completed

- 8 minutes

Generative AI is transforming the approach to productivity.
"""


def test_a_learn_module_reads_as_its_parts():
    page = mslearn.parse_page("https://learn.microsoft.com/training/modules/explore-generative-ai/", MODULE)
    assert (page.title, page.kind, page.count, page.level) == ("Explore Generative AI", "Module", "9 units", "Beginner")
    assert page.summary.startswith("Discover the fundamentals")
    assert len(page.objectives) == 3 and page.prerequisites.startswith("A basic understanding")
    assert [u.url for u in page.units] == [
        "https://learn.microsoft.com/training/modules/explore-generative-ai/1-introduction",
        "https://learn.microsoft.com/training/modules/explore-generative-ai/2-what-is-generative-ai",
        "https://learn.microsoft.com/training/modules/explore-generative-ai/9-summary",
    ]
    # Badges, the Azure sign-up pitch, the assessment prompt and the tag lines are gone.
    for gone in ("achievements", "Sign up", "Take the module assessment", "\nStart", " Developer "):
        assert gone not in page.markdown
    assert "(https://learn.microsoft.com/training/modules/explore-generative-ai/1-introduction)" in page.markdown


def test_a_module_url_without_its_slash_still_resolves_units():
    page = mslearn.parse_page("https://learn.microsoft.com/training/modules/explore-generative-ai", MODULE)
    assert page.units[0].url == "https://learn.microsoft.com/training/modules/explore-generative-ai/1-introduction"


def test_a_learning_path_lists_its_modules():
    page = mslearn.parse_page("https://learn.microsoft.com/training/paths/get-started-with-microsoft-365-copilot/", PATH)
    assert (page.kind, page.count, page.level) == ("Learning path", "7 modules", "Beginner")
    assert page.summary.startswith("This course directs users")
    assert [(u.title, u.url) for u in page.units] == [
        ("Get ready to work with Microsoft Copilot", "https://learn.microsoft.com/training/modules/get-ready-work-microsoft-365-copilot/")
    ]
    assert "achievements" not in page.markdown and "At a glance" not in page.markdown


def test_a_unit_has_its_reading_time():
    page = mslearn.parse_page("https://learn.microsoft.com/training/modules/explore-generative-ai/2-what-is-generative-ai", UNIT)
    assert (page.kind, page.minutes) == ("Unit", 8)
    assert page.markdown == "Generative AI is transforming the approach to productivity."


def test_only_microsoft_learn_pages_are_read_in_the_hub():
    assert client.get("/api/learning/microsoft-learn/page", params={"url": "https://example.com/x"}).status_code == 422
    assert client.get("/api/learning/microsoft-learn/page", params={"url": "http://learn.microsoft.com/x"}).status_code == 422


def test_one_search_covers_both_providers_and_leaves_without_client_identifiers(monkeypatch):
    sent = []

    def learn(q, limit=8):
        sent.append(q)
        return [mslearn.LearnResult(title="Explore responsible AI", url="https://learn.microsoft.com/training/modules/responsible-ai/", excerpt="Principles")]

    monkeypatch.setattr(mslearn, "search", learn)
    groups = client.get("/api/learning/providers/search", params={"q": "summarise mail from jane.doe@client-example.com"}).json()
    assert sent and "@" not in sent[0] and "summarise" in sent[0]
    by = {g["provider"]: g for g in groups}
    # Without a key, Pluralsight says so rather than returning nothing silently.
    assert by["Pluralsight"]["state"] == "sample" and "isn't connected" in by["Pluralsight"]["note"]
    assert by["Microsoft Learn"]["state"] == "live"
    assert by["Microsoft Learn"]["results"] == [
        {
            "title": "Explore responsible AI",
            "url": "https://learn.microsoft.com/training/modules/responsible-ai/",
            "excerpt": "Principles",
            "level": "",
            "duration_seconds": 0,
            "read_in_hub": True,
        }
    ]


def test_learn_search_results_are_one_per_page_with_a_clean_excerpt(monkeypatch):
    rows = {
        "results": [
            {
                "title": "What is Responsible AI?",
                "contentUrl": "https://learn.microsoft.com/azure/machine-learning/concept-responsible-ai#principles",
                "content": "APPLIES TO: [Azure CLI ml extension v2](https://x)\n\nWhat is Responsible AI? Responsible AI is an approach.",
            },
            {
                "title": "What is Responsible AI?",
                "contentUrl": "https://learn.microsoft.com/azure/machine-learning/concept-responsible-ai#tools",
                "content": "Another passage of the same page.",
            },
            {"title": "Elsewhere", "contentUrl": "https://example.com/page", "content": "Not Microsoft Learn."},
        ]
    }
    monkeypatch.setattr(mslearn._session, "call", lambda tool, args: json.dumps(rows))
    found = mslearn.search("responsible AI")
    assert [(r.title, r.url) for r in found] == [
        ("What is Responsible AI?", "https://learn.microsoft.com/azure/machine-learning/concept-responsible-ai")
    ]
    assert found[0].excerpt == "Responsible AI is an approach."


def test_with_a_key_the_search_includes_pluralsight_s_library(monkeypatch):
    monkeypatch.setenv("PLURALSIGHT_API_KEY", "ps-key")
    monkeypatch.setenv("PLURALSIGHT_SSO_ORG", "mufg")
    monkeypatch.setattr(mslearn, "search", lambda q, limit=8: [])
    send, calls = _graphql(
        {
            "HubSearch": {
                "courseCatalog": {
                    "nodes": [
                        {"id": "c-1", "slug": "responsible-ai-foundations", "title": "Responsible AI Foundations", "level": "Beginner", "shortDescription": "Start here", "courseSeconds": 5400.0}
                    ]
                }
            }
        }
    )
    monkeypatch.setattr(http, "send", send)
    by = {g["provider"]: g for g in client.get("/api/learning/providers/search", params={"q": "responsible AI"}).json()}
    assert by["Pluralsight"]["state"] == "live"
    assert by["Pluralsight"]["results"][0] == {
        "title": "Responsible AI Foundations",
        "url": "https://app.pluralsight.com/sso/mufg?returnUrl=library/courses/responsible-ai-foundations",
        "excerpt": "Start here",
        "level": "Beginner",
        "duration_seconds": 5400,
        "read_in_hub": False,
    }
    assert calls[0][2] == {"term": "responsible AI"}


def test_one_provider_failing_never_hides_the_other(monkeypatch):
    def down(q, limit=8):
        raise http.ExternalError("Microsoft Learn", 503, "Service Unavailable")

    monkeypatch.setattr(mslearn, "search", down)
    by = {g["provider"]: g for g in client.get("/api/learning/providers/search", params={"q": "copilot"}).json()}
    assert by["Microsoft Learn"]["state"] == "blocked" and "503" in by["Microsoft Learn"]["note"]
    assert by["Pluralsight"]["state"] == "sample"
    assert client.get("/api/learning/providers/search", params={"q": "x"}).status_code == 422


def test_microsoft_learn_items_open_and_read_in_the_hub():
    items = client.get("/api/learning/items", params={"source": "Microsoft Learn"}).json()
    assert len(items) == 8
    assert all(i["read_in_hub"] and i["launch_url"] == i["url"] and i["url"].startswith("https://learn.microsoft.com/") for i in items)


def test_without_a_key_pluralsight_courses_open_as_a_search():
    items = client.get("/api/learning/items", params={"source": "Pluralsight"}).json()
    assert items and all(not i["live"] and i["launch_url"].startswith("https://www.pluralsight.com/search?q=") for i in items)
    status = {i["id"]: i for i in client.get("/api/integrations").json()}
    assert status["pluralsight"]["state"] == "sample"
    assert {n["setting"] for n in status["pluralsight"]["needs"]} >= {"PLURALSIGHT_API_KEY", "PLURALSIGHT_SSO_ORG"}


def _graphql(answers):
    calls = []

    def send(service, method, url, **kwargs):
        body = kwargs.get("json_body") or {}
        calls.append((url, kwargs.get("headers", {}).get("Authorization"), body.get("variables")))
        name = next(n for n in answers if n in body.get("query", ""))
        return http.Response(200, json.dumps({"data": answers[name]}))

    return send, calls


def test_with_a_key_pluralsight_supplies_details_progress_and_a_single_sign_on_link(monkeypatch):
    monkeypatch.setenv("PLURALSIGHT_API_KEY", "ps-key")
    monkeypatch.setenv("PLURALSIGHT_SSO_ORG", "mufg")
    send, calls = _graphql(
        {
            "HubCourses": {
                "courseCatalog": {
                    "nodes": [
                        {
                            "id": "PS-c-9f21a",
                            "slug": "financial-statements-deep-dive",
                            "title": "Financial Statements: The Deep Dive",
                            "level": "Advanced",
                            "description": "Live description",
                            "courseSeconds": 9000.0,
                            "authors": ["A. Author"],
                            "url": "https://app.pluralsight.com/library/courses/financial-statements-deep-dive",
                        }
                    ]
                }
            },
            "HubLearner": {"users": {"nodes": [{"psUserId": "ps-77"}]}},
            "HubProgress": {"courseProgress": {"nodes": [{"courseId": "PS-c-9f21a", "percentComplete": 42.0, "isCourseCompleted": False}]}},
        }
    )
    monkeypatch.setattr(http, "send", send)
    item = next(i for i in client.get("/api/learning/items", params={"source": "Pluralsight"}).json() if i["provider_ref"] == "PS-c-9f21a")
    assert item["live"] and item["title"] == "Financial Statements: The Deep Dive"
    assert (item["level"], item["duration_seconds"], item["instructor"]) == ("Advanced", 9000, "A. Author")
    assert (item["status"], item["progress"]) == ("in_progress", 42)
    assert item["launch_url"] == "https://app.pluralsight.com/sso/mufg?returnUrl=library/courses/financial-statements-deep-dive"
    assert {auth for _, auth, _ in calls} == {"Bearer ps-key"}
    assert any(v and v.get("emails") == ["sai.vivek@mufg.example"] for _, _, v in calls)


def test_a_pluralsight_failure_keeps_the_catalogue_and_says_why(monkeypatch):
    monkeypatch.setenv("PLURALSIGHT_API_KEY", "ps-key")

    def refuse(service, method, url, **kwargs):
        raise http.ExternalError("Pluralsight", 401, "Unauthorized")

    monkeypatch.setattr(http, "send", refuse)
    items = client.get("/api/learning/items", params={"source": "Pluralsight"}).json()
    assert items and not any(i["live"] for i in items)
    status = {i["id"]: i for i in client.get("/api/integrations").json()}
    assert status["pluralsight"]["state"] == "blocked"
    assert status["pluralsight"]["blocking"] == "Pluralsight returned 401: Unauthorized"


def test_a_course_says_why_it_is_suggested_wherever_it_is_opened():
    """The side panel opens from shelves and searches, not only from the
    recommendations, so the reason comes with the course itself."""
    # u-1001 is a Compliance Analyst.
    def why(item_id):
        return client.get(f"/api/learning/items/{item_id}").json()["recommendation_reason"]

    assert why("model-risk-management-essentials") == "Mapped to your compliance user role."
    assert why("mslearn-draft-analyze-present") == "Part of the Business users path, one of your role's learning paths."
    assert why("how-to-build-a-kyc-agent") == "Covers kyc, which your role works with."
    # Nothing ties it to the role, so no reason is made up.
    assert why("apache-kafka-getting-started") == ""


def test_demo_accounts_start_part_way_through_a_pluralsight_course():
    assert client.post("/api/auth/demo", json={"user_id": "demo-compliance"}).status_code == 200
    item = client.get("/api/learning/items/model-risk-management-essentials").json()
    assert (item["source"], item["status"], item["progress"]) == ("Pluralsight", "in_progress", 42)
    # Seeding again never overwrites what the person has done since.
    client.post("/api/learning/progress", json={"item_id": "model-risk-management-essentials", "status": "completed"})
    from app import auth

    auth.seed_users()
    assert client.get("/api/learning/items/model-risk-management-essentials").json()["status"] == "completed"


def test_the_integrations_page_names_what_microsoft_sign_in_needs(monkeypatch):
    for name in ("ENTRA_TENANT_ID", "ENTRA_CLIENT_ID", "ENTRA_CLIENT_SECRET", "VIVA_ENGAGE_GRAPH_TOKEN", "VIVA_ENGAGE_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    status = {i["id"]: i for i in client.get("/api/integrations").json()}
    assert status["entra"]["state"] == "not_configured"
    assert {n["setting"] for n in status["entra"]["needs"] if n["setting"]} >= {"ENTRA_TENANT_ID", "ENTRA_CLIENT_ID", "ENTRA_CLIENT_SECRET"}
    assert status["viva_engage"]["state"] == "not_configured"
    assert any("Community.Read.All" in n["what"] for n in status["viva_engage"]["needs"])
    assert status["microsoft_learn"]["state"] == "live"
    assert client.get("/api/auth/options").json()["microsoft"] is False


# --------------------------------------------------------------- Microsoft sign-in

TENANT = "11111111-2222-3333-4444-555555555555"


@pytest.fixture
def entra_app(monkeypatch):
    monkeypatch.setenv("ENTRA_TENANT_ID", TENANT)
    monkeypatch.setenv("ENTRA_CLIENT_ID", "client-123")
    monkeypatch.setenv("ENTRA_CLIENT_SECRET", "secret-xyz")
    monkeypatch.delenv("ENTRA_REDIRECT_URI", raising=False)
    for name in ("VIVA_ENGAGE_GRAPH_TOKEN", "VIVA_ENGAGE_TOKEN"):
        monkeypatch.delenv(name, raising=False)


def _id_token(**claims) -> str:
    def part(data):
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    return f"{part({'alg': 'RS256'})}.{part(claims)}.signature"


def _start_sign_in():
    signed_out = TestClient(app)
    start = signed_out.get("/api/auth/microsoft/login", params={"next": "/community"}, follow_redirects=False)
    assert start.status_code == 302
    query = parse_qs(urlparse(start.headers["location"]).query)
    return signed_out, start, query


def test_sign_in_with_microsoft_starts_with_pkce(entra_app):
    _, start, query = _start_sign_in()
    location = start.headers["location"]
    assert location.startswith(f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/authorize?")
    assert query["code_challenge_method"] == ["S256"] and query["client_id"] == ["client-123"]
    assert "https://graph.microsoft.com/Community.Read.All" in query["scope"][0]
    assert query["redirect_uri"] == ["http://localhost:5175/api/auth/microsoft/callback"]
    assert "creditwiz_entra_state" in start.headers["set-cookie"]


def test_without_an_app_registration_sign_in_goes_to_the_integrations_page():
    response = TestClient(app).get("/api/auth/microsoft/login", follow_redirects=False)
    assert response.status_code == 302 and response.headers["location"] == "/integrations?entra=not_configured"


def _microsoft(state_nonce, engage_error=None):
    calls = []

    def send(service, method, url, **kwargs):
        calls.append((method, url, kwargs.get("form", {}).get("grant_type")))
        if url.endswith("/oauth2/v2.0/token"):
            form = kwargs["form"]
            if form["grant_type"] == "authorization_code":
                token = _id_token(aud="client-123", tid=TENANT, nonce=state_nonce, exp=time.time() + 600, oid="oid-42", name="Dana Cruz")
                return http.Response(200, json.dumps({"access_token": "graph-access", "refresh_token": "refresh-1", "expires_in": 3600, "id_token": token}))
            if engage_error:
                raise http.ExternalError("Microsoft Entra ID", 400, engage_error)
            return http.Response(200, json.dumps({"access_token": "engage-access", "expires_in": 3600}))
        if url.startswith("https://graph.microsoft.com/v1.0/me"):
            assert kwargs["headers"]["Authorization"] == "Bearer graph-access"
            return http.Response(
                200,
                json.dumps({"displayName": "Dana Cruz", "givenName": "Dana", "mail": "dana.cruz@mufg.example", "jobTitle": "Compliance Analyst", "department": "Compliance"}),
            )
        raise AssertionError(url)

    return send, calls


def test_the_microsoft_round_trip_signs_the_person_in_with_their_directory_profile(entra_app, monkeypatch):
    browser, _, query = _start_sign_in()
    state = query["state"][0]
    send, calls = _microsoft(entra._pending[state][1])
    monkeypatch.setattr(http, "send", send)
    done = browser.get("/api/auth/microsoft/callback", params={"code": "auth-code", "state": state}, follow_redirects=False)
    assert done.status_code == 302 and done.headers["location"] == "/community"

    me = browser.get("/api/me").json()
    assert (me["display_name"], me["job_title"], me["persona"]["id"]) == ("Dana Cruz", "Compliance Analyst", "compliance_user")
    assert entra.signed_in("entra-oid-42") and entra.token_for("entra-oid-42", "engage") == "engage-access"
    browser.headers["X-CreditWiz-Request"] = "1"
    status = {i["id"]: i for i in browser.get("/api/integrations").json()}
    assert status["entra"]["state"] == "live" and status["viva_engage"]["state"] == "live"
    assert ("POST", f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token", "refresh_token") in calls

    browser.post("/api/auth/logout")
    assert not entra.signed_in("entra-oid-42")


def test_a_missing_viva_engage_consent_is_named_on_the_integrations_page(entra_app, monkeypatch):
    browser, _, query = _start_sign_in()
    state = query["state"][0]
    consent = "AADSTS65001: The user or administrator has not consented to use the application"
    send, _ = _microsoft(entra._pending[state][1], engage_error=consent)
    monkeypatch.setattr(http, "send", send)
    browser.get("/api/auth/microsoft/callback", params={"code": "auth-code", "state": state}, follow_redirects=False)
    status = {i["id"]: i for i in browser.get("/api/integrations").json()}
    assert status["entra"]["state"] == "live"
    assert status["viva_engage"]["state"] == "blocked" and "AADSTS65001" in status["viva_engage"]["blocking"]


def test_a_callback_that_does_not_match_its_sign_in_is_refused(entra_app):
    browser, _, _ = _start_sign_in()
    done = browser.get("/api/auth/microsoft/callback", params={"code": "auth-code", "state": "forged"}, follow_redirects=False)
    assert done.headers["location"] == "/integrations?entra=failed"
    assert browser.get("/api/me").status_code == 401


def test_an_id_token_for_another_application_is_refused(entra_app):
    token = _id_token(aud="someone-else", tid=TENANT, nonce="n", exp=time.time() + 600, oid="x")
    with pytest.raises(ValueError, match="another application"):
        entra.claims(token, "n")
