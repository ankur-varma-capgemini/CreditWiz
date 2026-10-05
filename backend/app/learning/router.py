"""Learning owns the catalog, authored paths, curation and progress."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import APIRouter, HTTPException

from .. import http, integrations
from .. import personas as hub_personas
from ..context import store as context_store
from ..hub import guardrails
from ..identity import derive_persona, load_profile
from ..marketplace.store import store as marketplace_store
from ..permissions import resolve_persona, visible
from ..retrieval.ask import ask
from ..retrieval.models import AgentAnswer, AgentSearch
from . import mslearn, pluralsight
from . import progress as progress_store
from . import ratings as ratings_store
from .models import (
    Item,
    ItemDetail,
    ItemWithProgress,
    LearningHome,
    LearningPath,
    MyLearning,
    ProgressIn,
    ProviderResult,
    ProviderResults,
    RatingIn,
    Section,
    TopicCoverage,
)
from .store import store as catalog_store

_DATA_DIR = Path(
    os.environ.get("CREDITWIZ_DATA_DIR", Path(__file__).resolve().parents[2] / "data")
)
router = APIRouter(prefix="/api/learning", tags=["learning"])
PROFICIENCY_NOTE = (
    "Progress and topic coverage come from the items you mark complete. Proficiency will be "
    "measured separately once the enterprise measure is agreed."
)
_PATH_AFFINITY = (10.0, 6.0, 3.0)
_AGENT_PATH_AFFINITY = (5.0, 3.0, 1.0)
_DOC_TYPES = ("documentation", "guide", "confluence")


def _raw() -> dict:
    """The catalogue as authored. Parsed once and cached by the store."""
    return catalog_store.raw


def validate_catalog(raw: dict) -> tuple[list[LearningPath], list[Item]]:
    items = [Item.model_validate(i) for i in raw["items"]]
    ids = {i.id for i in items}
    if len(ids) != len(items):
        raise ValueError("Duplicate learning item id")
    links = {i.id: i.prerequisites for i in items}

    def check(key, visited):
        if key not in ids:
            raise ValueError(f"Unknown prerequisite: {key}")
        if key in visited:
            raise ValueError("Learning prerequisites must not contain cycles")
        for dep in links[key]:
            check(dep, visited | {key})

    for i in items:
        check(i.id, set())
    paths = [LearningPath.model_validate(p) for p in raw["paths"]]
    for p in paths:
        if len(p.steps) != len(set(p.steps)) or any(s not in ids for s in p.steps):
            raise ValueError(f"Invalid steps in learning path {p.id}")
    path_ids = {p.id for p in paths}
    if len(path_ids) != len(paths):
        raise ValueError("Duplicate learning path id")
    if any(i.path not in path_ids for i in items):
        raise ValueError("Unknown learning item path")
    if any(
        p not in path_ids
        for key, values in raw.get("persona_paths", {}).items()
        if not key.startswith("_")
        for p in values
    ):
        raise ValueError("Unknown persona path")
    return paths, items


def _load() -> tuple[list[LearningPath], list[Item]]:
    """Catalogue narrowed to what the signed-in user may see.

    Parsing and validation are cached; visibility depends on the user's groups
    so it stays per-request.
    """
    paths, items = catalog_store.catalog
    items = [i for i in items if visible(i)]
    allowed = {i.id for i in items}
    paths = [
        p.model_copy(update={"steps": [s for s in p.steps if s in allowed]})
        for p in paths
    ]
    return [p for p in paths if p.steps or any(i.path == p.id for i in items)], items


def _persona_paths():
    return catalog_store.persona_paths


def _derived_persona_id():
    return derive_persona(load_profile()).id


def _user_id():
    return load_profile().id


def _affinity(path, pid, scale):
    paths = _persona_paths().get(pid, [])
    return scale[paths.index(path)] if path in paths[: len(scale)] else 0.0


def curation_breakdown(item, persona):
    tags = {t.lower() for t in (persona.interests.tags if persona else [])}
    return {
        "path_affinity": _affinity(
            item.path, persona.id if persona else None, _PATH_AFFINITY
        ),
        "persona_tag": 2.0 * len(tags & {t.lower() for t in item.tags}),
        "persona_match": 2.0 if persona and persona.id in item.personas else 0.0,
    }


def curation_score(item, persona):
    return sum(curation_breakdown(item, persona).values())


def recommendation_reason(item, persona, path_titles: dict[str, str]) -> str:
    """Why an item suits this person, from the same inputs that rank it.

    Empty when nothing ties the item to them: it is simply in the catalogue.
    """
    role = persona.label.lower()
    if persona.id in item.required_for:
        return f"Required for your {role} role."
    if persona.id in item.personas:
        return f"Mapped to your {role} role."
    if _affinity(item.path, persona.id, _PATH_AFFINITY):
        return f"Part of the {path_titles.get(item.path, item.path)} path, one of your role's learning paths."
    interests = {t.lower() for t in persona.interests.tags}
    shared = [t for t in item.tags if t.lower() in interests]
    if shared:
        return f"Covers {', '.join(shared)}, which your role works with."
    return ""


def recommend_for_persona(persona, limit=6):
    _, items = _load()
    ranked = sorted(
        items, key=lambda i: (-i.priority, -curation_score(i, persona), i.id)
    )
    return [i for i in ranked if curation_score(i, persona) > 0][:limit]


def recommend_for_agent(agent_id, persona=None, limit=3):
    agent = marketplace_store.agent(agent_id)
    if agent is None or not visible(agent):
        return []
    _, items = _load()
    tags = {t.lower() for t in agent.tags}
    pid = hub_personas.persona_id(persona) if persona else None

    def relevance(i):
        return (10 if agent_id in i.related_agents else 0) + 2 * len(
            tags & {t.lower() for t in i.tags}
        )

    ranked = sorted(
        items,
        key=lambda i: (
            -(agent_id in i.related_agents),
            -(relevance(i) + _affinity(i.path, pid, _AGENT_PATH_AFFINITY)),
            i.id,
        ),
    )
    return [i for i in ranked if relevance(i) > 0][:limit]


def _with_progress(items, persona_id):
    _, allowed_items = _load()
    allowed = {i.id for i in allowed_items}
    agents = {a.id for a in marketplace_store.agents if visible(a)}
    uid = _user_id()
    rows = progress_store.all_for(uid)
    stars = ratings_store.summaries(uid)
    out = []
    for i in items:
        if i.id not in allowed:
            continue
        row = rows.get(i.id, {})
        blocked = [
            dep
            for dep in i.prerequisites
            if rows.get(dep, {}).get("status") != "completed"
        ]
        payload = i.model_dump()
        payload["prerequisites"] = [dep for dep in i.prerequisites if dep in allowed]
        payload["related_agents"] = [aid for aid in i.related_agents if aid in agents]
        out.append(
            ItemWithProgress(
                **payload,
                **stars.get(i.id, ratings_store.empty()),
                status=row.get("status", "not_started"),
                progress=row.get("progress", 0),
                required=persona_id in i.required_for,
                blocked_by=[dep for dep in blocked if dep in allowed],
                prerequisite_unavailable=any(dep not in allowed for dep in blocked),
            )
        )
    return _providers(out)


def _providers(items: list[ItemWithProgress]) -> list[ItemWithProgress]:
    """What each item's provider adds: Pluralsight's live details and the
    learner's progress when Pluralsight is connected, where Start opens, and
    whether the item can be read in the hub. A provider that fails leaves the
    catalogue's own values, and the Integrations page says why."""
    courses = [i for i in items if i.source == "Pluralsight"]
    live: dict[str, dict] = {}
    done: dict[str, tuple[int, bool]] = {}
    if courses and pluralsight.configured():
        refs = [i.provider_ref for i in courses]
        try:
            live = pluralsight.courses(refs)
            done = pluralsight.progress(load_profile().email, refs)
            integrations.clear_error("pluralsight", None)
        except http.ExternalError as e:
            integrations.record_error("pluralsight", None, integrations.explain(e))
    for i in items:
        if i.source == "Pluralsight":
            data = live.get(i.provider_ref)
            if data:
                i.title = data.get("title") or i.title
                i.description = data.get("description") or data.get("shortDescription") or i.description
                i.level = data.get("level") or i.level
                i.duration_seconds = int(data.get("courseSeconds") or i.duration_seconds)
                if data.get("authors"):
                    i.instructor = ", ".join(data["authors"])
                i.live = True
            if i.provider_ref in done:
                # Pluralsight's own record of what was watched replaces self-reporting.
                pct, finished = done[i.provider_ref]
                i.progress = 100 if finished else pct
                i.status = "completed" if finished else "in_progress" if pct else i.status
            i.launch_url = pluralsight.launch_url(i.title, i.url, data)
        elif i.source == "Microsoft Learn" and mslearn.is_learn_url(i.url):
            i.launch_url = i.url
            i.read_in_hub = True
    return items


