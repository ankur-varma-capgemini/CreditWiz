"""Knowledge sources: what will feed Nexus, as the team listed it."""

import pytest
from fastapi.testclient import TestClient

from app.knowledge.models import KnowledgeSources
from app.knowledge.store import load
from app.main import app

client = TestClient(app)


def test_the_sources_listed_for_swim_lane_1_are_served():
    response = client.get("/api/knowledge/sources")
    assert response.status_code == 200
    body = response.json()
    assert [s["name"] for s in body["systems"]] == ["Confluence", "SharePoint", "JIRA", "ServiceNow", "Documents"]
    assert [d["abbreviation"] for d in body["document_types"]] == ["BRD", "ASD", "HLD", "LLD"]
    assert [g["name"] for g in body["link_groups"]] == ["Pitchbook links", "Library links"]


def test_nothing_the_team_has_not_confirmed_is_filled_in():
    sources = load()
    assert all(s.connection == "not_connected" and not s.owner and not s.location for s in sources.systems)
    assert all(not d.lives_in and not d.owner for d in sources.document_types)
    # The team named ASD without saying what it stands for.
    asd = next(d for d in sources.document_types if d.abbreviation == "ASD")
    assert asd.name == "" and asd.about == "" and asd.feeds == ""


def test_a_reference_to_an_unlisted_system_is_refused():
    raw = load().model_dump()
    raw["link_groups"][0]["systems"].append("teams")
    with pytest.raises(ValueError):
        KnowledgeSources.model_validate(raw)


def test_sign_in_is_required():
    anonymous = TestClient(app)
    assert anonymous.get("/api/knowledge/sources", headers={"X-CreditWiz-Request": "1"}).status_code == 401
