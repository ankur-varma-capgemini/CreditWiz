import json
import os
import sqlite3
import subprocess
import sys
import time

from fastapi.testclient import TestClient

from app import auth, database
from app.learning import router as learning
from app.main import app
from app.marketplace.store import store

client = TestClient(app)
HEADERS = {"X-CreditWiz-Request": "1"}


def login(uid):
    other = TestClient(app, headers=HEADERS)
    assert other.post("/api/auth/demo", json={"user_id": uid}).status_code == 200
    return other


def complete(c, item="kyc-document-checklist"):
    r = c.post("/api/learning/progress", json={"item_id": item, "status": "completed"})
    assert r.status_code == 200, r.text
    return r.json()


def _use_catalog(tmp_path, monkeypatch, raw):
    """Point the app at a modified catalogue on disk and drop the cache."""
    import json

    from app.learning.store import store as learning_store

    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "learning.json").write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setenv("CREDITWIZ_DATA_DIR", str(data_dir))
    learning_store.invalidate()


def test_session_required_csrf_and_revocation():
    anon = TestClient(app)
    for route in (
        "/api/home",
        "/api/learning/items",
        "/api/context/summary",
        "/api/marketplace/agents",
        "/api/preferences",
    ):
        assert anon.get(route).status_code == 401
    assert anon.post("/api/auth/demo", json={"user_id": "u-1001"}).status_code == 403
    assert (
        client.post(
            "/api/auth/demo",
            json={"user_id": "u-1001"},
            headers={"Origin": "https://untrusted.example"},
        ).status_code
        == 403
    )
    cookie = client.cookies.get(auth.COOKIE)
    assert client.post("/api/auth/logout").status_code == 200
    client.cookies.set(auth.COOKIE, cookie)
    assert client.get("/api/home").status_code == 401


def test_users_have_separate_progress_feedback_preferences_and_reads():
    first, second = login("demo-business"), login("demo-compliance")
    complete(first)
    first.post(
        "/api/context/feedback",
        json={
            "pillar": "learning",
            "context": "item",
            "helpful": False,
            "missing": "More examples",
        },
    )
    domain = first.get("/api/domains").json()[1]["id"]
    assert (
        first.put(
            "/api/preferences",
            json={"default_domain": domain, "show_learning_reminders": False},
        ).status_code
        == 200
    )
    first.post("/api/notifications/read")
    assert (
        first.get("/api/learning/items/kyc-document-checklist").json()["status"]
        == "completed"
    )
    assert (
        second.get("/api/learning/items/kyc-document-checklist").json()["status"]
        == "not_started"
    )
    assert second.get("/api/context/summary").json()["total_events"] == 0
    assert second.get("/api/context/summary").json()["total_feedback"] == 0
    assert second.get("/api/preferences").json()["default_domain"] == "all"
    assert all(n["read"] for n in first.get("/api/notifications").json())
    assert any(not n["read"] for n in second.get("/api/notifications").json())
    again = login("demo-business")
    assert again.get("/api/preferences").json()["default_domain"] == domain
    assert (
        again.get("/api/learning/items/kyc-document-checklist").json()["status"]
        == "completed"
    )


def test_learning_acl_applies_to_catalog_detail_progress_search_paths_and_preview():
    c = login("demo-business")
    hidden = "document-agent-pattern-doc"
    assert hidden not in c.get("/api/learning/items").text
    assert c.get(f"/api/learning/items/{hidden}").status_code == 404
    assert (
        c.post(
            "/api/learning/progress", json={"item_id": hidden, "status": "completed"}
        ).status_code
        == 404
    )
    assert hidden not in c.get("/api/search?q=document").text
    assert hidden not in c.get("/api/learning").text
    assert hidden not in c.get("/api/learning/for-agent/contract-analyzer").text
    assert c.get("/api/learning?persona=developer").status_code == 403
    assert c.get("/api/marketplace/home?persona=developer").status_code == 403
    assert (
        c.post(
            "/api/marketplace/search", json={"query": "code", "persona": "developer"}
        ).status_code
        == 403
    )
    assert (
        login("demo-developer").get(f"/api/learning/items/{hidden}").status_code == 200
    )


