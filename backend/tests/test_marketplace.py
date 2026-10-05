import os

from fastapi.testclient import TestClient

os.environ["CREDITWIZ_DISABLE_LLM"] = "1"

from app.main import app
from app.marketplace import search
from app.marketplace.models import Agent
from app.marketplace.store import (
    normalize_agent,
    store,
)

client = TestClient(app)


def test_agents_load_and_validate():
    agents = store.agents
    assert len(agents) == 18  # 8 samples + the client's 10 first-pass KYC agents
    assert all(a.access.how for a in agents)
    # A confirmed owner is a condition of going to production, not of being
    # listed. The client's first-pass KYC agents are in_development with the
    # owner deliberately blank rather than invented.
    assert all(a.owner.email for a in agents if a.status == "production")
    assert any(a.status == "in_development" and not a.owner.email for a in agents)
    assert {a.id for a in agents} >= {
        "kyc-cip-agent",
        "contract-analyzer",
        "asset-locator",
    }


def test_home_builds_carousels_for_persona():
    body = client.get(
        "/api/marketplace/home", params={"persona": "compliance_user"}
    ).json()
    assert body["persona"] == "compliance_user"
    ids = [c["id"] for c in body["carousels"]]
    assert ids[0] == "recommended"
    recommended = [a["id"] for a in body["carousels"][0]["agents"]]
    assert recommended[0] in {
        "kyc-sanctions-review-agent",
        "kyc-cip-agent",
        "kyc-supervisor-agent",
        "kyc-adverse-media-agent",
        "fraud-case-summariser",
        "policy-qa-agent",
    }
    assert "code-review-assistant" not in recommended[:3]


def test_developer_persona_sees_code_review_first():
    body = client.get("/api/marketplace/home", params={"persona": "developer"}).json()
    recommended = [a["id"] for a in body["carousels"][0]["agents"]]
    assert recommended[0] == "code-review-assistant"


def test_nlp_search_understands_onboarding_documents():
    body = client.post(
        "/api/marketplace/search",
        json={
            "query": "I need an agent that can review customer onboarding documents",
            "persona": "compliance_user",
        },
    ).json()
    # Nothing interprets the query before retrieval, so "engine" names the
    # reranker. With no key configured, RRF's order stands.
    assert body["engine"] == "fusion"
    assert body["no_match"] is False
    top = [m["agent"]["id"] for m in body["results"]]
    assert top[0] in {"kyc-cip-agent", "onboarding-pack-assistant"}
    assert "Customer onboarding / KYC" in body["intent"]["concepts"]
    assert body["results"][0]["reasons"]


def test_nlp_search_paraphrase_without_keyword_overlap():
    body = client.post(
        "/api/marketplace/search",
        json={"query": "someone owes us money, where are their assets"},
    ).json()
    top = [m["agent"]["id"] for m in body["results"]]
    assert top[0] == "asset-locator"


def test_search_no_match_returns_next_steps():
    body = client.post(
        "/api/marketplace/search", json={"query": "zebra origami"}
    ).json()
    assert body["no_match"] is True
    assert body["results"] == []
    assert any(s["href"] == "/learning/catalog" for s in body["next_steps"])


def test_agent_detail_and_related():
    body = client.get("/api/marketplace/agents/contract-analyzer").json()
    assert body["owner"]["team"] == "Legal Technology"
    related = client.get("/api/marketplace/agents/contract-analyzer/related").json()
    assert related and related[0]["id"] != "contract-analyzer"
    assert client.get("/api/marketplace/agents/nope").status_code == 404


def test_shared_context_layer_is_hub_wide_not_pillar_owned(tmp_path):
    """Every pillar writes the same shapes to one store."""
    m = client.post(
        "/api/context/events",
        json={
            "pillar": "marketplace",
            "type": "view",
            "subject_id": "contract-analyzer",
            "subject_type": "agent",
            "topics": ["Legal"],
        },
    ).json()
    assert m["ok"] and m["id"]
    l = client.post(
        "/api/context/events",
        json={
            "pillar": "learning",
            "type": "learning_view",
            "subject_id": "how-to-build-a-kyc-agent",
            "subject_type": "video",
            "topics": ["kyc", "Legal"],
        },
    ).json()
    assert l["ok"]

    summary = client.get("/api/context/summary").json()
    assert summary["total_events"] == 2
    assert {p["pillar"] for p in summary["by_pillar"]} == {"marketplace", "learning"}

    # one shared file, not one per pillar
    assert (tmp_path / "hub.db").exists()
    assert not list(tmp_path.glob("*marketplace*"))


