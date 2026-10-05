"""Pluralsight, through its GraphQL API.

The hub's catalogue holds what MUFG curated: which courses, for whom, on which
path. Pluralsight supplies what it knows about each of those courses and each
learner's progress. Configure from MUFG's Pluralsight plan:

    PLURALSIGHT_API_KEY    an API key from the plan administrator
    PLURALSIGHT_SSO_ORG    the plan's single-sign-on organisation, for course links

Without a key the catalogue's own sample values stand, and a course opens as a
Pluralsight search for its title instead of a single-sign-on link. Pluralsight
plays its videos only on its own site, so a course always opens there.
"""

from __future__ import annotations

import os
import threading
import time
from urllib.parse import quote

from .. import http

ENDPOINT = "https://paas-api.pluralsight.com/graphql"
SERVICE = "Pluralsight"
_COURSE_SECONDS = 3600.0
_PROGRESS_SECONDS = 300.0

COURSES = """
query HubCourses($ids: [String]) {
  courseCatalog(first: 100, filter: {ids: $ids}) {
    nodes { id slug title level shortDescription description courseSeconds authors url }
  }
}
"""
SEARCH = """
query HubSearch($term: String) {
  courseCatalog(first: 10, filter: {searchTerm: $term, showOffPlanContent: false}) {
    nodes { id slug title level shortDescription courseSeconds url }
  }
}
"""
LEARNER = """
query HubLearner($emails: [String]) {
  users(filter: {emails: $emails}) { nodes { psUserId } }
}
"""
PROGRESS = """
query HubProgress($users: [ID], $courses: [String]) {
  courseProgress(filter: {psUserIds: $users, courseIds: $courses}) {
    nodes { courseId percentComplete isCourseCompleted }
  }
}
"""


def configured() -> bool:
    return bool(os.environ.get("PLURALSIGHT_API_KEY", "").strip())


def query(text: str, variables: dict) -> dict:
    response = http.send(
        SERVICE,
        "POST",
        ENDPOINT,
        headers={"Authorization": f"Bearer {os.environ['PLURALSIGHT_API_KEY'].strip()}"},
        json_body={"query": text, "variables": variables},
    )
    data = response.json() or {}
    if data.get("errors"):
        raise http.ExternalError(SERVICE, response.status, http.reason(response.text))
    return data.get("data") or {}


_held: dict[tuple, tuple[object, float]] = {}
_held_lock = threading.Lock()


def _remember(key: tuple, seconds: float, fetch):
    now = time.monotonic()
    with _held_lock:
        found = _held.get(key)
        if found and found[1] > now:
            return found[0]
    value = fetch()
    with _held_lock:
        if len(_held) > 256:
            _held.clear()
        _held[key] = (value, now + seconds)
    return value


def courses(ids: list[str]) -> dict[str, dict]:
    """What Pluralsight says about these courses, by course id."""
    wanted = sorted({i for i in ids if i})
    if not wanted:
        return {}

    def fetch():
        nodes = query(COURSES, {"ids": wanted}).get("courseCatalog", {}).get("nodes") or []
        return {str(n["id"]): n for n in nodes if n and n.get("id")}

    return _remember(("courses", tuple(wanted)), _COURSE_SECONDS, fetch)


def search(term: str) -> list[dict]:
    """Courses on MUFG's plan that match, from Pluralsight's whole library."""

    def fetch():
        return query(SEARCH, {"term": term}).get("courseCatalog", {}).get("nodes") or []

    return _remember(("search", term.lower()), _COURSE_SECONDS, fetch)


def progress(email: str, ids: list[str]) -> dict[str, tuple[int, bool]]:
    """This learner's progress on these courses: percent complete, and whether done."""
    wanted = sorted({i for i in ids if i})
    if not email or not wanted:
        return {}

    def fetch():
        users = query(LEARNER, {"emails": [email]}).get("users", {}).get("nodes") or []
        if not users:
            return {}
        nodes = query(PROGRESS, {"users": [users[0]["psUserId"]], "courses": wanted}).get("courseProgress", {}).get("nodes") or []
        out: dict[str, tuple[int, bool]] = {}
        for n in nodes:
            pct = float(n.get("percentComplete") or 0)
            # Read as a fraction when it is one; the schema says only Float.
            pct = pct * 100 if pct <= 1 else pct
            out[str(n["courseId"])] = (max(0, min(100, round(pct))), bool(n.get("isCourseCompleted")))
        return out

    return _remember(("progress", email.lower(), tuple(wanted)), _PROGRESS_SECONDS, fetch)


def launch_url(title: str, catalogue_url: str, live: dict | None) -> str:
    """Where Start opens: a single-sign-on link when MUFG's org and the course's
    slug are known, else Pluralsight's own course URL, else a search for the title."""
    org = os.environ.get("PLURALSIGHT_SSO_ORG", "").strip()
    slug = (live or {}).get("slug") or ""
    if org and slug:
        return f"https://app.pluralsight.com/sso/{quote(org)}?returnUrl={quote('library/courses/' + slug, safe='/')}"
    if live and live.get("url"):
        return str(live["url"])
    if catalogue_url:
        return catalogue_url
    return "https://www.pluralsight.com/search?q=" + quote(title)
