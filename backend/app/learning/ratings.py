"""Learner star ratings for learning items.

Two averages, on purpose:

`rating_average` is the plain mean, and it is withheld entirely until an item has
`MIN_SHOWN` ratings. On a catalogue this size a mean over one or two votes is
noise presented as fact, and "5.0" from a single rating reads as authoritative.

`rating_weighted` is that mean shrunk toward the catalogue mean. Nothing displays
it today. It exists because it is the value a rating-aware ranker must sort on:
without shrinkage a lone 5.0 outranks a 4.6 earned over forty ratings. Ranking
still ignores ratings entirely -- see learning/router.curation_breakdown.
"""

from __future__ import annotations

from datetime import UTC, datetime

from .. import database

# Below this many ratings we say so rather than showing a number.
MIN_SHOWN = 3
# Shrinkage strength: how many "catalogue average" votes every item starts with.
PRIOR_WEIGHT = 5.0
# The catalogue mean is itself shrunk toward the midpoint, because early on the
# catalogue is a handful of votes. Without this, the first rating in Nexus is
# the catalogue mean, shrinking it toward itself is a no-op, and a lone 5 lands
# at exactly 5.0 -- the thing the weighting exists to prevent.
CATALOG_PRIOR = 10.0
NEUTRAL = 3.0


def empty() -> dict:
    return {
        "rating_count": 0,
        "rating_average": None,
        "rating_weighted": None,
        "my_rating": None,
    }


def summaries(user_id: str) -> dict[str, dict]:
    """Aggregate every item's ratings, plus this user's own, in one round trip."""
    with database.connect() as conn:
        totals = conn.execute(
            "SELECT item_id, COUNT(*) AS n, SUM(stars) AS s "
            "FROM learning_ratings GROUP BY item_id"
        ).fetchall()
        mine = conn.execute(
            "SELECT item_id, stars FROM learning_ratings WHERE user_id=?", (user_id,)
        ).fetchall()

    votes = sum(r["n"] for r in totals)
    catalog_mean = (CATALOG_PRIOR * NEUTRAL + sum(r["s"] for r in totals)) / (
        CATALOG_PRIOR + votes
    )

    out: dict[str, dict] = {}
    for row in totals:
        count, total = row["n"], row["s"]
        out[row["item_id"]] = {
            "rating_count": count,
            "rating_average": round(total / count, 1) if count >= MIN_SHOWN else None,
            "rating_weighted": round(
                (PRIOR_WEIGHT * catalog_mean + total) / (PRIOR_WEIGHT + count), 3
            ),
            "my_rating": None,
        }
    for row in mine:
        out.setdefault(row["item_id"], empty())["my_rating"] = row["stars"]
    return out


def record(user_id: str, item_id: str, stars: int) -> None:
    """One rating per user per item. Rating again replaces the previous one."""
    now = datetime.now(UTC).isoformat(timespec="milliseconds")
    with database.connect(write=True) as conn:
        conn.execute(
            "INSERT INTO learning_ratings VALUES (?,?,?,?,?) "
            "ON CONFLICT(user_id,item_id) DO UPDATE SET "
            "stars=excluded.stars, updated_at=excluded.updated_at",
            (user_id, item_id, stars, now, now),
        )


def clear(user_id: str, item_id: str) -> None:
    with database.connect(write=True) as conn:
        conn.execute(
            "DELETE FROM learning_ratings WHERE user_id=? AND item_id=?",
            (user_id, item_id),
        )