def test_interests_aggregate_across_pillars():
    client.post(
        "/api/context/events",
        json={"pillar": "learning", "type": "learning_view", "topics": ["kyc"]},
    )
    client.post(
        "/api/context/events",
        json={
            "pillar": "marketplace",
            "type": "search",
            "query": "kyc",
            "topics": ["kyc", "Compliance"],
        },
    )
    client.post(
        "/api/context/events",
        json={"pillar": "marketplace", "type": "launch", "topics": ["kyc"]},
    )
    interests = client.get("/api/context/interests").json()
    top = interests[0]
    assert top["topic"] == "kyc"
    assert top["weight"] == 1.0
    assert sorted(top["pillars"]) == ["learning", "marketplace"]


def test_user_context_joins_profile_persona_and_footprints():
    client.post(
        "/api/context/events",
        json={"pillar": "learning", "type": "learning_view", "topics": ["kyc"]},
    )
    ctx = client.get("/api/context/me").json()
    assert ctx["persona"] == "compliance_user"
    assert ctx["job_title"] == "Compliance Analyst"
    assert ctx["pillars_seen"] == ["learning"]
    assert ctx["interests"][0]["topic"] == "kyc"


def test_feedback_is_hub_wide(tmp_path):
    client.post(
        "/api/context/feedback",
        json={
            "pillar": "learning",
            "context": "video",
            "helpful": False,
            "subject_id": "v1",
            "missing": "Need a payroll video",
        },
    )
    client.post(
        "/api/context/feedback",
        json={"pillar": "marketplace", "context": "search", "helpful": True},
    )
    s = client.get("/api/context/summary").json()
    assert s["total_feedback"] == 2 and s["helpful"] == 1 and s["not_helpful"] == 1
    assert s["recent_missing"] == ["Need a payroll video"]
    assert (tmp_path / "hub.db").exists()


def test_deprecated_marketplace_endpoints_still_write_to_shared_store():
    client.post(
        "/api/marketplace/events",
        json={"type": "agent_view", "agent_id": "contract-analyzer"},
    )
    s = client.get("/api/context/summary").json()
    assert s["by_pillar"][0]["pillar"] == "marketplace"


def test_metadata_template_lists_required_fields():
    tpl = client.get("/api/marketplace/metadata-template").json()
    for field in (
        "id",
        "name",
        "business_domains",
        "use_cases",
        "capabilities",
        "personas",
        "owner",
        "status",
        "platform",
        "tools_services",
        "models",
        "access",
        "documentation_url",
        "architecture_url",
        "documents",
        "created_at",
        "updated_at",
    ):
        assert field in tpl


def test_local_intent_lexicon():
    intent = search.local_intent("screen a new customer against sanctions lists")
    assert "AML screening" in intent.concepts
    assert "Compliance" in intent.domains


SIMPLE_INTAKE_RECORD = {
    "agentId": "agent-001",
    "name": "KYC Verification Agent",
    "description": "Helps validate customer identity and KYC documents.",
    "domain": "Compliance",
    "useCases": ["Customer onboarding", "Identity verification"],
    "capabilities": [
        "Document validation",
        "Identity verification",
        "Compliance checks",
    ],
    "personas": ["Compliance User", "Business User"],
    "platform": "AWS",
    "owner": "KYC AI Team",
    "status": "Production",
    "tools": [],
    "models": [],
    "documentationUrl": "",
    "architectureUrl": "",
    "launchUrl": "",
    "createdDate": "",
    "updatedDate": "",
}


def test_simple_intake_format_normalises_to_canonical_model():
    agent = Agent.model_validate(normalize_agent(SIMPLE_INTAKE_RECORD))
    assert agent.id == "agent-001"
    assert agent.business_domains == ["Compliance"]
    assert agent.personas == ["compliance_user", "business_user"]
    assert agent.owner.team == "KYC AI Team"
    assert agent.status == "production"
    assert agent.category == "Compliance & Risk"
    assert agent.tagline.startswith("Helps validate")
    assert agent.use_cases == ["Customer onboarding", "Identity verification"]


