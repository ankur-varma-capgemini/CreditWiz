"""What people contribute through Create, and where each goes to be found.

    Create -> POST /api/contributions -> contributions table   the record
                                      -> ingest()              its agent's index
                                            prompt, agent proposal -> Prompts & Skills
                                            skill video            -> Learning

The table is the record of truth. An index holds a derived copy, one text
embedded, which reindex() rebuilds from the table at boot. Who may find a
contribution is read from the table on every search, never from an index:

    its author     always, from the moment it is submitted
    anyone else    once approved, within the audience fixed at submission
                   team        the author's desk
                   department  the author's department
                   everyone    everyone signed in to Nexus

A prompt's audience is the scope its author chose, except that High risk
keeps it to their desk: the library's own rule for High. Returned work leaves
the index; its author still sees it in My library.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Literal

from .. import database
from ..auth import user_id
from ..identity import load_profile
from ..retrieval.agent import Candidate, explain
from ..retrieval.index import Doc
from ..retrieval.models import AgentHit
from .models import Risk, Submission
from .store import store

Audience = Literal["team", "department", "everyone"]
Destination = Literal["prompts", "learning"]

# Which agent's index each kind goes to. Discover's catalogue is its own and
# stays untouched, so an agent proposal -- a chain of the library's prompts --
# is found by the Prompts & Skills agent while Model Risk reviews it.
DESTINATION: dict[str, Destination] = {"prompt": "prompts", "agent": "prompts", "video": "learning"}
KINDS: dict[Destination, tuple[str, ...]] = {"prompts": ("prompt", "agent"), "learning": ("video",)}
_NAME = {"prompt": "prompt", "agent": "agent proposal", "video": "skill video"}
_HIT_KIND = {"prompt": "prompt", "agent": "agent", "video": "learning"}
_STATUS = {"in_review": "In review", "live": "Approved"}


@dataclass(frozen=True)
class Viewer:
    """Who is asking, with the desk and department an audience is matched on."""

    id: str
    desk: str
    department: str


def viewer() -> Viewer:
    profile = load_profile()
    desk = store.desk_for(profile.job_title)
    return Viewer(user_id(), desk.id if desk else "", profile.department)


def audience_of(body: Submission, risk: Risk | None) -> Audience:
    if body.kind != "prompt":
        return "everyone"
    if risk == "High" or body.scope == "team":
        return "team"
    return "department" if body.scope == "dept" else "everyone"


def doc_id(contribution_id: str) -> str:
    return f"contribution:{contribution_id}"


def _payload(row: sqlite3.Row) -> dict:
    return json.loads(row["payload"])


def text(row: sqlite3.Row) -> str:
    """What its index embeds: the same fields a catalogue record gives."""
    p = _payload(row)
    parts = [f"{row['title']}.", p.get("description", "")]
    if row["kind"] == "prompt":
        parts.append(f"Category: {p['category']}.")
        if p.get("tags"):
            parts.append("Tags: " + ", ".join(p["tags"]) + ".")
        if p.get("inputs"):
            parts.append("Inputs: " + ", ".join(p["inputs"]) + ".")
    elif row["kind"] == "agent":
        steps = [s for s in (store.prompt(i) for i in p.get("chain", [])) if s]
        parts.append("Chains the prompts: " + "; ".join(s.title for s in steps) + ".")
    return " ".join(part.strip() for part in parts if part and part.strip())


def doc(row: sqlite3.Row) -> Doc:
    return Doc(doc_id(row["id"]), text(row), "contribution", row["user_id"])


def _agent(destination: Destination):
    if destination == "prompts":
        from .agent import agent
    else:
        from ..learning.agent import agent
    return agent


def ingest(row: sqlite3.Row) -> bool:
    """Put one contribution where it will be found: embedded into its
    destination agent's index. True when its vector was stored."""
    return _agent(DESTINATION[row["kind"]]).add(doc(row))


def retire(row: sqlite3.Row) -> None:
    """Take one out of its index: returned work is offered to no one."""
    _agent(DESTINATION[row["kind"]]).remove(doc_id(row["id"]), "contribution")


def reindex() -> dict[str, dict[str, int] | None]:
    """Each agent's contributions, rebuilt from the table. Run at boot."""
    with database.connect() as conn:
        rows = conn.execute("SELECT * FROM contributions WHERE status != 'returned'").fetchall()
    return {
        destination: _agent(destination).sync(
            "contribution", [doc(r) for r in rows if DESTINATION[r["kind"]] == destination]
        )
        for destination in KINDS
    }


def _in_audience(row: sqlite3.Row, who: Viewer) -> bool:
    if row["audience"] == "everyone":
        return True
    if row["audience"] == "department":
        return bool(row["department"]) and row["department"] == who.department
    return bool(row["desk"]) and row["desk"] == who.desk


def findable(destination: Destination, who: Viewer) -> dict[str, sqlite3.Row]:
    """The contributions this person may find through one agent, by index id."""
    kinds = KINDS[destination]
    with database.connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM contributions WHERE kind IN ({','.join('?' * len(kinds))}) "
            "AND status != 'returned' AND (user_id = ? OR status = 'live')",
            (*kinds, who.id),
        ).fetchall()
    return {doc_id(r["id"]): r for r in rows if r["user_id"] == who.id or _in_audience(r, who)}


def describe(row: sqlite3.Row) -> str:
    """How a contribution reads to the reranker."""
    return f"{row['title']}. {_payload(row).get('description', '')} (a {_NAME[row['kind']]} a colleague contributed)"


def hit(row: sqlite3.Row, who: Viewer, c: Candidate, queries: list[str]) -> AgentHit:
    """A contribution as a result. Its author opens it in My library; anyone
    else sees it listed, with where it lives not yet confirmed."""
    own = row["user_id"] == who.id
    name = _NAME[row["kind"]]
    p = _payload(row)
    return AgentHit(
        ref=doc_id(row["id"]),
        kind=_HIT_KIND[row["kind"]],
        title=row["title"],
        summary=p.get("description") or f"A {name} contributed through Create.",
        href="/library/mine" if own else "",
        why=explain(c, [p.get("category", ""), *p.get("tags", [])], queries),
        meta=f"{'Your' if own else 'Contributed'} {name} · {_STATUS[row['status']]}",
        fit=c.fit,
        score=c.score,
        similarity=c.similarity,
        keyword=c.keyword,
    )
