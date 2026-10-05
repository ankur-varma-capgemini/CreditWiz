"""The home assistant as a LangGraph graph.

    START -> user_context -> conversation
               |-- greeting | small talk | thanks | goodbye | help -> respond -> END
               '-- task -> follow_up -> guardrails -> understand
                       |-- the model reads it as conversation -> respond -> END
                       '-- governance -> route
                       -> prompts | marketplace | learning | community   fan-out (Send)
                       -> synthesize                                      fan-in
                       -> save -> END

Conversation never reaches a pillar or the planner: respond answers it
directly, naturally where the data policy lets the model see it, and in a
fixed line where it does not.

A follow-up ("is there a quick reference for it?") is read with the topic of
the conversation's earlier request before anything else runs (followup.py), so
the privacy check, the plan, every search and the usage log see the request as
it was meant.

The model plans every task, judges each agent's shortlist and writes the
reply. While it reads the request, the rules' reading of the intents streams
at once. Nothing is searched until the model's plan says where, so the page
never shows results that are about to be replaced.

The pillars run in parallel in one superstep and their results merge through
the `pillar_results` reducer, so synthesize runs once, when all have returned.
Streamed (router.py), each pillar's result reaches the page the moment that
pillar finishes, and the reply token by token as the model writes it.

Every node records its own time; "pillars (parallel)" is the wall-clock time
of the whole fan-out, which is the slowest pillar, not the sum of them.

No checkpointer: the state, which holds the words as typed, is never
persisted, and tracing to LangSmith is switched off for the same reason.
"""

from __future__ import annotations

import logging
import operator
import os
import uuid
from dataclasses import replace
from time import perf_counter
from typing import Annotated, Any, Callable, TypedDict

# The state carries the request as typed, client name included. It must not
# leave the process, so LangSmith tracing is off whatever the environment says.
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

from langgraph.config import get_stream_writer  # noqa: E402
from langgraph.graph import END, START, StateGraph  # noqa: E402
from langgraph.types import Send  # noqa: E402

from ..context.models import UserContext  # noqa: E402
from ..context.user import build_user_context  # noqa: E402
from ..journeys import task  # noqa: E402
from ..journeys.models import AssetCard, FollowUp, Journey, TaskContext  # noqa: E402
from ..journeys.reply import follow_ups  # noqa: E402
from ..journeys.router import summary  # noqa: E402
from ..journeys.store import CardBuilder  # noqa: E402
from ..journeys.store import store as journey_store  # noqa: E402
from ..prompts.draft import goal_of, is_authoring  # noqa: E402
from ..prompts.models import Draft  # noqa: E402
from . import conversation, followup, governance, guardrails, pillars, planner, synthesis, telemetry  # noqa: E402
from .models import AskRequest, Capability, PillarGroup  # noqa: E402

log = logging.getLogger(__name__)

RECOMMENDED = 6


def _merge(a: dict | None, b: dict | None) -> dict:
    return {**(a or {}), **(b or {})}


class HubState(TypedDict, total=False):
    # The design's state.
    original_query: str
    sanitized_query: str
    user_context: UserContext
    task_context: TaskContext
    selected_pillars: list[str]
    subqueries: dict[str, str]
    pillar_results: Annotated[dict[str, PillarGroup], _merge]
    final_response: str
    errors: Annotated[list[str], operator.add]
    # What the nodes pass along to explain and assemble the answer.
    request: AskRequest
    persona: Any
    session_id: str
    journeys: list[Journey]
    # The persona's example requests, offered as suggestions.
    examples: list[str]
    conversation: conversation.Gate
    # The request read with the conversation it continues.
    reading: followup.Reading
    capabilities: list[Capability]
    guard: guardrails.Guard
    entitlements: guardrails.Entitlements
    plan: planner.PlanDraft
    gate: governance.Gate
    toolkit: list[AssetCard]
    draft: Draft | None
    reply_source: str
    reply_reason: str
    follow_ups: list[FollowUp]
    timings: Annotated[dict[str, int], _merge]
    started: float
    fanned_out: float
    turn_id: str


def _timed(name: str, fn: Callable[[HubState], dict]) -> Callable[[HubState], dict]:
    def node(state: HubState) -> dict:
        t = perf_counter()
        out = fn(state)
        out["timings"] = {**out.get("timings", {}), name: round((perf_counter() - t) * 1000)}
        return out

    return node


def _writer() -> Callable[[dict], None]:
    """Hands events to a streaming caller; drops them when nobody streams."""
    try:
        return get_stream_writer()
    except RuntimeError:
        return lambda event: None


# -------------------------------------------------------------------- nodes