def test_search_results_explain_why():
    body = client.post(
        "/api/marketplace/search",
        json={
            "query": "I need something for validating customer documents during onboarding"
        },
    ).json()
    top = body["results"][0]
    assert top["agent"]["id"] in {"kyc-cip-agent", "onboarding-pack-assistant"}
    assert top["why"].startswith("This agent")
    assert "onboarding" in top["why"].lower() or "document" in top["why"].lower()


def test_event_types_follow_agreed_names():
    for t in (
        "search",
        "agent_view",
        "agent_click",
        "agent_launch",
        "documentation_click",
        "request_access",
        "feedback_positive",
        "feedback_negative",
    ):
        assert (
            client.post("/api/marketplace/events", json={"type": t}).status_code == 200
        )
    assert (
        client.post("/api/marketplace/events", json={"type": "view_agent"}).status_code
        == 422
    )


def test_documents_are_links_to_where_they_live_not_copies():
    # The hub serves no documentation or architecture pages of its own.
    assert client.get("/api/marketplace/agents/contract-analyzer/docs").status_code == 404
    assert client.get("/api/marketplace/agents/contract-analyzer/architecture").status_code == 404
    agent = client.get("/api/marketplace/agents/contract-analyzer").json()
    # No link has been given yet, and none is invented.
    assert agent["documents"] == []


def test_every_agent_is_open_and_names_only_listed_document_types_and_systems():
    from app.knowledge.store import load

    sources = load()
    types = {d.id for d in sources.document_types}
    systems = {s.id for s in sources.systems}
    for agent in store.all_agents:
        assert agent.access.type == "open", agent.id
        for doc in agent.documents:
            assert doc.type in types and (not doc.system or doc.system in systems), agent.id


def test_an_agent_document_is_a_safe_link():
    import pytest

    base = store.all_agents[0].model_dump()
    agent = Agent.model_validate(
        {
            **base,
            "documents": [
                {
                    "type": "hld",
                    "system": "confluence",
                    "url": "https://confluence.example/hld",
                    "description": "Components, integrations and data flows of the agent.",
                }
            ],
        }
    )
    assert agent.documents[0].system == "confluence"
    assert agent.documents[0].description.startswith("Components")
    with pytest.raises(ValueError):
        Agent.model_validate({**base, "documents": [{"type": "hld", "url": "javascript:alert(1)"}]})


def test_learning_for_agent_is_persona_ordered():
    recs = client.get(
        "/api/learning/for-agent/kyc-cip-agent",
        params={"persona": "compliance_user"},
    ).json()
    ids = [i["id"] for i in recs]
    assert "kyc-verifier-walkthrough" in ids and len(ids) <= 3
    # Both items explicitly link to the CIP Agent; either is the right lead
    # for a compliance user, and both sit ahead of anything only tag-related.
    assert recs[0]["id"] in {"kyc-verifier-walkthrough", "kyc-document-checklist"}
    dev = [
        i["id"]
        for i in client.get(
            "/api/learning/for-agent/kyc-cip-agent",
            params={"persona": "developer"},
        ).json()
    ]
    assert dev[0] == "how-to-build-a-kyc-agent"  # builder content first for a developer


def test_learning_items_span_many_content_types():
    items = client.get("/api/learning/items").json()
    types = {i["type"] for i in items}
    assert {
        "video",
        "quick-reference",
        "best-practice",
        "documentation",
        "guide",
        "course",
        "confluence",
    } <= types
    assert len(items) >= 20
    assert client.get("/api/learning/items", params={"type": "quick-reference"}).json()
    assert client.get("/api/learning/items/nope").status_code == 404
    detail = client.get("/api/learning/items/kyc-verifier-walkthrough").json()
    assert (
        detail["path_title"]
        and "kyc-cip-agent" in detail["related_agent_names"]
    )


def test_learning_home_sections_are_role_based():
    body = client.get("/api/learning", params={"persona": "compliance_user"}).json()
    ids = [s["id"] for s in body["sections"]]
    assert ids[0] == "required"  # mandatory first
    assert {"role", "best-practice", "docs", "quick-reference"} <= set(ids)
    assert all(i["required"] for i in body["sections"][0]["items"])
    assert body["persona_label"] == "Compliance user"


