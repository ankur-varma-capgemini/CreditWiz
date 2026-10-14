import time

from fastapi import APIRouter, HTTPException, Query

from ..context import store as context_store
from ..permissions import resolve_persona
from . import keyword, search, semantic
from .models import (
    Ack,
    Agent,
    Carousel,
    EventIn,
    FeedbackIn,
    MarketplaceHome,
    Persona,
    SearchRequest,
    SearchResponse,
)
from .store import store

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])

EXAMPLE_QUERIES = [
    "I need an agent that can review customer onboarding documents",
    "Screen a new customer against sanctions lists",
    "Summarise a supplier contract and flag unusual clauses",
    "Find assets for a charged-off account",
    "Draft an arrears reminder that follows conduct rules",
    "Review my pull request for security issues",
]

NEXT_STEPS = [
    {"label": "Browse all agents", "href": "/marketplace/agents"},
    {"label": "Learn how to build an agent", "href": "/learning?path=builders"},
    {"label": "Explore the learning catalog", "href": "/learning/catalog"},
]


def _build_carousels(persona: Persona | None) -> list[Carousel]:
    agents = store.agents
    out: list[Carousel] = []
    for c in store.carousels:
        if c.rule.type == "persona":
            items = search.recommend_for_persona(persona, agents)
        elif c.rule.type == "category":
            items = sorted(
                (a for a in agents if a.category == c.rule.value),
                key=lambda a: -a.popularity,
            )
        elif c.rule.type == "featured":
            items = sorted(
                (a for a in agents if a.featured or a.popularity >= 80),
                key=lambda a: -a.popularity,
            )
        else:  # recent
            items = sorted(agents, key=lambda a: a.updated_at, reverse=True)[:8]
        if items:
            out.append(
                Carousel(id=c.id, title=c.title, subtitle=c.subtitle, agents=items)
            )
    return out


def _derived_persona_id() -> str:
    from ..identity import (
        derive_persona,
        load_profile,
    )  # local import avoids a cycle at import time

    return derive_persona(load_profile()).id


@router.get("/home", response_model=MarketplaceHome)
def marketplace_home(
    persona: str | None = Query(default=None), domain: str | None = None
) -> MarketplaceHome:
    p = store.persona(resolve_persona(persona).id)
    carousels = _build_carousels(p)
    if domain:
        carousels = [
            c.model_copy(
                update={"agents": [a for a in c.agents if domain in a.business_domains]}
            )
            for c in carousels
        ]
        carousels = [c for c in carousels if c.agents]
    return MarketplaceHome(
        persona=p.id if p else "",
        personas=store.personas,
        domains=store.domains(),
        carousels=carousels,
        agent_count=len(store.agents),
        example_queries=EXAMPLE_QUERIES,
    )


@router.get("/curation")
def curation(persona: str | None = Query(default=None)) -> dict:
    """Why the 'Recommended for you' row is ordered the way it is.

    Returns the per-component curation score for every agent. Rule-based and
    explainable by design; no behavioural signals are involved.
    """
    p = store.persona(resolve_persona(persona).id)
    rows = []
    for a in store.agents:
        parts = search.curation_breakdown(a, p)
        rows.append(
            {
                "agent_id": a.id,
                "name": a.name,
                "total": round(sum(parts.values()), 2),
                "components": {k: round(v, 2) for k, v in parts.items()},
            }
        )
    rows.sort(key=lambda r: -r["total"])
    return {
        "persona": p.id if p else None,
        "persona_label": p.label if p else None,
        "weights": search.CURATION_WEIGHTS,
        "persona_boost": f"+{search.PERSONA_BOOST:.0%} of matched metadata when the owner names this persona",
        "inputs": ["derived persona", "agent metadata"],
        "excluded": [
            "behavioural footprints (collected, not used for ranking in the MVP)"
        ],
        "ranked": rows,
    }


@router.get("/personas", response_model=list[Persona])
def personas() -> list[Persona]:
    return store.personas


@router.get("/domains", response_model=list[str])
def domains() -> list[str]:
    return store.domains()


@router.get("/agents", response_model=list[Agent])
def list_agents(
    domain: str | None = None,
    category: str | None = None,
    persona: str | None = None,
    status: str | None = None,
) -> list[Agent]:
    items = store.agents
    if domain:
        items = [a for a in items if domain in a.business_domains]
    if category:
        items = [a for a in items if a.category == category]
    if persona:
        items = [a for a in items if persona in a.personas]
    if status:
        items = [a for a in items if a.status == status]
    return sorted(items, key=lambda a: a.name.lower())


@router.get("/agents/{agent_id}", response_model=Agent)
def get_agent(agent_id: str) -> Agent:
    agent = store.agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.get("/agents/{agent_id}/related", response_model=list[Agent])
def related_agents(agent_id: str) -> list[Agent]:
    agent = store.agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    def overlap(other: Agent) -> int:
        return (
            3 * (other.category == agent.category)
            + 2 * len(set(other.business_domains) & set(agent.business_domains))
            + len(set(other.capabilities) & set(agent.capabilities))
        )

    others = [a for a in store.agents if a.id != agent.id]
    return [a for a in sorted(others, key=lambda a: -overlap(a)) if overlap(a) > 0][:3]