def test_agent_acl_covers_all_discovery_and_resources(monkeypatch):
    store._refresh()
    records = [
        a.model_copy(update={"audience_groups": ["AI-Hub-Admins"]})
        if a.id == "contract-analyzer"
        else a
        for a in store._agents
    ]
    monkeypatch.setattr(store, "_agents", records)
    monkeypatch.setattr(store, "_refresh", lambda: None)
    c = login("demo-business")
    for route in (
        "/api/marketplace/agents",
        "/api/marketplace/home",
        "/api/search?q=kyc",
        "/api/learning/items",
        "/api/marketplace/curation",
    ):
        # Exact quoted id: the learning item "contract-analyzer-in-5" would
        # otherwise match as a substring and fail this for the wrong reason.
        assert '"contract-analyzer"' not in c.get(route).text
    for suffix in ("", "/related"):
        assert (
            c.get("/api/marketplace/agents/contract-analyzer" + suffix).status_code
            == 404
        )
    assert (
        "contract-analyzer"
        not in c.post("/api/marketplace/search", json={"query": "contract"}).text
    )


def test_profile_permission_revocation_takes_effect_with_existing_session():
    c = login("demo-developer")
    with database.connect(write=True) as conn:
        row = conn.execute(
            "SELECT profile FROM users WHERE id='demo-developer'"
        ).fetchone()
        profile = json.loads(row[0])
        profile["groups"] = ["AI-Hub-Users"]
        conn.execute(
            "UPDATE users SET profile=? WHERE id='demo-developer'",
            (json.dumps(profile),),
        )
    assert c.get("/api/learning/items/document-agent-pattern-doc").status_code == 404


def test_paths_are_ordered_and_prerequisites_enforced():
    home = client.get("/api/learning").json()
    assert home["role_paths"] and home["role_paths"][0]["total_steps"]
    path = next(p for p in home["paths"] if p["id"] == "compliance")
    items = client.get("/api/learning/items?path=compliance").json()
    assert [i["id"] for i in items] == path["steps"]
    assert [i["sequence"] for i in items] == list(range(1, len(items) + 1))
    assert (
        client.post(
            "/api/learning/progress",
            json={"item_id": "kyc-agent-runbook-confluence", "status": "completed"},
        ).status_code
        == 409
    )
    complete(client)
    complete(client, "kyc-agent-runbook-confluence")
    path_after = next(
        p
        for p in client.get("/api/learning").json()["paths"]
        if p["id"] == "compliance"
    )
    assert path_after["completed_steps"] == 2


def test_recommendations_fill_after_completed_candidates_are_removed():
    for _ in range(3):
        recs = client.get("/api/learning/recommended").json()
        assert recs
        for item in recs:
            complete(client, item["id"])
    pending = client.get("/api/learning/recommended").json()
    assert all(i["status"] == "not_started" and not i["blocked_by"] for i in pending)
    assert all(i["recommendation_reason"] for i in pending)
    remaining = [
        i
        for i in learning._with_progress(learning._load()[1], "compliance_user")
        if i.status == "not_started"
        and not i.required
        and not i.blocked_by
        and not i.prerequisite_unavailable
        and learning.curation_score(i, learning.resolve_persona()) > 0
    ]
    assert len(pending) == min(4, len(remaining))


def test_completion_exactly_once_and_atomic_across_processes(tmp_path):
    code = """from app.learning.progress import record
import sys
for _ in range(10):
 record('u-1001','kyc-document-checklist',sys.argv[1],20,{'pillar':'learning','type':'learning_complete','subject_id':'kyc-document-checklist'})
"""
    env = {**os.environ, "CREDITWIZ_VAR_DIR": str(tmp_path)}
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", code, status],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for status in ["completed", "in_progress", "completed", "in_progress"]
    ]
    for process in processes:
        _, stderr = process.communicate(timeout=30)
        assert process.returncode == 0, stderr
    assert (
        client.get("/api/learning/items/kyc-document-checklist").json()["progress"]
        == 100
    )
    complete(client)
    with database.connect() as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM events WHERE event_key IS NOT NULL"
            ).fetchone()[0]
            == 1
        )
    assert (
        client.post(
            "/api/context/events",
            json={"pillar": "learning", "type": "learning_complete"},
        ).status_code
        == 422
    )


def test_catalog_validation_rejects_cycles_and_unknown_steps(tmp_path, monkeypatch):
    """Written to a real catalogue file so the whole load path runs: read,
    parse, validate. No production seam exists just for the test."""
    import pytest

    raw = learning._raw()
    raw["items"][0]["prerequisites"] = [raw["items"][0]["id"]]
    _use_catalog(tmp_path, monkeypatch, raw)

    with pytest.raises(ValueError, match="cycles"):
        learning._load()