def test_progress_tracks_started_and_completed():
    started = client.post(
        "/api/learning/progress",
        json={
            "item_id": "kyc-document-checklist",
            "status": "in_progress",
            "progress": 40,
        },
    ).json()
    assert started["status"] == "in_progress" and started["progress"] == 40

    again = client.post(
        "/api/learning/progress",
        json={
            "item_id": "kyc-document-checklist",
            "status": "in_progress",
            "progress": 10,
        },
    ).json()
    assert again["progress"] == 40  # progress never regresses

    done = client.post(
        "/api/learning/progress",
        json={"item_id": "kyc-document-checklist", "status": "completed"},
    ).json()
    assert done["status"] == "completed" and done["progress"] == 100

    summary = client.get(
        "/api/context/summary"
    ).json()  # completion is also a hub footprint
    assert any(
        p["pillar"] == "learning" and p["types"].get("learning_complete")
        for p in summary["by_pillar"]
    )
    assert (
        client.post(
            "/api/learning/progress", json={"item_id": "nope", "status": "completed"}
        ).status_code
        == 404
    )


def test_my_learning_reports_progress_and_coverage_not_proficiency():
    client.post(
        "/api/learning/progress",
        json={"item_id": "kyc-verifier-walkthrough", "status": "completed"},
    )
    client.post(
        "/api/learning/progress",
        json={
            "item_id": "sanctions-screening-basics",
            "status": "in_progress",
            "progress": 65,
        },
    )
    me = client.get("/api/learning/my-learning").json()
    assert me["completed"] >= 1 and me["in_progress"] >= 1
    assert me["required_total"] >= me["required_completed"]

    kyc = next(c for c in me["coverage"] if c["topic"] == "KYC")
    assert kyc["completed"] <= kyc["total"]  # factual counts, never a percentage

    # The note must say proficiency is not measured until a measure is agreed.
    # Checked by meaning, not wording, so the sentence can be edited as copy.
    note = me["proficiency_note"].lower()
    assert "proficiency" in note and "agreed" in note
    assert not any("proficiency" in k.lower() and k != "proficiency_note" for k in me)


def test_rating_requires_the_learner_to_have_opened_the_item():
    """A rating from someone who never opened the content is not a signal."""
    assert (
        client.post(
            "/api/learning/ratings",
            json={"item_id": "kyc-verifier-walkthrough", "stars": 5},
        ).status_code
        == 409
    )
    client.post(
        "/api/learning/progress",
        json={"item_id": "kyc-verifier-walkthrough", "status": "in_progress"},
    )
    body = client.post(
        "/api/learning/ratings",
        json={"item_id": "kyc-verifier-walkthrough", "stars": 5},
    ).json()
    assert body["my_rating"] == 5 and body["rating_count"] == 1


def test_average_is_withheld_until_enough_ratings_but_weighted_value_exists():
    """One 5-star vote must not be published as "5.0"."""
    from app.learning import ratings

    client.post(
        "/api/learning/progress",
        json={"item_id": "kyc-verifier-walkthrough", "status": "in_progress"},
    )
    body = client.post(
        "/api/learning/ratings",
        json={"item_id": "kyc-verifier-walkthrough", "stars": 5},
    ).json()
    assert body["rating_count"] == 1 < ratings.MIN_SHOWN
    assert body["rating_average"] is None
    # Shrinkage pulls a lone 5 back toward the catalogue, so it cannot win a sort.
    assert body["rating_weighted"] < 5.0


def test_rating_again_replaces_rather_than_accumulates():
    client.post(
        "/api/learning/progress",
        json={"item_id": "kyc-verifier-walkthrough", "status": "in_progress"},
    )
    for stars in (2, 4):
        body = client.post(
            "/api/learning/ratings",
            json={"item_id": "kyc-verifier-walkthrough", "stars": stars},
        ).json()
    assert body["my_rating"] == 4 and body["rating_count"] == 1

    cleared = client.post(
        "/api/learning/ratings",
        json={"item_id": "kyc-verifier-walkthrough", "stars": None},
    ).json()
    assert cleared["my_rating"] is None and cleared["rating_count"] == 0


def test_average_appears_once_the_item_clears_the_threshold():
    """Three learners, three different scores: the mean becomes publishable."""
    from app.learning import ratings

    item = "kyc-verifier-walkthrough"
    for user, stars in (("u-1001", 5), ("demo-compliance", 4), ("demo-operations", 3)):
        assert client.post("/api/auth/demo", json={"user_id": user}).status_code == 200
        client.post("/api/learning/progress", json={"item_id": item, "status": "in_progress"})
        body = client.post(
            "/api/learning/ratings", json={"item_id": item, "stars": stars}
        ).json()

    assert body["rating_count"] == ratings.MIN_SHOWN == 3
    assert body["rating_average"] == 4.0
    # Each learner still sees only their own vote reflected back.
    assert body["my_rating"] == 3