@router.post("/search", response_model=SearchResponse)
def nlp_search(req: SearchRequest) -> SearchResponse:
    from ..identity import load_profile  # local import avoids a cycle

    started = time.perf_counter()
    agents = store.agents
    persona = store.persona(resolve_persona(req.persona).id)
    audience = load_profile().groups
    permitted = {agent.id for agent in agents}

    # The flow is: query -> embedding -> hybrid -> rerank -> context.
    #
    # No interpretation step ahead of retrieval. The query is embedded as
    # typed, so what you search for is what you asked for, and the same words
    # return the same agents every time. A model reads the request once, at the
    # rerank, where it judges candidates against it rather than rewriting it.
    #
    # `intent` below is the local lexicon and is used ONLY to explain results.
    # It costs a fraction of a millisecond, never calls a model, and never
    # touches what is retrieved or how anything is ordered.
    intent = search.local_intent(req.query)

    # Both indexes cover the whole catalogue, so both are told who is asking:
    # candidates come back already permitted rather than being retrieved
    # globally and dropped afterwards, which would let agents this user cannot
    # see occupy candidate slots. rank() still applies its own visibility drop
    # -- this is a recall fix, not the security boundary.
    #
    # The only other filter is a domain the user chose themselves from the
    # browse list. Nothing is inferred and then filtered on.
    chosen = [req.domain] if req.domain else []
    allowed = (
        {a.id for a in agents if req.domain in a.business_domains}
        if req.domain
        else permitted
    )

    if keyword.index.size == 0:
        keyword.index.sync(store.all_agents)

    embed_started = time.perf_counter()
    retrieved = (
        semantic.index.search(
            search.retrieval_text(req.query), groups=audience, domains=chosen
        )
        if semantic.index.available
        else None
    )
    embed_ms = round((time.perf_counter() - embed_started) * 1000)
    matched = keyword.index.search(
        search.keyword_text(req.query), allowed=allowed
    )
    results = search.rank(
        req.query, intent, agents, persona=persona, domain=req.domain,
        similar=retrieved, keywords=matched,
    )
    relaxed = False

    fused_order = [m.agent.id for m in results]
    rerank_started = time.perf_counter()
    results, reranker = search.rerank(req.query, results)
    engine = reranker
    rerank_ms = round((time.perf_counter() - rerank_started) * 1000)
    results = results[: len(fused_order)]
    # Trace enough to reconstruct why this ranking happened: how the request was
    # interpreted, what retrieval proposed, and what came out. Without the
    # candidates it is impossible to tell afterwards whether an agent was missed
    # because retrieval never proposed it or because the ranker dropped it.
    context_store.record_event(
        {
            "pillar": "marketplace",
            "type": "search",
            "query": req.query,
            "persona": persona.id if persona else req.persona,
            "topics": sorted(
                {d for m in results for d in m.agent.business_domains}
                | set(intent.domains)
            ),
            "meta": {
                "engine": engine,
                "results": [m.agent.id for m in results],
                "scores": {m.agent.id: m.score for m in results},
                "intent": {
                    "domains": intent.domains,
                    "capabilities": intent.capabilities,
                },
                "retrieval": {
                    "available": retrieved is not None,
                    "candidates": dict(
                        sorted((retrieved or {}).items(), key=lambda kv: -kv[1])[:5]
                    ),
                    # Separated out so a slow search can be attributed: model
                    # inference versus everything around it.
                    "embed_ms": embed_ms,
                },
                "keyword": {
                    "candidates": dict(
                        sorted(matched.items(), key=lambda kv: -kv[1])[:5]
                    ),
                },
                "fusion": "rrf",
                # The order fusion produced, before the reranker saw it. Without
                # both, a changed ordering cannot be attributed to either stage.
                "fused_order": fused_order,
                "rerank": {
                    "by": reranker,
                    "ms": rerank_ms,
                    "changed": fused_order != [m.agent.id for m in results],
                },
                "filters": {
                    "domains": intent.domains,
                    # True when the understood domains excluded everything and
                    # the search was retried without them.
                    "relaxed": relaxed,
                },
                "domain_filter": req.domain or None,
                "no_match": not results,
                "took_ms": round((time.perf_counter() - started) * 1000),
            },
        }
    )
    return SearchResponse(
        query=req.query,
        intent=intent,
        engine=engine,
        results=results,
        no_match=not results,
        next_steps=NEXT_STEPS if not results else [],
    )


@router.post("/events", response_model=Ack, deprecated=True)
def post_event(ev: EventIn) -> Ack:
    """Deprecated. Footprints are hub-wide: POST /api/context/events."""
    payload = ev.model_dump()
    payload.setdefault("pillar", "marketplace")
    payload["persona"] = _derived_persona_id()
    payload["subject_id"] = payload.pop("agent_id", None)
    payload["subject_type"] = "agent"
    return Ack(id=context_store.record_event(payload))


@router.post("/feedback", response_model=Ack, deprecated=True)
def post_feedback(fb: FeedbackIn) -> Ack:
    """Deprecated. Feedback is hub-wide: POST /api/context/feedback."""
    payload = fb.model_dump()
    payload.setdefault("pillar", "marketplace")
    payload["persona"] = _derived_persona_id()
    payload["subject_id"] = payload.pop("agent_id", None)
    return Ack(id=context_store.record_feedback(payload))


@router.get("/feedback/summary", deprecated=True)
def feedback_summary() -> dict:
    """Deprecated. Use GET /api/context/summary."""
    return context_store.summary()


@router.get("/metadata-template")
def metadata_template() -> dict:
    return store.metadata_template()


# ---------------------------------------------------------------- learning
#
# No documentation or architecture pages are served: an agent's documents are
# links to where each lives (Agent.documents), and Nexus keeps no copies.

from ..learning.models import ItemWithProgress
from ..learning.router import for_agent as learning_for_agent


@router.get(
    "/agents/{agent_id}/learning",
    response_model=list[ItemWithProgress],
    deprecated=True,
)
def agent_learning(agent_id: str) -> list[ItemWithProgress]:
    """Deprecated. Learning owns learning recommendations: GET /api/learning/for-agent/{agent_id}."""
    if store.agent(agent_id) is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return learning_for_agent(agent_id)