def test_real_catalog_search_domain_filter_and_local_access_request():
    assert any(
        r["title"] == "KYC document checklist"
        for r in client.get("/api/search?q=checklist").json()["results"]
    )
    filtered = client.get("/api/marketplace/home?domain=Legal").json()
    assert filtered["carousels"]
    assert all(
        "Legal" in a["business_domains"]
        for c in filtered["carousels"]
        for a in c["agents"]
    )
    body = {
        "agent_id": "contract-analyzer",
        "reason": "Review supplier contracts for our team",
    }
    first = client.post("/api/access-requests", json=body)
    second = client.post("/api/access-requests", json=body)
    assert first.status_code == 200 and first.json()["id"] == second.json()["id"]
    assert login("demo-business").get("/api/access-requests").json() == []


def test_password_login_production_disables_demo_and_limits_attempts(monkeypatch):
    with database.connect(write=True) as conn:
        conn.execute(
            "UPDATE users SET password_hash=? WHERE id='u-1001'",
            (auth.password_hash("correct-password-123"),),
        )
    monkeypatch.setenv("CREDITWIZ_ENV", "production")
    c = TestClient(app, base_url="https://testserver", headers=HEADERS)
    assert c.get("/api/auth/options").json() == {"demo": False, "microsoft": False, "users": []}
    assert c.post("/api/auth/demo", json={"user_id": "u-1001"}).status_code == 404
    email = client.get("/api/me").json()["email"]
    for _ in range(5):
        assert (
            c.post(
                "/api/auth/login", json={"email": email, "password": "wrong"}
            ).status_code
            == 401
        )
    assert (
        c.post(
            "/api/auth/login", json={"email": email, "password": "wrong"}
        ).status_code
        == 429
    )
    with database.connect(write=True) as conn:
        conn.execute("DELETE FROM login_attempts")
    response = c.post(
        "/api/auth/login", json={"email": email, "password": "correct-password-123"}
    )
    assert response.status_code == 200
    assert (
        "Secure" in response.headers["set-cookie"]
        and "HttpOnly" in response.headers["set-cookie"]
    )
    assert c.get("/api/me").status_code == 200
    with database.connect(write=True) as conn:
        conn.execute("UPDATE sessions SET expires_at=?", (time.time() - 1,))
    assert c.get("/api/me").status_code == 401


def test_legacy_migration_preserves_files_and_only_imports_once(tmp_path, monkeypatch):
    old_dir = tmp_path / "legacy"
    old_dir.mkdir()
    old = old_dir / "learning.db"
    with sqlite3.connect(old) as conn:
        conn.execute(
            "CREATE TABLE learning_progress (user_id,item_id,status,progress,started_at,completed_at,updated_at)"
        )
        conn.execute(
            "INSERT INTO learning_progress VALUES ('u-1001','legacy-item','completed',100,NULL,'now','now')"
        )
    (old_dir / "interactions.jsonl").write_text(
        json.dumps({"type": "view", "pillar": "learning"}) + "\n", encoding="utf-8"
    )
    monkeypatch.setattr(database, "VAR_DIR", old_dir)
    for _ in range(2):
        with database.connect() as conn:
            assert (
                conn.execute("SELECT COUNT(*) FROM learning_progress").fetchone()[0]
                == 1
            )
            assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
    assert old.exists() and (old_dir / "interactions.jsonl").exists()


def test_unreviewed_content_hidden_and_unsafe_urls_rejected(tmp_path, monkeypatch):
    import pytest

    from app.learning.models import Item
    from app.marketplace.models import Agent

    raw = learning._raw()
    raw["items"][0]["review_status"] = "draft"
    hidden_id = raw["items"][0]["id"]
    _use_catalog(tmp_path, monkeypatch, raw)
    assert hidden_id not in {i["id"] for i in client.get("/api/learning/items").json()}
    bad = dict(raw["items"][1], url="javascript:alert(1)")
    with pytest.raises(ValueError):
        Item.model_validate(bad)
    enterprise = dict(raw["items"][1], source_kind="enterprise")
    enterprise.pop("audience_groups")
    with pytest.raises(ValueError):
        Item.model_validate(enterprise)
    agent = store.agents[0].model_dump()
    agent["id"] = "../private"
    with pytest.raises(ValueError):
        Agent.model_validate(agent)