def test_ratings_are_collected_but_never_ranked_on():
    """The chosen stance: collect now, rank later. Curation stays explainable."""
    client.post(
        "/api/learning/progress",
        json={"item_id": "kyc-verifier-walkthrough", "status": "in_progress"},
    )
    before = client.get("/api/learning/curation").json()
    client.post(
        "/api/learning/ratings",
        json={"item_id": "kyc-verifier-walkthrough", "stars": 1},
    )
    after = client.get("/api/learning/curation").json()
    assert before["ranked"] == after["ranked"]
    assert not any("rating" in k for r in after["ranked"] for k in r["components"])

    # It is collected, though: the rating lands in the shared footprint stream
    # that a future ranker reads.
    learning = next(
        p
        for p in client.get("/api/context/summary").json()["by_pillar"]
        if p["pillar"] == "learning"
    )
    assert learning["types"].get("rating") == 1


def test_progress_is_sqlite_and_survives_reads(tmp_path):
    """Progress is mutable state, so it lives in SQLite rather than a rewritten JSON file."""
    import sqlite3

    client.post(
        "/api/learning/progress",
        json={
            "item_id": "prompt-patterns-one-pager",
            "status": "in_progress",
            "progress": 30,
        },
    )
    db = tmp_path / "hub.db"
    assert db.exists()

    rows = (
        sqlite3.connect(db)
        .execute("SELECT user_id, item_id, status, progress FROM learning_progress")
        .fetchall()
    )
    assert ("u-1001", "prompt-patterns-one-pager", "in_progress", 30) in rows

    # concurrent-safe upsert: same row, not a duplicate
    client.post(
        "/api/learning/progress",
        json={"item_id": "prompt-patterns-one-pager", "status": "completed"},
    )
    # Demo accounts carry rows of their own, so count this person's.
    rows = (
        sqlite3.connect(db)
        .execute("SELECT status, progress FROM learning_progress WHERE user_id='u-1001'")
        .fetchall()
    )
    assert len(rows) == 1 and rows[0] == ("completed", 100)


def _agent(**overrides):
    from app.marketplace.models import Agent
    from app.marketplace.store import normalize_agent, store

    base = store.agents[0].model_dump()
    base.update(overrides)
    return Agent.model_validate(normalize_agent(base))


def _compliance():
    from app.marketplace.store import store

    return store.persona("compliance_user")


def test_an_agent_that_names_no_persona_still_ranks_on_its_metadata():
    """Owners describe what an agent does; they should not have to enumerate
    every role that might want it. Curation is derived from that description."""
    from app.marketplace import search

    untagged = _agent(
        id="untagged-screening",
        personas=[],
        business_domains=["Compliance", "Onboarding"],
        capabilities=["Sanctions screening", "Risk scoring"],
        tags=["kyc", "aml"],
    )
    score = search.curation_score(untagged, _compliance())
    assert score > 10, f"metadata-only agent scored {score}"
    assert search.curation_breakdown(untagged, _compliance())["persona_boost"] == 0.0


def test_naming_a_persona_cannot_manufacture_relevance():
    """The boost is a percentage of matched metadata, so 25% of nothing is
    nothing. A mistaken persona tag cannot promote an unrelated agent."""
    from app.marketplace import search

    unrelated = _agent(
        id="unrelated-but-tagged",
        personas=["compliance_user"],
        business_domains=["Engineering"],
        capabilities=["Code review"],
        use_cases=["Review a pull request for style issues"],
        tags=["python"],
        popularity=0,
    )
    parts = search.curation_breakdown(unrelated, _compliance())
    assert parts["persona_boost"] == 0.0
    assert search.curation_score(unrelated, _compliance()) == 0.0


