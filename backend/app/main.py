import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from . import auth, data, entra, identity, integrations
from .account import router as account_router
from .community.router import router as community_router
from .context.router import router as context_router
from .journeys.router import router as journeys_router
from .knowledge.router import router as knowledge_router
from .learning.router import router as learning_router
from .marketplace.router import router as marketplace_router
from .marketplace.store import store as marketplace_store
from .hub.router import router as hub_router
from .prompts.router import router as prompts_router
from .models import (
    CurrentUser,
    Domain,
    HomeResponse,
    Notification,
    PersonaInfo,
    Pillar,
    SearchResponse,
    SearchResult,
)
from .permissions import visible


@asynccontextmanager
async def lifespan(app):
    auth.seed_users()
    # Embed the catalogue once at boot. Unchanged agents are skipped, so this is
    # a no-op on every restart after the first unless the catalogue was edited.
    # It never raises: a failed index leaves search on the lexical ranker.
    from .marketplace.keyword import index as keyword_index
    from .marketplace.semantic import index as semantic_index
    from .marketplace.store import store as agent_store

    import logging

    keyword_index.sync(agent_store.all_agents)
    counts = semantic_index.sync(agent_store.all_agents)
    if any(counts.values()):
        logging.getLogger("mufg.semantic").info("Semantic index synced: %s", counts)
    # The Prompts & Skills and Learning agents: their catalogues, then what
    # people contributed through Create, rebuilt from the contributions table.
    from .learning import agent as learning_agent
    from .prompts import agent as prompts_agent
    from .prompts.contributions import reindex

    synced = {"prompts": prompts_agent.sync(), "learning": learning_agent.sync()}
    synced.update({f"{name} contributions": c for name, c in reindex().items()})
    for name, c in synced.items():
        if c and (c["added"] or c["updated"] or c["removed"]):
            logging.getLogger("mufg.retrieval").info("%s index synced: %s", name, c)
    # Build the ONNX sessions now, not on the first user's search: Discover's,
    # and the one the agents share. Costs nothing if an index is unavailable.
    semantic_index.search("warm up the embedding session", limit=1)
    prompts_agent.agent.semantic.search("warm up the embedding session", frozenset({"-"}), limit=1)
    yield


app = FastAPI(
    title="MUFG AI Hub API", version="0.2.0", lifespan=lifespan
)
app.include_router(auth.router)
app.include_router(entra.router)
app.include_router(integrations.router)
app.include_router(account_router)
app.include_router(marketplace_router)
app.include_router(learning_router)
app.include_router(community_router)
app.include_router(context_router)
app.include_router(journeys_router)
app.include_router(knowledge_router)
app.include_router(prompts_router)
app.include_router(hub_router)