def _paths_with_progress(paths, items):
    by_id = {i.id: i for i in items}
    output = []
    for p in paths:
        steps = p.steps or [i.id for i in items if i.path == p.id]
        next_id = next(
            (
                s
                for s in steps
                if by_id[s].status != "completed"
                and not by_id[s].blocked_by
                and not by_id[s].prerequisite_unavailable
            ),
            None,
        )
        output.append(
            p.model_copy(
                update={
                    "steps": steps,
                    "total_steps": len(steps),
                    "completed_steps": sum(
                        by_id[s].status == "completed" for s in steps
                    ),
                    "next_item_id": next_id,
                }
            )
        )
    return output


@router.get("", response_model=LearningHome)
def home(persona: str | None = None):
    paths, items = _load()
    p = resolve_persona(persona)
    enriched = _with_progress(items, p.id)
    required = [i for i in enriched if i.required and i.status != "completed"]
    continuing = [i for i in enriched if i.status == "in_progress" and not i.required]
    role = [
        i
        for i in enriched
        if i.status == "not_started"
        and not i.required
        and not i.blocked_by
        and not i.prerequisite_unavailable
        and curation_score(i, p) > 0
    ]
    role.sort(key=lambda i: (-i.priority, -curation_score(i, p), i.id))
    # Copy before annotating: these objects are shared with the type-based
    # sections below, and mutating them leaks the reason onto every other card.
    titles = {path.id: path.title for path in paths}
    role = [
        i.model_copy(update={"recommendation_reason": recommendation_reason(i, p, titles)})
        for i in role
    ]
    sections = []
    if required:
        sections.append(
            Section(
                id="required",
                title="Required for your role",
                subtitle="Assigned learning. Complete prerequisites first.",
                items=required,
            )
        )
    if continuing:
        sections.append(
            Section(
                id="continue",
                title="Continue learning",
                subtitle="Pick up where you left off.",
                items=continuing,
            )
        )
    if role:
        sections.append(
            Section(
                id="role",
                title="Recommended for your role",
                subtitle="Based on your role and the curated catalog.",
                items=role[:4],
            )
        )
    # The type sections are a browse index, so they stay complete for their type
    # even when an item also appears in the personalised rows above. Deduping
    # them removed whole sections and made the index misleading.
    for sid, title, subtitle, types in (
        ("best-practice", "Best practices", "How our teams get reliable results.", ("best-practice",)),
        ("docs", "Documentation and guides", "Reference material and how-to guides.", _DOC_TYPES),
        ("quick-reference", "Quick references", "One-pagers to keep open while you work.", ("quick-reference",)),
    ):
        picked = [
            i
            for i in enriched
            if i.type in types and (p.id in i.personas or i.required)
        ]
        if picked:
            sections.append(Section(id=sid, title=title, subtitle=subtitle, items=picked))
    paths = _paths_with_progress(paths, enriched)
    role_ids = _persona_paths().get(p.id, [])
    return LearningHome(
        persona=p.id,
        persona_label=p.label,
        paths=paths,
        sections=sections,
        item_count=len(items),
        role_paths=sorted(
            [path for path in paths if path.id in role_ids],
            key=lambda path: role_ids.index(path.id),
        ),
    )