def test_evidence_outranks_a_curator_hint():
    """Real overlap must beat a persona tag sitting on a thin agent -- the
    failure the previous flat +10 produced."""
    from app.marketplace import search

    persona = _compliance()
    thin_but_tagged = _agent(
        id="thin-tagged", personas=["compliance_user"],
        business_domains=["Compliance"], capabilities=[], tags=[], popularity=99,
    )
    rich_untagged = _agent(
        id="rich-untagged", personas=[],
        business_domains=["Compliance", "Onboarding"],
        capabilities=["Sanctions screening"], tags=["kyc"], popularity=0,
    )
    assert search.curation_score(rich_untagged, persona) > search.curation_score(
        thin_but_tagged, persona
    )


def test_capability_matching_tolerates_wording_differences():
    """Two catalogues will not phrase things identically."""
    from app.marketplace import search

    reworded = _agent(
        id="reworded", personas=[], business_domains=[],
        capabilities=["Sanctions list screening"], tags=[], popularity=0,
    )
    assert search.curation_breakdown(reworded, _compliance())["capability"] == 2.0

    unrelated = _agent(
        id="different-customer-thing", personas=[], business_domains=[],
        capabilities=["Customer communication"], tags=[], popularity=0,
    )
    assert search.curation_breakdown(unrelated, _compliance())["capability"] == 0.0


def test_use_cases_count_toward_relevance():
    """An owner's description of what the agent is for is evidence, even when
    the capability list is thin."""
    from app.marketplace import search

    described = _agent(
        id="described-only", personas=[], business_domains=[], capabilities=[], tags=[],
        use_cases=["Screen a customer against sanctions lists"], popularity=0,
    )
    # Covers two interests: the capability "Sanctions screening" and the tag.
    assert search.curation_breakdown(described, _compliance())["use_case"] == 4.0


def test_a_wordy_listing_cannot_outscore_a_precise_one():
    """Coverage is counted per persona interest, not per sentence, so writing
    four use cases about the same thing scores once."""
    from app.marketplace import search

    repetitive = _agent(
        id="repetitive", personas=[], business_domains=[], capabilities=[], tags=[],
        use_cases=[
            "Ask what the policy says",
            "Find the policy section that applies",
            "Look up a policy exception",
            "Explain a policy in plain language",
        ],
        popularity=0,
    )
    broad = _agent(
        id="broad", personas=[], business_domains=[], capabilities=[], tags=[],
        use_cases=["Check a policy", "Screen for sanctions"], popularity=0,  # 3 interests
    )
    parts = search.curation_breakdown(repetitive, _compliance())
    assert parts["use_case"] == 2.0, "one interest, however many sentences"
    assert search.curation_breakdown(broad, _compliance())["use_case"] == 6.0


def test_search_intent_outranks_persona():
    """The two modes are different questions. 'Who are you' drives the
    carousels; 'what do you need right now' must drive search -- a compliance
    user asking about Python gets the code agent, not KYC."""
    results = client.post(
        "/api/marketplace/search",
        json={"query": "I need something to review Python code"},
    ).json()["results"]
    assert results, "expected at least one match"
    assert results[0]["agent"]["id"] == "code-review-assistant"


def test_embedding_text_carries_the_searchable_metadata():
    """Governance fields stay out: the index describes what an agent does, and
    owner, access and URLs are read from agents.json, never from Chroma."""
    from app.marketplace import semantic
    from app.marketplace.store import store

    agent = next(a for a in store.all_agents if a.id == "kyc-sanctions-review-agent")
    text = semantic.embedding_text(agent)
    assert agent.name in text
    assert "Sanctions screening" in text and "Compliance" in text
    assert agent.owner.team not in text and "mufg.example" not in text
    assert "http" not in text


def test_agents_are_embedded_once_and_only_re_embedded_when_changed(tmp_path, monkeypatch):
    """Embedding is the expensive step, so a restart must not repeat it."""
    from app.marketplace import semantic
    from app.marketplace.store import store

    # A private directory: the session fixture already populated the shared
    # one, and this test counts what a first sync adds.
    monkeypatch.setenv("CREDITWIZ_INDEX_DIR", str(tmp_path / "chroma"))
    index = semantic.SemanticIndex()
    agents = store.all_agents
    first = index.sync(agents)
    if not index.available:
        import pytest

        pytest.skip("semantic index unavailable in this environment")
    assert first["added"] == len(agents)

    again = index.sync(agents)
    assert again["unchanged"] == len(agents)
    assert again["added"] == 0 and again["updated"] == 0

    edited = agents[0].model_copy(update={"tagline": "A completely new tagline"})
    third = index.sync([edited, *agents[1:]])
    assert third["updated"] == 1 and third["unchanged"] == len(agents) - 1

    dropped = index.sync(agents[1:])
    assert dropped["removed"] == 1


