"""The home assistant's API.

    POST /api/ask                              one question, answered across the hub
    POST /api/ask/stream                       the same, as server-sent events
    POST /api/ask/turns/{turn_id}/feedback     was the answer helpful
    POST /api/ask/turns/{turn_id}/selected     which recommendation they opened

The stream is event-driven progressive response: the page hears that the
request was understood, then the plan, then each pillar's result the moment
that pillar finishes, then the reply token by token, then the whole answer.
When the model has to plan, a first reading and its results come first,
marked provisional, within a fraction of a second.
The backend takes as long as it takes; the person starts reading within a
second or two. Posted, not an EventSource GET, so the question never travels
in a URL.
"""

from __future__ import annotations

import contextvars
import json
import logging
import queue
import threading
import uuid
from time import perf_counter
from typing import Iterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..permissions import resolve_persona
from . import llm, telemetry
from .graph import PILLAR_NODES, RECOMMENDED, graph
from .models import AskRequest, AskResponse, Plan, SubQuery, TurnFeedback, TurnSelection

log = logging.getLogger(__name__)

router = APIRouter(tags=["hub"])


def _inputs(req: AskRequest, persona) -> dict:
    return {
        "request": req,
        "persona": persona,
        "original_query": req.q,
        "session_id": req.session or uuid.uuid4().hex,
        "started": perf_counter(),
        "errors": [],
        "timings": {},
    }


def _response(req: AskRequest, s: dict, took: int) -> AskResponse:
    gate = s["conversation"]
    if gate.kind != "task":
        # Small talk: answered by the conversation gate, nothing planned or recorded.
        return AskResponse(
            kind=gate.kind,
            turn_id=None,
            session_id=s["session_id"],
            query=req.q,
            user=s["user_context"],
            capabilities=s["capabilities"],
            reply=s["final_response"],
            reply_source=s.get("reply_source", "rules"),
            follow_ups=s["follow_ups"],
            took_ms=took,
        )
    if s.get("errors"):
        # Which pillars failed and how; never the request.
        log.warning("hub answered with pillar errors: %s", ", ".join(s["errors"]))

    plan, g, guard = s["plan"], s["gate"], s["guard"]
    results = s.get("pillar_results", {})
    used_model = plan.source == "claude" or s["reply_source"] == "claude"
    return AskResponse(
        kind="task",
        turn_id=s["turn_id"],
        session_id=s["session_id"],
        query=req.q,
        user=s["user_context"],
        task=s["task_context"],
        plan=Plan(
            opening=gate.opening,
            sanitized_query=s["sanitized_query"],
            model_access=guard.model_access,
            subqueries=[
                SubQuery(pillar=p, query=g.subqueries[p], reformulated=p in g.reformulated)
                for p in s["selected_pillars"]
            ],
            selected_pillars=s["selected_pillars"],
            plan_source=plan.source,
            plan_reason=plan.reason,
            reply_source=s["reply_source"],
            reply_reason=s["reply_reason"],
            governance=g.notes,
            timings_ms={**s["timings"], "total": took},
            model=llm.model() if used_model else "",
            follows_on=s["reading"].topic,
        ),
        recommended=s["toolkit"][:RECOMMENDED],
        pillars=[results[p] for p in s["selected_pillars"] if p in results],
        draft=s.get("draft"),
        capabilities=s.get("capabilities") or [],
        reply=s["final_response"],
        reply_source=s["reply_source"],
        follow_ups=s["follow_ups"],
        took_ms=took,
    )


@router.post("/api/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    # Persona preview is checked here, at the edge, before anything runs.
    persona = resolve_persona(req.persona)
    inputs = _inputs(req, persona)
    s = graph.invoke(inputs)
    return _response(req, s, round((perf_counter() - inputs["started"]) * 1000))


# ------------------------------------------------------------------ stream


def _events(node: str, update: dict) -> list[dict]:
    """What the page hears when a node finishes."""
    if node == "understand":
        p = update["plan"]
        return [{"type": "task_understood", "intents": p.intents, "planned_by": p.source, "reason": p.reason}]
    if node == "governance":
        g = update["gate"]
        return [
            {
                "type": "plan_ready",
                "task": update["task_context"].model_dump(mode="json"),
                "pillars": update["selected_pillars"],
                "subqueries": [{"pillar": p, "query": g.subqueries[p]} for p in update["selected_pillars"]],
                "governance": g.notes,
            }
        ]
    # The job's toolkit is sent by synthesize, once the agents have searched.
    if node in PILLAR_NODES:
        return [{"type": "pillar_result", "group": update["pillar_results"][node].model_dump(mode="json")}]
    if node == "respond":
        return [
            {
                "type": "response",
                "reply": update["final_response"],
                "reply_source": update["reply_source"],
                "draft": None,
                "follow_ups": [f.model_dump(mode="json") for f in update["follow_ups"]],
            }
        ]
    if node == "synthesize":
        return [
            {
                "type": "response",
                "reply": update["final_response"],
                "reply_source": update["reply_source"],
                "draft": update["draft"].model_dump(mode="json") if update.get("draft") else None,
                "follow_ups": [f.model_dump(mode="json") for f in update["follow_ups"]],
            }
        ]
    return []


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/api/ask/stream")
def ask_stream(req: AskRequest) -> StreamingResponse:
    persona = resolve_persona(req.persona)
    inputs = _inputs(req, persona)
    events: queue.Queue[dict | None] = queue.Queue()

    def run() -> None:
        final: dict | None = None
        try:
            for mode, chunk in graph.stream(inputs, stream_mode=["updates", "custom", "values"]):
                if mode == "values":
                    final = chunk
                elif mode == "custom":
                    events.put(chunk)
                else:
                    for node, update in chunk.items():
                        for event in _events(node, update or {}):
                            events.put(event)
            took = round((perf_counter() - inputs["started"]) * 1000)
            events.put({"type": "complete", "response": _response(req, final, took).model_dump(mode="json")})
        except Exception as exc:  # noqa: BLE001 - the page is told; the request is never logged
            log.warning("hub stream failed: %s", type(exc).__name__)
            events.put({"type": "error", "message": "The hub could not answer just now. Try again."})
        finally:
            events.put(None)

    # The graph runs in a thread of its own, carrying this request's context
    # (who is signed in), because the response streams on after this returns.
    context = contextvars.copy_context()
    threading.Thread(target=context.run, args=(run,), daemon=True).start()

    def stream() -> Iterator[str]:
        yield _sse({"type": "accepted", "session_id": inputs["session_id"]})
        while (event := events.get()) is not None:
            yield _sse(event)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --------------------------------------------------------------- feedback


@router.post("/api/ask/turns/{turn_id}/feedback")
def turn_feedback(turn_id: str, body: TurnFeedback) -> dict:
    if not telemetry.feedback(turn_id, body.helpful):
        raise HTTPException(404, "Answer not found")
    return {"ok": True}


@router.post("/api/ask/turns/{turn_id}/selected")
def turn_selected(turn_id: str, body: TurnSelection) -> dict:
    if not telemetry.selected(turn_id, body.ref):
        raise HTTPException(404, "Recommendation not found on that answer")
    return {"ok": True}