@router.get("/items", response_model=list[ItemWithProgress])
def list_items(
    path: str | None = None,
    type: str | None = None,
    topic: str | None = None,
    agent: str | None = None,
    status: str | None = None,
    q: str = "",
    persona: str | None = None,
    source: str | None = None,
):
    paths, items = _load()
    p = resolve_persona(persona)
    ordered = None
    if source:
        items = [i for i in items if i.source.lower() == source.lower()]
    if path:
        selected = next((p for p in paths if p.id == path), None)
        if selected is None:
            raise HTTPException(404, "Learning path not found")
        ordered = selected.steps or [i.id for i in items if i.path == path]
        items = sorted(
            [i for i in items if i.id in ordered], key=lambda i: ordered.index(i.id)
        )
    if type:
        items = [
            i
            for i in items
            if i.type == type or (type == "docs" and i.type in _DOC_TYPES)
        ]
    if topic:
        items = [i for i in items if topic.lower() in [t.lower() for t in i.topics]]
    if agent:
        items = [i for i in items if agent in i.related_agents]
    if q.strip():
        terms = q.lower().split()
        items = [
            i
            for i in items
            if all(
                t in " ".join([i.title, i.description, *i.tags, *i.topics]).lower()
                for t in terms
            )
        ]
    out = _with_progress(items, p.id)
    if ordered:
        for i in out:
            i.sequence = ordered.index(i.id) + 1
    return [i for i in out if not status or i.status == status]