def test_semantic_retrieval_finds_an_agent_that_shares_no_words():
    """The gap lexical matching cannot close: the KYC agent says "sanctions and
    PEP lists" and never uses the words in this query."""
    from app.marketplace import semantic
    from app.marketplace.store import store

    index = semantic.SemanticIndex()
    index.sync(store.all_agents)
    if not index.available:
        import pytest

        pytest.skip("semantic index unavailable in this environment")
    hits = index.search("anti-money-laundering watchlist checks", limit=3)
    assert hits, "expected candidates"
    # Either sanctions agent proves the point; the client's Sanctions Review
    # Agent now outranks the sample that stood in for it.
    assert max(hits, key=hits.get) == "kyc-sanctions-review-agent"


def test_search_still_works_when_the_semantic_index_is_disabled(monkeypatch):
    """A failed or switched-off index must degrade to lexical, never 500."""
    monkeypatch.setenv("CREDITWIZ_DISABLE_SEMANTIC", "1")
    from app.marketplace import semantic

    assert semantic.SemanticIndex().search("sanctions screening") == {}
    results = client.post(
        "/api/marketplace/search", json={"query": "validating customer documents"}
    ).json()["results"]
    assert results and results[0]["agent"]["id"] in {
        "kyc-cip-agent",
        "onboarding-pack-assistant",
    }


def test_search_records_a_trace_that_explains_the_ranking():
    """Afterwards it must be possible to tell whether an agent was missed
    because retrieval never proposed it or because the ranker dropped it."""
    client.post(
        "/api/marketplace/search",
        json={"query": "anti-money-laundering watchlist checks"},
    )
    trace = client.get(
        "/api/context/events?pillar=marketplace&type=search&limit=1"
    ).json()[0]
    assert trace["query"] == "anti-money-laundering watchlist checks"
    assert trace["persona"] == "compliance_user"

    meta = trace["meta"]
    assert meta["engine"] in {"claude", "fusion"}
    assert meta["results"] and set(meta["scores"]) == set(meta["results"])
    assert "domains" in meta["intent"] and "capabilities" in meta["intent"]
    assert "available" in meta["retrieval"] and "candidates" in meta["retrieval"]
    assert meta["no_match"] is False
    assert isinstance(meta["took_ms"], int)


def test_the_footprint_trail_is_scoped_to_the_signed_in_user():
    client.post("/api/marketplace/search", json={"query": "sanctions screening"})
    assert client.get("/api/context/events").json(), "own trail is readable"

    # Switching the session swaps the cookie, so this reads the other user's trail.
    assert (
        client.post("/api/auth/demo", json={"user_id": "demo-developer"}).status_code
        == 200
    )
    theirs = [
        e.get("query") for e in client.get("/api/context/events?type=search").json()
    ]
    assert "sanctions screening" not in theirs


def test_a_search_embeds_the_query_exactly_once(monkeypatch):
    """Embedding is the slow step. The router used to embed once for the trace
    and rank() embedded again -- two model calls per search.

    A search whose understood domains exclude everything is retried without
    them and does embed twice, by design. This query is not one of those.
    """
    from app.marketplace import semantic

    calls = {"n": 0}
    real = semantic.index.search

    def counted(query, limit=semantic.DEFAULT_CANDIDATES, groups=None, domains=None):
        calls["n"] += 1
        return real(query, limit, groups, domains)

    monkeypatch.setattr(semantic.index, "search", counted)
    body = client.post(
        "/api/marketplace/search", json={"query": "check customers against sanctions lists"}
    ).json()
    assert body["results"], "expected a match"
    assert calls["n"] == 1, f"query embedded {calls['n']} times"


def test_keyword_index_pins_an_exact_name():
    """BM25's job in the hybrid: exact tokens -- names, acronyms, IDs."""
    from app.marketplace import keyword
    from app.marketplace.store import store

    keyword.index.sync(store.all_agents)
    hits = keyword.index.search("Sanctions Review Agent")
    assert max(hits, key=hits.get) == "kyc-sanctions-review-agent"
    assert keyword.index.search("zebra origami") == {}