def allowed_origins() -> list[str]:
    """Origins allowed to make state-changing calls.

    The hosting platform assigns the public URL at deploy time, so it cannot be
    written into CREDITWIZ_ORIGINS ahead of time. Render exposes it as
    RENDER_EXTERNAL_URL; trust that in addition to whatever is configured.
    """
    origins = [
        o.strip()
        for o in os.environ.get(
            "CREDITWIZ_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
        if o.strip()
    ]
    external = os.environ.get("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
    if external and external not in origins:
        origins.append(external)
    return origins


def origin_allowed(origin: str) -> bool:
    """The CSRF allowlist, plus any loopback origin in development.

    Vite picks the next free port when 5173 is busy, and a developer on
    http://localhost:5174 was met with "Request verification failed". A
    remote attacker cannot present a loopback Origin, so accepting them
    outside production costs nothing. Production keeps the strict list.
    """
    if origin in allowed_origins():
        return True
    if auth.production():
        return False
    host = urlparse(origin).hostname or ""
    return host in {"localhost", "127.0.0.1", "::1"}


@app.middleware("http")
async def session_boundary(request: Request, call_next):
    if not request.url.path.startswith("/api/") or request.method == "OPTIONS":
        return await call_next(request)
    if request.method not in ("GET", "HEAD"):
        origin = request.headers.get("origin")
        if request.headers.get("X-CreditWiz-Request") != "1":
            return JSONResponse(
                {"detail": "Request blocked: missing X-CreditWiz-Request header"},
                status_code=403,
            )
        if origin and not origin_allowed(origin):
            return JSONResponse(
                {
                    "detail": f"Request blocked: origin {origin} is not allowed. "
                    "Set CREDITWIZ_ORIGINS to include it."
                },
                status_code=403,
            )
    public = request.url.path in (
        "/api/health",
        "/api/auth/options",
        "/api/auth/login",
        "/api/auth/demo",
        # The Microsoft sign-in round trip starts and ends signed out.
        "/api/auth/microsoft/login",
        "/api/auth/microsoft/callback",
    )
    uid = auth.resolve_session(request.cookies.get(auth.COOKIE))
    if not public and not uid:
        return JSONResponse({"detail": "Sign in to the MUFG AI Hub"}, status_code=401)
    token = auth.current_id.set(uid)
    profile_token = identity.reset_profile_cache()
    try:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
    finally:
        identity.restore(profile_token)
        auth.current_id.reset(token)


app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def current_user() -> CurrentUser:
    """Directory profile + derived persona. Persona is never stored on the profile."""
    profile = identity.load_profile()
    persona = identity.derive_persona(profile)
    return CurrentUser(
        id=profile.id,
        first_name=profile.first_name,
        display_name=profile.name,
        initials=profile.initials,
        email=profile.email,
        job_title=profile.job_title,
        department=profile.department,
        business_unit=profile.business_unit,
        location=profile.location,
        manager=profile.manager,
        is_admin=identity.is_admin(profile),
        unread_notifications=len([n for n in notifications() if not n.read]),
        demo_mode=not auth.production(),
        persona=PersonaInfo(**persona.model_dump()),
    )


def visible_pillars(user: CurrentUser) -> list[Pillar]:
    return [p for p in data.PILLARS if user.is_admin or not p.admin_only]


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/me", response_model=CurrentUser)
def me() -> CurrentUser:
    return current_user()


@app.get("/api/domains", response_model=list[Domain])
def domains() -> list[Domain]:
    return [
        Domain(id="all", name="All business domains"),
        *[
            Domain(id=d, name=d)
            for d in sorted(
                {
                    d
                    for a in marketplace_store.agents
                    if visible(a)
                    for d in a.business_domains
                }
            )
        ],
    ]


@app.get("/api/pillars", response_model=list[Pillar])
def pillars() -> list[Pillar]:
    return visible_pillars(current_user())


@app.get("/api/home", response_model=HomeResponse)
def home() -> HomeResponse:
    user = current_user()
    return HomeResponse(
        user=user,
        domains=domains(),
        pillars=visible_pillars(user),
    )


@app.get("/api/pillars/{pillar_id}", response_model=Pillar)
def pillar(pillar_id: str) -> Pillar:
    for p in visible_pillars(current_user()):
        if p.id == pillar_id:
            return p
    raise HTTPException(status_code=404, detail="Pillar not found")


@app.get("/api/notifications", response_model=list[Notification])
def notifications() -> list[Notification]:
    from .database import connect

    with connect() as conn:
        read = {
            r[0]
            for r in conn.execute(
                "SELECT notification_id FROM notification_reads WHERE user_id=?",
                (auth.user_id(),),
            )
        }
    from .account import preferences

    show_learning = preferences().show_learning_reminders
    return [
        n.model_copy(update={"read": n.id in read or n.read})
        for n in data.NOTIFICATIONS
        if show_learning or not n.href.startswith("/learning")
    ]


@app.post("/api/notifications/read")
def mark_notifications_read():
    from .database import connect

    with connect(write=True) as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO notification_reads VALUES (?,?)",
            [(auth.user_id(), n.id) for n in data.NOTIFICATIONS],
        )
    return {"ok": True}


# A typed character triggers this, so it must stay cheap. Below this length a
# query is still being typed and hybrid retrieval would rank noise.
TYPEAHEAD_MIN_QUERY = 3
TYPEAHEAD_AGENTS = 5


def _typeahead_agents(needle: str) -> list[SearchResult]:
    """Agent suggestions for the header search: name matches, then real search.

    Two different questions get typed into one box. "Sanctions Review" is
    navigation -- the person knows the name and wants to be taken there, which
    substring matching answers instantly and exactly. "check customers against
    sanctions lists" is a search, and no substring of it appears in any name or
    tagline, which is why the header used to dead-end in "No matches" while the
    marketplace page below answered the same question correctly.

    So: exact-ish matches first because they are precise, then the same hybrid
    retrieval and fusion the marketplace page runs, filling what is left. A
    single generic word like "agent" clears no relevance floor and is meant not
    to -- the name matches carry it.

    One deliberate difference from the marketplace path: intent comes from the
    local lexicon, never from Claude. This fires every 160 ms while someone
    types, and a model call per keystroke would be slow and expensive for a
    suggestion list. The lexicon is the same fallback a search uses when Claude
    is unavailable.
    """
    from .identity import load_profile
    from .marketplace import keyword, search as marketplace_search, semantic

    visible_agents = [a for a in marketplace_store.agents if visible(a)]

    def as_result(agent) -> SearchResult:
        return SearchResult(
            kind="agent", title=agent.name, href=f"/marketplace/agents/{agent.id}"
        )

    by_name = [
        a
        for a in visible_agents
        if needle in a.name.lower()
        or needle in a.tagline.lower()
        or any(needle in t.lower() for t in a.tags)
    ]
    if len(needle) < TYPEAHEAD_MIN_QUERY or len(by_name) >= TYPEAHEAD_AGENTS:
        return [as_result(a) for a in by_name[:TYPEAHEAD_AGENTS]]

    intent = marketplace_search.local_intent(needle)
    audience = load_profile().groups
    retrieved = (
        semantic.index.search(
            marketplace_search.retrieval_text(needle), groups=audience
        )
        if semantic.index.available
        else None
    )
    if keyword.index.size == 0:
        keyword.index.sync(marketplace_store.all_agents)
    matched = keyword.index.search(
        marketplace_search.keyword_text(needle),
        allowed={a.id for a in visible_agents},
    )
    matches = marketplace_search.rank(
        needle,
        intent,
        visible_agents,
        similar=retrieved,
        keywords=matched,
    )
    seen = {a.id for a in by_name}
    ordered = by_name + [m.agent for m in matches if m.agent.id not in seen]
    return [as_result(a) for a in ordered[:TYPEAHEAD_AGENTS]]


def _learning_hits(needle: str) -> list[SearchResult]:
    """Learning items for a query, best first.

    A title typed in part matches as it always has. A sentence, which the home
    page's ask box invites, matches an item carrying at least half of its
    subject words; the old whole-string match found nothing for one.
    """
    from .learning.router import _load
    from .learning.search import score_items

    _, items = _load()
    return [
        SearchResult(kind="learning", title=i.title, href=f"/learning/items/{i.id}")
        for _, i in score_items(needle, items)
    ]


TYPEAHEAD_PROMPTS = 5


def _prompt_hits(needle: str) -> list[SearchResult]:
    """Validated prompts for a query, with the prompt library's own matching."""
    from .prompts.store import search as search_prompts
    from .prompts.store import store as prompt_store

    return [
        SearchResult(kind="prompt", title=p.title, href=f"/library/prompts/{p.id}")
        for _, p in search_prompts(needle, prompt_store.library.prompts)[:TYPEAHEAD_PROMPTS]
    ]


@app.get("/api/search", response_model=SearchResponse)
def search(q: str = Query(default="", max_length=200)) -> SearchResponse:
    needle = q.strip().lower()
    if not needle:
        return SearchResponse(query=q, results=[])
    agent_hits = _typeahead_agents(needle)
    return SearchResponse(
        query=q, results=(agent_hits + _prompt_hits(needle) + _learning_hits(needle))[:20]
    )


# --- built frontend ---------------------------------------------------------
# Every API call in the SPA is a relative /api/... with credentials:'same-origin',
# so the app and the API must share an origin. Serving the build from here keeps
# the session cookie working and removes CORS from the deployment entirely.
# Registered last so every API route is matched first.

def static_root() -> Path:
    """Resolved at request time, not import time, so it is testable and so a
    dev server without a build still starts."""
    return Path(
        os.environ.get(
            "CREDITWIZ_STATIC_DIR",
            Path(__file__).resolve().parents[2] / "frontend" / "dist",
        )
    ).resolve()


@app.get("/{asset_path:path}", include_in_schema=False)
def spa(asset_path: str):
    root = static_root()
    if asset_path.startswith("api/") or not (root / "index.html").is_file():
        raise HTTPException(status_code=404, detail="Not found")
    target = (root / asset_path).resolve()
    # is_relative_to rejects ../ traversal out of the build directory.
    if asset_path and target.is_file() and target.is_relative_to(root):
        # Vite fingerprints filenames under assets/, so those are immutable.
        cache = (
            "public, max-age=31536000, immutable"
            if asset_path.startswith("assets/")
            else "no-cache"
        )
        return FileResponse(target, headers={"Cache-Control": cache})
    # Any other path is a client-side route. index.html must never be cached
    # or a redeploy leaves browsers asking for asset names that are gone.
    return FileResponse(root / "index.html", headers={"Cache-Control": "no-cache"})