@router.post("/search", response_model=AgentAnswer)
def ask_agent(body: AgentSearch) -> AgentAnswer:
    """The Learning agent, over the items this person may see and the skill
    videos they may see."""
    from .agent import find

    _, items = _load()
    persona_id = _derived_persona_id()
    return ask(
        "learning",
        body.query,
        lambda searched, model_reads: find([searched], items, persona_id=persona_id, rerank_query=model_reads),
    )


@router.get("/items/{item_id}", response_model=ItemDetail)
def item(item_id: str, persona: str | None = None):
    paths, items = _load()
    current = next((i for i in items if i.id == item_id), None)
    if current is None:
        raise HTTPException(404, "Learning item not found")
    p = resolve_persona(persona)
    related = sorted(
        (i for i in items if i.id != item_id),
        key=lambda i: (
            -(
                3 * len(set(i.related_agents) & set(current.related_agents))
                + 2 * len(set(i.topics) & set(current.topics))
                + (i.path == current.path)
            )
        ),
    )[:3]
    enriched = {i.id: i for i in _with_progress([current, *related], p.id)}
    # The detail page and the side panel say why it is suggested, wherever it
    # was opened from: a shelf, a search or a recommendation.
    titles = {path.id: path.title for path in paths}
    detail = enriched[item_id].model_copy(update={"recommendation_reason": recommendation_reason(current, p, titles)})
    return ItemDetail(
        **detail.model_dump(),
        path_title=titles.get(current.path, current.path),
        related_items=[enriched[i.id] for i in related],
        related_agent_names={
            a.id: a.name
            for a in marketplace_store.agents
            if a.id in current.related_agents and visible(a)
        },
    )


@router.post("/progress", response_model=ItemWithProgress)
def set_progress(body: ProgressIn):
    _, items = _load()
    current = next((i for i in items if i.id == body.item_id), None)
    if current is None:
        raise HTTPException(404, "Learning item not found")
    pid = _derived_persona_id()
    enriched = _with_progress([current], pid)[0]
    if enriched.status != "completed" and (
        enriched.blocked_by or enriched.prerequisite_unavailable
    ):
        raise HTTPException(
            409, "Complete the required prerequisites before starting this item."
        )
    event = {
        "pillar": "learning",
        "type": "learning_complete",
        "subject_id": current.id,
        "subject_type": current.type,
        "persona": pid,
        "topics": current.topics + current.tags,
        "meta": {"path": current.path, "measurement": "self_reported_completion"},
    }
    progress_store.record(_user_id(), current.id, body.status, body.progress, event)
    return _with_progress([current], pid)[0]


@router.post("/ratings", response_model=ItemWithProgress)
def rate(body: RatingIn):
    """Rate an item you have actually opened.

    Requiring a start is what keeps this from becoming a popularity vote among
    people who never watched the thing.
    """
    _, items = _load()
    current = next((i for i in items if i.id == body.item_id), None)
    if current is None:
        raise HTTPException(404, "Learning item not found")
    pid = _derived_persona_id()
    uid = _user_id()
    if _with_progress([current], pid)[0].status == "not_started":
        raise HTTPException(409, "Open this item before rating it.")

    if body.stars is None:
        ratings_store.clear(uid, current.id)
    else:
        ratings_store.record(uid, current.id, body.stars)
        context_store.record_event(
            {
                "pillar": "learning",
                "type": "rating",
                "subject_id": current.id,
                "subject_type": current.type,
                "persona": pid,
                "topics": current.topics + current.tags,
                "meta": {"stars": body.stars, "path": current.path},
            },
            uid=uid,
            # One footprint per rating, not one per revision of it.
            event_key=f"rating:{uid}:{current.id}",
        )
    return _with_progress([current], pid)[0]


@router.get("/my-learning", response_model=MyLearning)
def my_learning():
    _, items = _load()
    p = resolve_persona()
    enriched = _with_progress(items, p.id)
    mine = [
        i
        for i in enriched
        if p.id in i.personas or i.required or i.status != "not_started"
    ]
    coverage = {}
    for i in mine:
        for topic in set(i.topics):
            counts = coverage.setdefault(topic, [0, 0])
            counts[0] += i.status == "completed"
            counts[1] += 1
    return MyLearning(
        persona=p.id,
        persona_label=p.label,
        completed=sum(i.status == "completed" for i in mine),
        in_progress=sum(i.status == "in_progress" for i in mine),
        not_started=sum(i.status == "not_started" for i in mine),
        required_total=sum(i.required for i in mine),
        required_completed=sum(i.required and i.status == "completed" for i in mine),
        items=sorted(
            mine,
            key=lambda i: (
                {"in_progress": 0, "not_started": 1, "completed": 2}[i.status],
                i.title,
            ),
        ),
        coverage=[
            TopicCoverage(topic=t, completed=c[0], total=c[1])
            for t, c in sorted(coverage.items())
        ],
        proficiency_note=PROFICIENCY_NOTE,
    )