def user_context(state: HubState) -> dict:
    p = state["persona"]
    found = journey_store.for_persona(p.id)
    return {
        "user_context": build_user_context(p),
        "journeys": found.journeys if found else [],
        "examples": found.examples if found else [],
    }


def conversation_gate(state: HubState) -> dict:
    return {"conversation": conversation.read(state["original_query"])}


def entry_router(state: HubState) -> str:
    """Only a task goes on; small talk is answered where it stands."""
    return "follow_up" if state["conversation"].kind == "task" else "respond"


def follow_up(state: HubState) -> dict:
    """A follow-up with no topic of its own, read with the earlier request's."""
    return {"reading": followup.read(state["conversation"].task_query, state["request"].history)}


def after_understanding(state: HubState) -> str:
    """The model can read a message the rules took for a task as conversation."""
    return "respond" if state["plan"].small_talk else "governance"


def _earlier_job(state: HubState) -> str | None:
    earlier = state["request"].journey
    return next((j.title for j in state["journeys"] if j.id == earlier), None)


def respond(state: HubState) -> dict:
    """Conversation, answered directly: naturally by the model where the data
    policy allows, in a fixed line where it does not. No search runs."""
    gate = state["conversation"]
    if state.get("plan") is not None and state["plan"].small_talk:
        gate = replace(gate, kind="small_talk", task_query="", topic="")
    user = state["user_context"]
    first = user.display_name.split()[0] if user.display_name else ""
    text, suggestions, capabilities = conversation.answer(gate, first_name=first, examples=state["examples"])

    # The same policy as any request decides what the model may see.
    guard = state.get("guard") or guardrails.check(state["original_query"], None)
    source = "rules"
    if guard.model_view is not None:
        emit = _writer()
        said = conversation.natural(
            gate.kind,
            guard.model_view,
            first,
            user.persona_label,
            _earlier_job(state),
            # A reply with a client's placeholder in it is sent whole, once restored.
            on_delta=None if guard.model_view != state["original_query"] else (
                lambda delta: emit({"type": "response_delta", "delta": delta})
            ),
        )
        if said is not None:
            if guard.subject is not None and guard.model_access == "masked":
                said = said.replace(f"[{guard.subject.kind.upper()}]", guard.subject.name)
            text, source = said, "claude"
    return {
        "conversation": gate,
        "final_response": text,
        "reply_source": source,
        "follow_ups": suggestions,
        "capabilities": capabilities,
    }


def guardrails_check(state: HubState) -> dict:
    # The request without the greeting in front of it, read with the conversation.
    guard = guardrails.check(state["reading"].text, state["request"].subject)
    return {"guard": guard, "sanitized_query": guard.masked, "entitlements": guardrails.entitlements()}


def _history_view(state: HubState) -> tuple[str, ...]:
    """The earlier requests as the data policy lets the model see each one:
    the same check every request gets, and none that the policy keeps from it."""
    subject = state["request"].subject
    views = (guardrails.check(h, subject).model_view for h in state["reading"].earlier)
    return tuple(v for v in views if v is not None)


def understand(state: HubState) -> dict:
    """The model plans every task. While it reads the request, the rules'
    reading of the intents streams at once."""
    p, guard, reading = state["persona"], state["guard"], state["reading"]
    journeys, earlier = state["journeys"], state["request"].journey
    first = planner.first_reading(guard.masked, guard.model_view, journeys, earlier, reading.follows_up)
    if first is not None:
        _writer()(
            {"type": "task_understood", "intents": first.intents, "planned_by": "rules", "reason": first.reason, "provisional": True}
        )
    history = _history_view(state) if reading.follows_up and guard.model_view is not None else ()
    return {"plan": planner.plan(guard.masked, guard.model_view, p.label, journeys, earlier, reading.follows_up, history)}


def govern(state: HubState) -> dict:
    plan, guard, ents = state["plan"], state["guard"], state["entitlements"]
    g = governance.gate(plan, guard, state["journeys"], state["request"].journey, ents.withheld_prompts)
    user = state["user_context"]
    cards = CardBuilder() if g.journey else None
    task_context = TaskContext(
        intent=plan.intents[0],
        intents=plan.intents,
        intent_cue=plan.cue,
        objective=g.journey.objective if g.journey else plan.objective,
        activity=summary(g.journey, cards) if g.journey else None,
        carried_over=g.carried_over,
        subject=guard.subject,
        subject_carried_over=guard.subject_carried_over,
        needs=g.journey.needs if g.journey else plan.needs,
        sensitivity=g.sensitivity,
        sensitivity_reason=g.sensitivity_reason,
        loggable_query="[confidential request]" if g.sensitivity == "confidential" else guard.loggable,
        ordering=task.ordering_note(user.maturity) if g.journey else "",
    )
    return {
        "gate": g,
        "task_context": task_context,
        "selected_pillars": g.pillars,
        "subqueries": g.subqueries,
    }


