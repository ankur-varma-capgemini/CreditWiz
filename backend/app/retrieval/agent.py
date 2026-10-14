"""A pillar agent: query -> embedding -> hybrid -> relevance gate -> rerank.

The pipeline Discover runs for agents (docs/search-flow.md), for any
catalogue. A pillar configures one with what its records are and how each
reads to the reranker, and hands it the records the person may see.

    query       masked by the guardrails before any agent sees it
    embedding   MiniLM, the query as given
    hybrid      Chroma (meaning) and BM25 (exact words), each told what the
                person may see, fused by rank (RRF, k 60)
    gate        kept if close in meaning (0.30, and 65% of the best) or a
                strong keyword hit (half the best keyword score, carrying
                half of the words typed)
    rerank      the model judges every candidate against the request, strong,
                partial or no fit: strong comes before partial, and what does
                not fit is dropped, even when it is the only one. Skipped when
                policy keeps the request from the model, and on any failure,
                which keeps the fused order
    context     the caller reads each id's record from its source

Permission first and again after: the permitted set filters inside both
retrievers, and nothing outside it survives the gate.
"""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass, field, replace
from time import perf_counter
from typing import Callable, Literal

from ..text import subject_stems, word_starts
from .index import Doc, KeywordIndex, SemanticIndex, Source

# Discover's floors (marketplace/search.py), measured for a bare query.
SIMILARITY_FLOOR = 0.30
RELATIVE_FLOOR = 0.65
KEYWORD_RELATIVE_FLOOR = 0.5
# A keyword rescue must rest on most of what was typed. One shared word, such
# as "best" in "best pizza near me", scores as high as a rare acronym and
# would rescue anything that happens to contain it. Half the query's terms:
# the rule every word search on Nexus already uses.
KEYWORD_COVERAGE = 0.5
RRF_K = 60
# The shortlist each agent returns, and the most the reranker reads.
RESULT_LIMIT = 6

Retrieval = Literal["hybrid", "keyword"]


@dataclass(frozen=True)
class Candidate:
    id: str
    # The fused rank score, and the two signals behind it (either may be absent).
    score: float
    similarity: float | None
    keyword: float | None
    # The model's judgement against the request: "strong" or "partial". None
    # when it was not asked (the data policy) or its call failed.
    fit: str | None = None


@dataclass
class Found:
    candidates: list[Candidate]
    # "hybrid" when the vector index answered, "keyword" when it could not.
    retrieval: Retrieval
    reranked: bool
    embed_ms: int = 0
    rerank_ms: int = 0
    # What each retriever proposed before the gate, best five, for the trace.
    proposed: dict[str, dict[str, float]] = field(default_factory=dict)


def rrf(*rankings: dict[str, float], k: int = RRF_K) -> dict[str, float]:
    """Reciprocal Rank Fusion: ranks, not scores, so a cosine in 0..1 and a
    BM25 score in 0..10 fuse without either scale dominating."""
    fused: dict[str, float] = {}
    for ranking in rankings:
        for position, rid in enumerate(sorted(ranking, key=lambda i: -ranking[i])):
            fused[rid] = fused.get(rid, 0.0) + 1.0 / (k + position + 1)
    return fused


def gate(
    similar: dict[str, float],
    keywords: dict[str, float],
    permitted: frozenset[str],
    coverage: dict[str, float],
) -> list[Candidate]:
    """Fuse one query's two rankings and keep only what is relevant. RRF
    always returns something; this decides what is shown. `coverage` is the
    share of the query's terms each keyword hit carries."""
    if not similar and not keywords:
        return []
    top_similarity = max(similar.values(), default=0.0)
    top_keyword = max(keywords.values(), default=0.0)

    def relevant(rid: str) -> bool:
        sim, kw = similar.get(rid, 0.0), keywords.get(rid, 0.0)
        close = sim >= SIMILARITY_FLOOR and sim >= top_similarity * RELATIVE_FLOOR
        strong_keyword = (
            kw > 0 and kw >= top_keyword * KEYWORD_RELATIVE_FLOOR and coverage.get(rid, 0.0) >= KEYWORD_COVERAGE
        )
        return close or strong_keyword

    return [
        Candidate(rid, round(score, 4), round(similar[rid], 3) if rid in similar else None, keywords.get(rid))
        for rid, score in sorted(rrf(similar, keywords).items(), key=lambda kv: -kv[1])
        if rid in permitted and relevant(rid)
    ]


def _top(scores: dict[str, float]) -> dict[str, float]:
    return dict(sorted(scores.items(), key=lambda kv: -kv[1])[:5])


