"""The prompt library, read from data/prompts.json, and how it is searched."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from ..text import subject_stems, word_starts
from .models import Desk, Library, Prompt

_DATA_DIR = Path(
    os.environ.get("CREDITWIZ_DATA_DIR", Path(__file__).resolve().parents[2] / "data")
)
_RELOAD_SECONDS = 5.0


class LibraryStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loaded_at = 0.0
        self._library: Library | None = None
        self._by_id: dict[str, Prompt] = {}

    def _refresh(self) -> Library:
        now = time.monotonic()
        if self._library is not None and now - self._loaded_at < _RELOAD_SECONDS:
            return self._library
        with self._lock:
            if self._library is None or now - self._loaded_at >= _RELOAD_SECONDS:
                raw = json.loads((_DATA_DIR / "prompts.json").read_text(encoding="utf-8"))
                self._library = Library.model_validate(raw)
                self._by_id = {p.id: p for p in self._library.prompts}
                self._loaded_at = now
            return self._library

    @property
    def library(self) -> Library:
        return self._refresh()

    def prompt(self, prompt_id: str) -> Prompt | None:
        self._refresh()
        return self._by_id.get(prompt_id)

    def desk_for(self, job_title: str) -> Desk | None:
        title = job_title.strip().lower()
        return next(
            (d for d in self.library.desks if title in (t.lower() for t in d.job_titles)),
            None,
        )


store = LibraryStore()


def search(query: str, prompts: list[Prompt]) -> list[tuple[int, Prompt]]:
    """Prompts carrying at least half of the request's subject words, best first.

    The same word-start matching as Nexus search, so "stress testing" finds a
    stress tester. A word in the title counts twice: it names the job the prompt
    does, where the description only mentions it.
    """
    stems = subject_stems(query)
    if not stems:
        return []
    starts = word_starts(stems)
    needed = max(1, -(-len(stems) // 2))
    scored = []
    for p in prompts:
        text = " ".join([p.title, p.description, p.category, *p.tags]).lower()
        hits = sum(bool(s.search(text)) for s in starts)
        if hits < needed:
            continue
        title = p.title.lower()
        scored.append((hits + sum(bool(s.search(title)) for s in starts), p))
    scored.sort(key=lambda pair: (-pair[0], -pair[1].uses))
    return scored