# The kind of card each pillar answers with. Systems, data products and use
# cases belong to no pillar: they come with finding, unless the request named
# the kind of thing it wants.
_PILLAR_KINDS: dict[str, set[str]] = {
    "prompts": {"prompt"},
    "marketplace": {"agent"},
    "learning": {"learning"},
    "community": {"expert", "community"},
}
_PILLAR_KIND = set().union(*_PILLAR_KINDS.values())


def _toolkit(g: governance.Gate, plan: planner.PlanDraft, maturity: str) -> list[AssetCard]:
    """The job's own toolkit, cut to what was asked for, then ordered for the
    intents and the person's maturity. Asking for an agent brings the job's
    agents, not its courses and experts too."""
    if g.journey is None:
        return []
    intents = plan.intents
    asked = set().union(*(_PILLAR_KINDS[p] for p in g.pillars))

    def wanted(card: AssetCard) -> bool:
        if card.kind in _PILLAR_KIND:
            return card.kind in asked
        return card.intent in intents and not plan.narrowed

    toolkit = [c for c in CardBuilder().cards(g.journey.assets) if wanted(c)]
    toolkit.sort(
        key=lambda c: (
            intents.index(c.intent) if c.intent in intents else len(intents),
            task.maturity_rank(maturity, c.intent),
        )
    )
    return toolkit


def route(state: HubState) -> dict:
    """The job's toolkit; the pillars to fan out to are the gate's."""
    toolkit = _toolkit(state["gate"], state["plan"], state["user_context"].maturity)
    return {"toolkit": toolkit, "fanned_out": perf_counter()}


def fan_out(state: HubState) -> list[Send] | str:
    return [Send(p, state) for p in state["selected_pillars"]] or "synthesize"


def _pillar(name: str, search: Callable[[HubState, list[str]], pillars.Run]) -> Callable[[HubState], dict]:
    def node(state: HubState) -> dict:
        t = perf_counter()
        g = state["gate"]
        subquery = g.subqueries[name]
        try:
            run = search(state, pillars._queries(g.retrieval_query, subquery))
            errors: list[str] = []
        except Exception as exc:  # noqa: BLE001 - one pillar failing costs its own group only
            log.warning("hub pillar %s failed: %s", name, type(exc).__name__)
            run, errors = pillars.Run(), [f"{name}: {type(exc).__name__}"]
        ms = round((perf_counter() - t) * 1000)
        return {
            "pillar_results": {name: pillars.group(name, subquery, run, ms)},
            "timings": {f"pillar {name}": ms},
            "errors": errors,
        }

    return node


def _rerank_query(state: HubState) -> str | None:
    """What a pillar's agent may give the model to judge its shortlist with:
    the request as the data policy lets the model read it, whole, since a
    pillar's search words alone ("credit memo") say less about fit than the
    sentence they came from."""
    return state["guard"].model_view


def _prompts(state: HubState, queries: list[str]) -> pillars.Run:
    return pillars.prompts(queries, state["entitlements"], state["toolkit"], _rerank_query(state))


def _marketplace(state: HubState, queries: list[str]) -> pillars.Run:
    return pillars.marketplace(
        queries,
        state["entitlements"],
        state["persona"].id,
        state["gate"].journey,
        state["toolkit"],
        _rerank_query(state),
    )


def _learning(state: HubState, queries: list[str]) -> pillars.Run:
    return pillars.learning(queries, state["entitlements"], state["persona"].id, state["toolkit"], _rerank_query(state))


def _community(state: HubState, queries: list[str]) -> pillars.Run:
    return pillars.community(queries, state["entitlements"], state["gate"].journey, state["toolkit"])


