"""Microsoft Learn, through Microsoft's public Learn MCP server. No sign-in.

Two of its tools: microsoft_docs_search finds Learn content, and
microsoft_docs_fetch reads a page as markdown, so a Learn module and its units
can be read inside the hub. Microsoft notes the tool list can change; a tool
that disappears shows up as a failed call and on the Integrations page.

Queries leave the bank, so client names are taken out before a search is sent.
"""

from __future__ import annotations

import html
import json
import re
import threading
import time
from urllib.parse import urljoin, urlparse

from pydantic import BaseModel

from .. import http

MCP_URL = "https://learn.microsoft.com/api/mcp"
SERVICE = "Microsoft Learn"
HOST = "learn.microsoft.com"
_PAGE_SECONDS = 3600.0
_HEADERS = {"Accept": "application/json, text/event-stream"}


class LearnLink(BaseModel):
    title: str
    url: str


class LearnPage(BaseModel):
    url: str
    title: str
    # "Module", "Learning path", "Unit" or "Page"
    kind: str
    # "9 units", "7 modules"; empty for a unit or an article
    count: str = ""
    level: str = ""
    # Minutes, for a unit page
    minutes: int | None = None
    summary: str = ""
    objectives: list[str] = []
    prerequisites: str = ""
    # A module's units, or a learning path's modules
    units: list[LearnLink] = []
    markdown: str


class LearnResult(BaseModel):
    title: str
    url: str
    excerpt: str


def is_learn_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname == HOST


# ------------------------------------------------------------------- session


