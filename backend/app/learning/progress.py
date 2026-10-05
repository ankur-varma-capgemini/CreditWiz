"""Monotonic per-user learning state and exactly-once completion events in SQL."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from .. import database

Status = Literal["not_started", "in_progress", "completed"]
_ORDER = {"not_started": 0, "in_progress": 1, "completed": 2}

# Demo accounts start part-way through one Pluralsight course, so "Continue
# learning" has something to show before Pluralsight is connected. Once it is,
# the percentage comes from Pluralsight's own record of what was watched.
DEMO_PROGRESS = (
    ("demo-compliance", "model-risk-management-essentials", 42),
    ("demo-risk", "model-risk-management-essentials", 60),
    ("demo-credit", "financial-statement-analysis-deep-dive", 35),
    ("demo-rm", "negotiation-skills-for-deal-teams", 20),
)


def seed_demo(conn) -> None:
    """Only rows a demo account does not have yet, so what they did since stays."""
    now = datetime.now(UTC).isoformat(timespec="milliseconds")
    conn.executemany(
        "INSERT OR IGNORE INTO learning_progress VALUES (?,?,'in_progress',?,?,NULL,?)",
        [(uid, item_id, pct, now, now) for uid, item_id, pct in DEMO_PROGRESS],
    )


def all_for(user_id: str) -> dict[str, dict]:
    with database.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM learning_progress WHERE user_id=?", (user_id,)
        ).fetchall()
    return {r["item_id"]: dict(r) for r in rows}


def record(
    user_id: str,
    item_id: str,
    status: Status,
    progress: int | None = None,
    completion_event: dict | None = None,
) -> dict:
    now = datetime.now(UTC).isoformat(timespec="milliseconds")
    pct = 100 if status == "completed" else min(99, max(0, progress or 0))
    # BEGIN IMMEDIATE serializes read/modify/write across threads AND processes.
    with database.connect(write=True) as conn:
        existing = conn.execute(
            "SELECT * FROM learning_progress WHERE user_id=? AND item_id=?",
            (user_id, item_id),
        ).fetchone()
        previous = existing["status"] if existing else "not_started"
        next_status = max((previous, status), key=_ORDER.__getitem__)
        next_pct = (
            100
            if next_status == "completed"
            else max(existing["progress"] if existing else 0, pct)
        )
        started = (existing["started_at"] if existing else None) or (
            now if next_status != "not_started" else None
        )
        completed = (existing["completed_at"] if existing else None) or (
            now if next_status == "completed" else None
        )
        conn.execute(
            "INSERT INTO learning_progress VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(user_id,item_id) DO UPDATE SET status=excluded.status,progress=excluded.progress,"
            "started_at=excluded.started_at,completed_at=excluded.completed_at,updated_at=excluded.updated_at",
            (user_id, item_id, next_status, next_pct, started, completed, now),
        )
        if next_status == "completed" and previous != "completed" and completion_event:
            from ..context.store import record_event

            record_event(
                completion_event,
                conn=conn,
                uid=user_id,
                event_key=f"completion:{user_id}:{item_id}",
            )
        row = conn.execute(
            "SELECT * FROM learning_progress WHERE user_id=? AND item_id=?",
            (user_id, item_id),
        ).fetchone()
    return dict(row)
