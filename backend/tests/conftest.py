import pytest

from app import auth, database
from app.learning.store import store as learning_store


@pytest.fixture(scope="session", autouse=True)
def semantic_index(tmp_path_factory):
    """One populated index for the whole run.

    The module-level TestClient never enters the lifespan, so nothing would
    build the index and every search would hit the fallback. Build it once
    here, in its own directory, so tests exercise the retrieval path that
    production uses.
    """
    import os

    os.environ["CREDITWIZ_INDEX_DIR"] = str(tmp_path_factory.mktemp("chroma"))
    from app.marketplace.semantic import index
    from app.marketplace.store import store

    index.sync(store.all_agents)
    yield
    os.environ.pop("CREDITWIZ_INDEX_DIR", None)


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch, request):
    monkeypatch.setenv("CREDITWIZ_ENV", "development")
    monkeypatch.setenv("CREDITWIZ_DISABLE_LLM", "1")
    # A test that switches the model on to stand in for the planner must not
    # send the agents' reranks to the real API; one that tests reranking
    # sets its own.
    from app.hub import llm

    monkeypatch.setattr(llm, "rerank", lambda *args, **kwargs: None)
    monkeypatch.setattr(database, "VAR_DIR", tmp_path)
    database._ready.discard(str((tmp_path / "hub.db").resolve()))
    learning_store.invalidate()
    # In-memory state of the connected systems: tokens, the last errors they
    # reported, and what was fetched from them.
    from app import entra, integrations
    from app.community import vivaengage
    from app.learning import mslearn, pluralsight

    entra._grants.clear()
    entra._pending.clear()
    vivaengage._engage_ids.clear()
    integrations._errors.clear()
    mslearn._pages.clear()
    pluralsight._held.clear()
    for name in ("PLURALSIGHT_API_KEY", "PLURALSIGHT_SSO_ORG"):
        monkeypatch.delenv(name, raising=False)
    auth.seed_users()
    token = auth.current_id.set("u-1001")
    client = getattr(request.module, "client", None)
    if client:
        client.cookies.clear()
        client.headers["X-CreditWiz-Request"] = "1"
        assert (
            client.post("/api/auth/demo", json={"user_id": "u-1001"}).status_code == 200
        )
    yield
    if client:
        client.cookies.clear()
    auth.current_id.reset(token)