def test_rrf_fuses_by_rank_and_ignores_score_scale():
    """A cosine in 0..1 and a BM25 in 0..10 must fuse as ranks, not magnitudes."""
    from app.marketplace.search import rrf

    semantic_ranks = {"a": 0.9, "b": 0.8, "c": 0.1}
    keyword_ranks = {"b": 900.0, "a": 850.0}  # wildly different scale
    fused = rrf(semantic_ranks, keyword_ranks)
    # a and b are each first in one ranker and second in the other: a tie.
    assert abs(fused["a"] - fused["b"]) < 1e-9
    # c appears in one ranker only, last: it must trail both.
    assert fused["c"] < fused["a"]


def test_hybrid_search_still_returns_no_match_for_nonsense():
    """RRF always returns something; the relevance gate must not."""
    body = client.post("/api/marketplace/search", json={"query": "zebra origami"}).json()
    assert body["no_match"] is True and body["results"] == []


def test_search_trace_records_both_rankers():
    client.post("/api/marketplace/search", json={"query": "sanctions review"})
    meta = client.get("/api/context/events?type=search&limit=1").json()[0]["meta"]
    assert meta["fusion"] == "rrf"
    assert "candidates" in meta["keyword"] and "candidates" in meta["retrieval"]
    assert meta["results"][0] == "kyc-sanctions-review-agent"


def test_retrieval_is_filtered_by_audience_not_after_it():
    """Permission narrows the candidates inside the query, not afterwards.

    Post-filtering silently costs recall: an agent the user cannot see occupies
    one of the six candidate slots, so a permitted agent falls off the end. The
    fix only holds if the filter really reaches the index, which is what this
    asserts -- an audience that matches nothing must come back empty rather
    than come back full and be trimmed later.
    """
    from app.marketplace import keyword, semantic

    query = "sanctions screening"
    assert semantic.index.available, "index must be built for this to mean anything"

    permitted = semantic.index.search(query, groups=["AI-Hub-Users"])
    assert permitted, "the demo audience should retrieve something"

    assert semantic.index.search(query, groups=["Group-That-Owns-Nothing"]) == {}
    assert semantic.index.search(query, groups=[]) == {}

    # Passing no audience at all still searches the whole catalogue, which is
    # what the sync path and the tests rely on.
    assert semantic.index.search(query) != {}


def test_filter_shape_matches_what_chroma_accepts():
    """`$or` needs two clauses or more; a single value must be a bare clause.

    Chroma matches into a list-valued field with `$contains` only -- `$in` and
    `$eq` return nothing without erroring, so a wrong shape here looks like
    "no results" rather than a failure.
    """
    from app.marketplace.semantic import _any_of, _where

    assert _any_of("groups", []) is None
    assert _any_of("groups", ["one"]) == {"groups": {"$contains": "one"}}
    assert _any_of("groups", ["b", "a"]) == {
        "$or": [{"groups": {"$contains": "a"}}, {"groups": {"$contains": "b"}}]
    }

    # Audience and domain conditions combine with $and; either alone stays bare.
    assert _where(["g"], None) == {"groups": {"$contains": "g"}}
    assert _where(None, ["Compliance"]) == {"domains": {"$contains": "Compliance"}}
    assert _where(["g"], ["Compliance"]) == {
        "$and": [{"groups": {"$contains": "g"}}, {"domains": {"$contains": "Compliance"}}]
    }


def test_keyword_search_honours_the_allow_list():
    from app.marketplace import keyword

    everything = keyword.index.search("sanctions screening")
    assert everything
    one = next(iter(everything))
    assert set(keyword.index.search("sanctions screening", allowed={one})) == {one}
    assert keyword.index.search("sanctions screening", allowed=set()) == {}


def test_nothing_is_added_to_the_query_before_it_is_searched():
    """Retrieval sees the query and nothing else.

    An earlier pipeline expanded the query with a model's restatement and its
    guess at domains and capabilities before embedding. That let a request with
    no lexical overlap be rescued by our own expansion -- "zebra origami" once
    returned the Code Review Assistant, because the extraction supplied a
    capability and that capability was the best keyword score in the set.
    Searching what was typed removes the failure mode rather than guarding it.
    """
    from app.marketplace import search

    q = "  chase the client for missing paperwork  "
    assert search.retrieval_text(q) == q.strip()
    assert search.keyword_text(q) == q.strip()

    body = client.post("/api/marketplace/search", json={"query": "zebra origami"}).json()
    assert body["no_match"] is True and body["results"] == []