@router.get("/for-agent/{agent_id}", response_model=list[ItemWithProgress])
def for_agent(agent_id: str, persona: str | None = None):
    p = resolve_persona(persona)
    return _with_progress(recommend_for_agent(agent_id, p.id), p.id)


@router.get("/recommended", response_model=list[ItemWithProgress])
def recommended(persona: str | None = None):
    return [i for s in home(persona).sections if s.id == "role" for i in s.items]


def _search_pluralsight(text: str) -> ProviderResults:
    if not pluralsight.configured():
        return ProviderResults(
            provider="Pluralsight",
            state="sample",
            note="Pluralsight isn't connected yet, so only its courses in the hub's catalogue were searched.",
        )
    try:
        nodes = pluralsight.search(text) if text else []
    except http.ExternalError as e:
        reason = integrations.explain(e)
        integrations.record_error("pluralsight", None, reason)
        return ProviderResults(provider="Pluralsight", state="blocked", note=reason)
    integrations.clear_error("pluralsight", None)
    return ProviderResults(
        provider="Pluralsight",
        state="live",
        results=[
            ProviderResult(
                title=n["title"],
                url=pluralsight.launch_url(n["title"], "", n),
                excerpt=n.get("shortDescription") or "",
                level=n.get("level") or "",
                duration_seconds=int(n.get("courseSeconds") or 0),
            )
            for n in nodes
            if n and n.get("title")
        ],
    )


def _search_microsoft_learn(text: str) -> ProviderResults:
    try:
        found = mslearn.search(text) if text else []
    except http.ExternalError as e:
        reason = integrations.explain(e)
        integrations.record_error("microsoft_learn", None, reason)
        return ProviderResults(provider="Microsoft Learn", state="blocked", note=reason)
    integrations.clear_error("microsoft_learn", None)
    return ProviderResults(
        provider="Microsoft Learn",
        state="live",
        results=[ProviderResult(title=r.title, url=r.url, excerpt=r.excerpt, read_in_hub=True) for r in found],
    )


@router.get("/providers/search", response_model=list[ProviderResults])
def provider_search(q: str = ""):
    """The Learning search, beyond the hub's catalogue: Pluralsight's library
    (once it is connected) and Microsoft Learn, searched together. One provider
    failing never hides the other's results."""
    text = q.strip()[:200]
    if len(text) < 2:
        raise HTTPException(422, "Type at least two characters.")
    # The query leaves the bank, so client names and identifiers come out first.
    guard = guardrails.check(text, None)
    sendable = guardrails.for_retrieval(guard.masked, guard.names)
    with ThreadPoolExecutor(max_workers=2) as pool:
        ps = pool.submit(_search_pluralsight, sendable)
        ms = pool.submit(_search_microsoft_learn, sendable)
        return [ps.result(), ms.result()]


@router.get("/microsoft-learn/page", response_model=mslearn.LearnPage)
def microsoft_learn_page(url: str):
    """A Microsoft Learn module, path or unit, read in the hub."""
    if not mslearn.is_learn_url(url):
        raise HTTPException(422, "Only Microsoft Learn pages can be read in the hub.")
    try:
        page = mslearn.page(url)
    except http.ExternalError as e:
        integrations.record_error("microsoft_learn", None, integrations.explain(e))
        raise HTTPException(502, "Microsoft Learn didn't answer. Try again in a moment.") from None
    integrations.clear_error("microsoft_learn", None)
    context_store.record_event(
        {
            "pillar": "learning",
            "type": "learning_view",
            "subject_id": url,
            "subject_type": "microsoft_learn",
            "persona": _derived_persona_id(),
            "topics": [],
            "meta": {"source": "microsoft_learn", "kind": page.kind},
        }
    )
    return page


@router.get("/curation")
def curation(persona: str | None = None):
    p = resolve_persona(persona)
    _, items = _load()
    rows = [
        {
            "item_id": i.id,
            "title": i.title,
            "type": i.type,
            "path": i.path,
            "total": curation_score(i, p),
            "components": curation_breakdown(i, p),
        }
        for i in items
    ]
    return {
        "persona": p.id,
        "persona_label": p.label,
        "persona_paths": _persona_paths().get(p.id, []),
        "inputs": [
            "derived persona",
            "learning metadata",
            "authored path order",
            "prerequisites",
        ],
        "excluded": ["behavioral footprints are not used for ranking"],
        "proficiency": PROFICIENCY_NOTE,
        "ranked": sorted(rows, key=lambda r: -r["total"]),
    }