def synthesize(state: HubState) -> dict:
    fan_in = round((perf_counter() - state["fanned_out"]) * 1000)
    plan, guard, g = state["plan"], state["guard"], state["gate"]
    # The job's own toolkit is shown now, once the agents have searched and
    # beside the reply written from both. It comes from the job map, not a
    # search, so sent when the plan chose the job it appeared seconds before
    # anything had been found.
    if state["toolkit"]:
        _writer()({"type": "toolkit", "recommended": [c.model_dump(mode="json") for c in state["toolkit"][:RECOMMENDED]]})
    results = state.get("pillar_results", {})
    groups = [results[p] for p in state["selected_pillars"] if p in results]
    capabilities: list[Capability] = []
    if not state["toolkit"] and not any(gr.hits for gr in groups) and not plan.cue and g.journey is None:
        # Nothing matched, and the words named no intent or job: whatever it
        # was, say what the hub can do rather than leave a dead end.
        why = "Nothing in the hub matched and the request named no task, so the reply says what the hub can do."
        capabilities = conversation.capabilities(state["examples"])
        text, source = conversation.NOT_FOUND, "rules"
        if g.reply_view is not None:
            emit = _writer()
            user = state["user_context"]
            said = conversation.natural(
                "not_found",
                g.reply_view,
                user.display_name.split()[0] if user.display_name else "",
                user.persona_label,
                _earlier_job(state),
                on_delta=None if guard.subject else (lambda delta: emit({"type": "response_delta", "delta": delta})),
            )
            if said is not None:
                if guard.subject is not None and g.reply_access == "masked":
                    said = said.replace(f"[{guard.subject.kind.upper()}]", guard.subject.name)
                text, source = said, "claude"
    else:
        emit = _writer()
        text, source, why = synthesis.reply(
            model_view=g.reply_view,
            restore=guard.subject if g.reply_access == "masked" else None,
            intents=plan.intents,
            journey=g.journey,
            toolkit=state["toolkit"],
            groups=groups,
            searched=state["selected_pillars"],
            on_delta=lambda delta: emit({"type": "response_delta", "delta": delta}),
        )
    # A prompt written for them, when they asked for one to be written.
    draft = None
    if "contribute" in plan.intents and is_authoring(state["conversation"].task_query):
        user = state["user_context"]
        draft = pillars.draft_for(goal_of(guard.masked), state["entitlements"], user.job_title, user.department)
    return {
        "final_response": text,
        "reply_source": source,
        "reply_reason": why,
        "draft": draft,
        "capabilities": capabilities,
        # Offered from the job's whole toolkit: the reasons they did not ask
        # about are exactly what the answer left out.
        "follow_ups": follow_ups(plan.intents, g.journey, CardBuilder().cards(g.journey.assets) if g.journey else []),
        "timings": {"pillars (parallel)": fan_in},
    }


def save(state: HubState) -> dict:
    turn_id = uuid.uuid4().hex
    results = state.get("pillar_results", {})
    shown = [c.ref for c in state["toolkit"][:RECOMMENDED]] + [
        h.ref for p in state["selected_pillars"] if p in results for h in results[p].hits
    ]
    telemetry.save(
        turn_id=turn_id,
        session_id=state["session_id"],
        intents=list(state["plan"].intents),
        activity=state["gate"].journey.id if state["gate"].journey else None,
        pillars=list(state["selected_pillars"]),
        recommended=shown,
        sensitivity=state["task_context"].sensitivity,
        plan_source=state["plan"].source,
        reply_source=state["reply_source"],
        latency_ms=round((perf_counter() - state["started"]) * 1000),
    )
    return {"turn_id": turn_id}


# -------------------------------------------------------------------- graph

PILLAR_NODES: dict[str, Callable[[HubState, list[str]], pillars.Run]] = {
    "prompts": _prompts,
    "marketplace": _marketplace,
    "learning": _learning,
    "community": _community,
}


def build():
    g = StateGraph(HubState)
    g.add_node("user_context", _timed("user_context", user_context))
    g.add_node("conversation", _timed("conversation", conversation_gate))
    g.add_node("respond", _timed("respond", respond))
    g.add_node("follow_up", _timed("follow_up", follow_up))
    g.add_node("guardrails", _timed("guardrails", guardrails_check))
    g.add_node("understand", _timed("understand", understand))
    g.add_node("governance", _timed("governance", govern))
    g.add_node("route", _timed("route", route))
    for name, search in PILLAR_NODES.items():
        g.add_node(name, _pillar(name, search))
    g.add_node("synthesize", _timed("synthesize", synthesize))
    g.add_node("save", _timed("save", save))

    g.add_edge(START, "user_context")
    g.add_edge("user_context", "conversation")
    g.add_conditional_edges("conversation", entry_router, ["respond", "follow_up"])
    g.add_edge("respond", END)
    g.add_edge("follow_up", "guardrails")
    g.add_edge("guardrails", "understand")
    g.add_conditional_edges("understand", after_understanding, ["respond", "governance"])
    g.add_edge("governance", "route")
    g.add_conditional_edges("route", fan_out, [*PILLAR_NODES, "synthesize"])
    for name in PILLAR_NODES:
        g.add_edge(name, "synthesize")
    g.add_edge("synthesize", "save")
    g.add_edge("save", END)
    return g.compile()


graph = build()