class _Session:
    """One MCP session, reused; started again once if the server drops it."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sid: str | None = None
        self._ids = 0

    def _post(self, body: dict) -> dict | None:
        headers = dict(_HEADERS, **({"mcp-session-id": self._sid} if self._sid else {}))
        response = http.send(SERVICE, "POST", MCP_URL, headers=headers, json_body=body, timeout=30)
        self._sid = response.headers.get("mcp-session-id", self._sid)
        if "text/event-stream" in response.headers.get("content-type", ""):
            for line in response.text.splitlines():
                if line.startswith("data:"):
                    return json.loads(line[5:].strip())
            return None
        return response.json()

    def _start(self) -> None:
        self._sid = None
        self._post(
            {
                "jsonrpc": "2.0",
                "id": 0,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "mufg-ai-hub", "version": "0.1"},
                },
            }
        )
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def call(self, tool: str, arguments: dict) -> str:
        with self._lock:
            for attempt in (1, 2):
                try:
                    if self._sid is None:
                        self._start()
                    self._ids += 1
                    reply = self._post(
                        {"jsonrpc": "2.0", "id": self._ids, "method": "tools/call", "params": {"name": tool, "arguments": arguments}}
                    )
                    break
                except http.ExternalError:
                    self._sid = None
                    if attempt == 2:
                        raise
        if not reply or "result" not in reply:
            message = ((reply or {}).get("error") or {}).get("message", "")
            raise http.ExternalError(SERVICE, None, message or f"{tool} returned nothing")
        result = reply["result"]
        text = "".join(c.get("text", "") for c in result.get("content", []) if c.get("type", "text") == "text")
        if result.get("isError"):
            raise http.ExternalError(SERVICE, None, text[:200])
        return text


_session = _Session()


# -------------------------------------------------------------------- search


def _plain(markdown: str) -> str:
    # Docs pages open with which product versions they apply to: not an excerpt.
    text = re.sub(r"(?im)^[\s*_>]*applies to:?.*$", "", markdown)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[#*_`>|]", "", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def search(query: str, limit: int = 8) -> list[LearnResult]:
    text = _session.call("microsoft_docs_search", {"query": query})
    try:
        data = json.loads(text)
    except ValueError:
        return []
    rows = data.get("results", []) if isinstance(data, dict) else data
    found: list[LearnResult] = []
    seen: set[str] = set()
    for row in rows if isinstance(rows, list) else []:
        url = row.get("contentUrl") or row.get("url") or ""
        page_url = url.split("#")[0]
        # One hit per page: the search returns a page once per matching passage.
        if not is_learn_url(url) or page_url in seen:
            continue
        seen.add(page_url)
        title = re.sub(r"\s+-\s+Training$", "", row.get("title", "")).strip() or url
        excerpt = _plain(row.get("content", ""))
        if excerpt.startswith(title):
            excerpt = excerpt[len(title) :].strip()
        found.append(
            LearnResult(title=title, url=page_url, excerpt=excerpt[:240] + ("…" if len(excerpt) > 240 else ""))
        )
    return found[:limit]


# ---------------------------------------------------------------------- page

_LINK = re.compile(r"(!?\[[^\]]*\]\()([^)\s]+)(\))")
_LEVELS = ("Beginner", "Intermediate", "Advanced")
_DROP = {
    "Completed",
    "Take the module assessment",
    "Module Assessment Results",
    "Start",
    "**Achievement Code**",
    "Would you like to request an achievement code?",
}
_ROOT = re.compile(r"/training/(?:modules|paths)/[^/]+$")


def _base(url: str) -> str:
    # A module or path root is a folder: its units are relative to it.
    path = urlparse(url).path
    return url + "/" if _ROOT.search(path) else url


def _absolute(line: str, base: str) -> str:
    return _LINK.sub(lambda m: f"{m.group(1)}{urljoin(base, html.unescape(m.group(2)))}{m.group(3)}", line)


def _relative_unit(target: str) -> bool:
    return not re.match(r"^(?:[a-z]+:|/|#)", target)


def parse_page(url: str, text: str) -> LearnPage:
    base = _base(url)
    title = ""
    kind = "Page"
    count = ""
    level = ""
    minutes: int | None = None
    summary = ""
    objectives: list[str] = []
    prerequisites = ""
    units: list[LearnLink] = []
    seen_units: set[str] = set()
    out: list[str] = []
    section = ""
    glance = False
    skip_paragraph = False
    started = False

    for raw in text.replace("\r", "").split("\n"):
        line = raw.replace("&nbsp;", " ").rstrip()
        s = line.strip()
        if not title and s.startswith("# "):
            title = html.unescape(s[2:].strip())
            continue
        if s.startswith(("![", "[![")) and "/achievements/" in s:
            # Learn's decorative badges, linked or not.
            continue
        if s in _DROP or s.startswith("Assess your understanding of this module"):
            continue
        if skip_paragraph:
            if s:
                started = True
            elif started:
                skip_paragraph = False
            continue
        if s.startswith("## "):
            section = s[3:].strip()
            glance = section == "At a glance"
            if section == "Get started with Azure":
                skip_paragraph, started = True, False
                continue
            if glance:
                continue
            out.append(line)
            continue
        if glance:
            found = re.search(r"\[(" + "|".join(_LEVELS) + r")\]", s)
            if found and not level:
                level = found.group(1)
            if s and not re.match(r"^(?:-|\[|!)", s):
                # The path's description closes its "At a glance" block.
                glance = False
                summary = summary or html.unescape(s)
                out.append(line)
            continue
        if not section:
            m = re.fullmatch(r"- (Module|Learning Path)", s)
            if m:
                kind = "Module" if m.group(1) == "Module" else "Learning path"
                continue
            m = re.fullmatch(r"- (\d+) (Units?|Modules?)", s)
            if m:
                count = f"{m.group(1)} {m.group(2).lower()}"
                continue
            m = re.fullmatch(r"- (\d+) minutes?", s)
            if m:
                kind, minutes = "Unit", int(m.group(1))
                continue
            if raw.startswith(" ") and s and len(s) <= 40 and not re.match(r"^[-*#!\[>|`]", s):
                # A module's tag line: its level, then roles and products.
                if s in _LEVELS and not level:
                    level = s
                continue
            if s and not summary and kind in ("Module", "Learning path") and not re.match(r"^[-*#!\[>|`]", s):
                summary = html.unescape(s)
        if section == "Learning objectives" and s.startswith("- ") and not s.startswith("- ["):
            # Some modules list their units straight after the objectives.
            objectives.append(html.unescape(s[2:].strip()))
        if section == "Prerequisites" and s and not prerequisites and not s.startswith("#"):
            prerequisites = html.unescape(s.lstrip("- ").strip())
        unit = re.fullmatch(r"(?:- )?\[([^\]]+)\]\(([^)\s]+)\)", s)
        if unit and not s.startswith("[!["):
            target = html.unescape(unit.group(2))
            is_unit = kind == "Module" and s.startswith("- ") and _relative_unit(target)
            is_module = kind == "Learning path" and "/modules/" in target
            if is_unit or is_module:
                link = urljoin(base, target)
                if link not in seen_units:
                    seen_units.add(link)
                    units.append(LearnLink(title=html.unescape(unit.group(1)), url=link))
        out.append(_absolute(line, base))

    markdown = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
    return LearnPage(
        url=url,
        title=title or url,
        kind=kind,
        count=count,
        level=level,
        minutes=minutes,
        summary=summary,
        objectives=objectives,
        prerequisites=prerequisites,
        units=units,
        markdown=markdown,
    )


_pages: dict[str, tuple[LearnPage, float]] = {}
_pages_lock = threading.Lock()


def page(url: str) -> LearnPage:
    """A Learn page, read through the MCP server. Held for an hour."""
    now = time.monotonic()
    with _pages_lock:
        held = _pages.get(url)
        if held and held[1] > now:
            return held[0]
    found = parse_page(url, _session.call("microsoft_docs_fetch", {"url": url}))
    with _pages_lock:
        if len(_pages) > 128:
            _pages.clear()
        _pages[url] = (found, now + _PAGE_SECONDS)
    return found