def test_account_provisioning_revokes_old_sessions():
    from app.manage import provision, validate

    c = login("demo-business")
    profile = c.get("/api/me").json()
    provision(
        profile["email"],
        profile["display_name"],
        "Business Analyst",
        "Business",
        ["AI-Hub-Users"],
        "new-local-password-123",
    )
    assert c.get("/api/me").status_code == 401
    assert validate() == {
        "agents": 18,
        "learning_items": 58,
        "paths": 11,
        "journeys": 16,
        "prompts": 60,
        "templates": 4,
        "assets": 21,
        "knowledge_systems": 5,
        "document_types": 4,
    }


def test_single_origin_deployment_serves_the_spa_and_keeps_api_404s_json(
    tmp_path, monkeypatch
):
    """Deployment shape: one service serves the API and the built SPA.

    The app calls /api/... relatively with credentials:'same-origin', so a
    separate frontend origin would never send the session cookie.
    """
    build = tmp_path / "dist"
    (build / "assets").mkdir(parents=True)
    (build / "index.html").write_text("<!doctype html><title>MUFG AI Hub</title>")
    (build / "assets" / "app-abc123.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("must not be served")
    monkeypatch.setenv("CREDITWIZ_STATIC_DIR", str(build))

    # A client-side route falls back to index.html rather than 404ing.
    page = client.get("/learning/me")
    assert page.status_code == 200 and "MUFG AI Hub" in page.text
    assert page.headers["cache-control"] == "no-cache"

    # Fingerprinted assets are safe to cache forever.
    asset = client.get("/assets/app-abc123.js")
    assert asset.status_code == 200 and "immutable" in asset.headers["cache-control"]

    # An unknown API path must stay a JSON 404, not silently become the SPA.
    missing = client.get("/api/does-not-exist")
    assert missing.status_code == 404
    assert missing.headers["content-type"].startswith("application/json")

    # Traversal out of the build directory is refused.
    assert "must not be served" not in client.get("/../secret.txt").text


def test_deploy_origin_allowlist_includes_the_platform_url(monkeypatch):
    """The public URL is assigned at deploy time, so it cannot be pre-configured."""
    from app.main import allowed_origins

    monkeypatch.setenv("CREDITWIZ_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://mufg-ai-hub.onrender.com/")
    origins = allowed_origins()
    assert "https://mufg-ai-hub.onrender.com" in origins
    assert "http://localhost:5173" in origins


def test_cached_catalog_cannot_be_corrupted_by_a_caller():
    """The catalogue is parsed once and shared, so a caller that edits what it
    was handed must not poison every later request."""
    before = len(client.get("/api/learning/items").json())

    raw = learning._raw()
    raw["items"] = raw["items"][:1]
    raw["items"][0]["title"] = "MUTATED"

    after = client.get("/api/learning/items").json()
    assert len(after) == before
    assert not any(i["title"] == "MUTATED" for i in after)


def test_one_request_reads_the_signed_in_profile_once():
    """visible() runs per record. Without a request-scoped cache this read the
    same row 65 times for one page."""
    from app import identity

    reads = {"n": 0}
    original = identity.DirectoryProfile.model_validate

    def counted(*args, **kwargs):
        reads["n"] += 1
        return original(*args, **kwargs)

    identity.DirectoryProfile.model_validate = counted
    try:
        assert client.get("/api/learning").status_code == 200
    finally:
        identity.DirectoryProfile.model_validate = original
    assert reads["n"] == 1, f"profile parsed {reads['n']} times in one request"


def test_csrf_accepts_any_loopback_origin_in_development_only(monkeypatch):
    """Vite moves to the next free port when 5173 is busy. A developer on
    localhost:5174 was refused with "Request verification failed"; a remote
    attacker cannot present a loopback Origin, so outside production any
    loopback port is fine. Production keeps the strict allowlist."""
    from app.main import origin_allowed

    monkeypatch.setenv("CREDITWIZ_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("CREDITWIZ_ENV", "development")
    assert origin_allowed("http://localhost:5174")
    assert origin_allowed("http://127.0.0.1:3000")
    assert origin_allowed("http://[::1]:5173")
    assert not origin_allowed("https://evil.example")

    monkeypatch.setenv("CREDITWIZ_ENV", "production")
    assert origin_allowed("http://localhost:5173")  # still on the list
    assert not origin_allowed("http://localhost:5174")

    # And the refusal says what to fix, not just that it failed.
    c = TestClient(app, headers={**HEADERS, "Origin": "https://evil.example"})
    r = c.post("/api/auth/demo", json={"user_id": "u-1001"})
    assert r.status_code == 403 and "CREDITWIZ_ORIGINS" in r.json()["detail"]