class RetrievalAgent:
    def __init__(self, name: str, what: str) -> None:
        # The collection it keeps, and what the reranker is told it ranks.
        self.name = name
        self.what = what
        self.semantic = SemanticIndex(name)
        self.keyword = KeywordIndex()
        self._lock = threading.Lock()
        self._marks: dict[str, str] = {}

    # ------------------------------------------------------------- ingestion

    def sync(self, source: Source, docs: list[Doc]) -> dict[str, int] | None:
        """Bring one source in line with its records. Cheap when nothing
        changed, one fingerprint over the texts, and None back."""
        mark = hashlib.sha256(
            "\n".join(f"{d.id}\t{d.owner}\t{d.text}" for d in sorted(docs, key=lambda d: d.id)).encode("utf-8")
        ).hexdigest()
        if self._marks.get(source) == mark:
            return None
        with self._lock:
            if self._marks.get(source) == mark:
                return None
            self.keyword.sync(source, docs)
            counts = self.semantic.sync(source, docs)
            self._marks[source] = mark
        return counts

    def add(self, doc: Doc) -> bool:
        """Ingest one record now: found by its words at once, and embedded and
        stored in the vector index. False when the vector index could not take
        it; it is still found by its words, and embedded at the next sync."""
        with self._lock:
            self.keyword.upsert(doc)
            self._marks.pop(doc.source, None)
            return self.semantic.upsert(doc)

    def remove(self, doc_id: str, source: Source) -> None:
        with self._lock:
            self.keyword.remove(doc_id)
            self.semantic.remove(doc_id)
            self._marks.pop(source, None)

    # ------------------------------------------------------------- retrieval

    def find(
        self,
        queries: list[str],
        allowed: set[str],
        *,
        describe: Callable[[str], str],
        prefer: set[str] | frozenset[str] = frozenset(),
        rerank_query: str | None = None,
        limit: int = RESULT_LIMIT,
    ) -> Found:
        """One request's candidates, best first.

        `queries` are the request's searches, as typed and as the planner
        rewrote it: each is retrieved and gated on its own, then fused, so a
        rewrite can add recall but never lose what the person's own words
        found. `prefer` leans toward their own desk or role; it reorders what
        retrieval found and never adds a record. `rerank_query` is what the
        model may read, or None to keep the request from it.
        """
        permitted = frozenset(allowed)
        semantic_up = self.semantic.available
        retrieval: Retrieval = "hybrid" if semantic_up else "keyword"
        rankings: list[dict[str, float]] = []
        kept: dict[str, Candidate] = {}
        proposed: dict[str, dict[str, float]] = {"semantic": {}, "keyword": {}}
        started = perf_counter()
        for q in dict.fromkeys(q.strip() for q in queries if q.strip()):
            similar = self.semantic.search(q, permitted) if semantic_up else {}
            keywords = self.keyword.search(q, permitted)
            for name, scores in (("semantic", similar), ("keyword", keywords)):
                for rid, s in scores.items():
                    proposed[name][rid] = max(s, proposed[name].get(rid, 0.0))
            passed = gate(similar, keywords, permitted, self.keyword.coverage(q, keywords))
            rankings.append({c.id: c.score for c in passed})
            for c in passed:
                kept.setdefault(c.id, c)
        embed_ms = round((perf_counter() - started) * 1000)
        proposed = {name: _top(scores) for name, scores in proposed.items()}
        if not kept:
            return Found([], retrieval, False, embed_ms, 0, proposed)

        preferred = {rid: 1.0 for rid in kept if rid in prefer}
        fused = rrf(*rankings, preferred) if len(rankings) > 1 or preferred else rankings[0]
        shortlist = [
            replace(kept[rid], score=round(score, 4))
            for rid, score in sorted(fused.items(), key=lambda kv: -kv[1])
        ][:limit]

        reranked, rerank_ms = False, 0
        if rerank_query:
            t = perf_counter()
            judged = rerank(self.what, rerank_query, [(c.id, describe(c.id)) for c in shortlist])
            rerank_ms = round((perf_counter() - t) * 1000)
            if judged is not None:
                by_id = {c.id: c for c in shortlist}
                shortlist = [
                    replace(by_id[rid], fit=fit) for rid, fit in judged_order([c.id for c in shortlist], judged)
                ]
                reranked = True
        return Found(shortlist, retrieval, reranked, embed_ms, rerank_ms, proposed)


def rerank(what: str, query: str, candidates: list[tuple[str, str]]) -> list[tuple[str, str]] | None:
    """The model's judgement of a shortlist of (id, description): each id with
    its fit, "strong", "partial" or "none", best first. None to keep the
    order it came in.

    Fusion orders by agreement between two retrievers, a proxy for relevance
    rather than a judgement of it. This compares each candidate with the
    request, over the shortlist only, where the cost is bounded. The model
    grades every candidate rather than choosing which to leave out: asked to
    omit, it emptied answers retrieval had right ("credit memo" lost every
    memo prompt); asked to grade, it has "partial" for the closest thing.

    A single candidate is judged too: with nothing to order, the question is
    only whether it fits, and an unrelated lone match ("Code Review Assistant"
    for a portfolio review) is exactly what should not be shown.

    Not cached: every request is read by the model, even one asked before.
    """
    from ..hub import llm

    if not candidates or not llm.available():
        return None
    return llm.rerank(what, query, candidates)


_FIT_RANK = {"strong": 0, "partial": 1}


def judged_order(ids: list[str], judged: list[tuple[str, str]]) -> list[tuple[str, str | None]]:
    """The shortlist as judged: strong fits, then partial ones, each in the
    model's order; what it judged no fit is dropped. Anything it did not
    judge keeps its place behind, unjudged, so a short reply loses nothing."""
    graded = {rid: fit for rid, fit in judged if rid in ids}
    placed = sorted(((rid, fit) for rid, fit in graded.items() if fit in _FIT_RANK), key=lambda rf: _FIT_RANK[rf[1]])
    return [*placed, *((rid, None) for rid in ids if rid not in graded)]


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def explain(c: Candidate, labels: list[str], queries: list[str]) -> str:
    """Why a record is here, from its own labels and the two signals: metadata
    anyone can check, not generated prose."""
    starts = word_starts(subject_stems(" ".join(queries)))
    # One label per spelling: a topic "Prompting" and a tag "prompting" are one.
    distinct = {label.lower(): label for label in reversed(labels) if label}
    matched = [label for low, label in reversed(distinct.items()) if any(s.search(low) for s in starts)]
    if matched:
        return f"Matches {_join(matched[:3])}."
    if c.similarity is not None and c.keyword is not None:
        return "Close in meaning to what you asked, and shares its words."
    if c.similarity is not None:
        return "Close in meaning to what you asked."
    return "Shares words with what you asked."
