"""The two indexes a pillar agent retrieves from, over one text per record.

    data file / contributions table  --authoritative-->  the records
             |
             '--derived-->  one text per record --> Chroma  meaning, by cosine
                                                --> BM25    exact words, acronyms

Built the way Discover's are (marketplace/semantic.py and keyword.py), which
stay exactly as they are. Nothing is read back out of an index as fact:
retrieval returns ids and numbers, and each record is then read from its
source. Deleting the index directory costs a rebuild and nothing else.

Every record belongs to a source. "catalog" is what ships in a data file;
"contribution" is what people submit through Create. A sync replaces one
source at a time, so reloading a catalogue never drops a contribution.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import re
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from ..text import STOP_WORDS, stem

log = logging.getLogger("mufg.retrieval")

# What each retriever proposes to fusion, as on Discover.
CANDIDATES = 6
# Records embedded per call. The model's working memory grows to the largest
# batch it has run and keeps that size, so a whole catalogue at once cost
# about 230MB on a fresh boot; eight at a time keeps startup within Render's
# 512MB.
EMBED_BATCH = 8
# Standard BM25 parameters: term-frequency saturation, length normalisation.
K1 = 1.5
B = 0.75

Source = Literal["catalog", "contribution"]


@dataclass(frozen=True)
class Doc:
    id: str
    text: str
    source: Source = "catalog"
    # Who submitted it, for a contribution: kept on the vector for audit.
    # Access is decided per request from the records themselves, never from
    # what an index holds.
    owner: str = ""


def enabled() -> bool:
    return os.environ.get("CREDITWIZ_DISABLE_SEMANTIC") not in ("1", "true")


def tokens(text: str) -> list[str]:
    """Terms for BM25, with Nexus's own stop words and stemmer."""
    return [stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 1 and w not in STOP_WORDS]


def fingerprint(doc: Doc) -> str:
    return hashlib.sha256(f"{doc.source}\n{doc.owner}\n{doc.text}".encode("utf-8")).hexdigest()[:16]


@lru_cache(maxsize=1)
def _embedder():
    """The embedding model every agent's collection uses: the very instance
    Discover's open index holds, so the process runs one ONNX session and a
    vector means the same thing in every index.

    A second session cost about 370MB on a fresh boot and took the service
    over Render's 512MB. Discover's code is left as it is: this reads the
    instance its collection already holds, and builds a separate one only
    when Discover's index could not open."""
    from ..marketplace import semantic

    collection = semantic.index._open()
    shared = getattr(collection, "_embedding_function", None) if collection is not None else None
    return shared if shared is not None else semantic._embedding_function()


class SemanticIndex:
    """One Chroma collection. Never breaks search: any failure disables it and
    the agent answers from its keyword index alone."""

    def __init__(self, collection: str) -> None:
        self.collection = collection
        self._lock = threading.Lock()
        self._handle = None
        self._broken = False

    def _open(self):
        if self._handle is not None or self._broken or not enabled():
            return self._handle
        with self._lock:
            if self._handle is not None or self._broken:
                return self._handle
            try:
                import chromadb

                from ..database import VAR_DIR

                # The same directory as Discover's index, one collection each.
                path = Path(os.environ.get("CREDITWIZ_INDEX_DIR") or VAR_DIR / "chroma")
                path.mkdir(parents=True, exist_ok=True)
                self._handle = chromadb.PersistentClient(path=str(path)).get_or_create_collection(
                    self.collection,
                    embedding_function=_embedder(),
                    metadata={"hnsw:space": "cosine"},
                )
            except Exception as exc:  # noqa: BLE001 - degrade, never fail search
                log.warning("%s index unavailable, using keyword search: %s", self.collection, exc)
                self._broken = True
        return self._handle

    @staticmethod
    def _store(handle, docs: list[Doc]) -> None:
        for start in range(0, len(docs), EMBED_BATCH):
            batch = docs[start : start + EMBED_BATCH]
            handle.upsert(
                ids=[d.id for d in batch],
                documents=[d.text for d in batch],
                metadatas=[
                    {
                        "fingerprint": fingerprint(d),
                        "source": d.source,
                        # The id again, as metadata: Chroma filters on
                        # metadata, and a request's permitted set is matched on this.
                        "rid": d.id,
                        **({"owner": d.owner} if d.owner else {}),
                    }
                    for d in batch
                ],
            )

    def sync(self, source: Source, docs: list[Doc]) -> dict[str, int]:
        """Bring one source in line: new records embedded, changed ones
        re-embedded, removed ones deleted, unchanged ones left alone, so a
        restart embeds nothing that has not changed."""
        counts = {"added": 0, "updated": 0, "removed": 0, "unchanged": 0}
        handle = self._open()
        if handle is None:
            return counts
        try:
            existing = handle.get(where={"source": source}, include=["metadatas"])
            known = {i: (m or {}).get("fingerprint") for i, m in zip(existing["ids"], existing["metadatas"])}
            changed = [d for d in docs if known.get(d.id) != fingerprint(d)]
            wanted = {d.id for d in docs}
            stale = [i for i in known if i not in wanted]
            if changed:
                self._store(handle, changed)
            if stale:
                handle.delete(ids=stale)
            counts.update(
                added=sum(d.id not in known for d in changed),
                updated=sum(d.id in known for d in changed),
                removed=len(stale),
                unchanged=len(docs) - len(changed),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("%s index sync failed, using keyword search: %s", self.collection, exc)
            self._broken = True
        return counts

    def upsert(self, doc: Doc) -> bool:
        """Embed and store one record now. True once it is in the index."""
        handle = self._open()
        if handle is None:
            return False
        try:
            self._store(handle, [doc])
        except Exception as exc:  # noqa: BLE001
            log.warning("%s index could not store a record: %s", self.collection, type(exc).__name__)
            return False
        return True

    def remove(self, doc_id: str) -> None:
        handle = self._open()
        if handle is None:
            return
        try:
            handle.delete(ids=[doc_id])
        except Exception as exc:  # noqa: BLE001
            log.warning("%s index could not remove a record: %s", self.collection, type(exc).__name__)

    def stored(self, doc_id: str) -> dict | None:
        """What the index holds for one record, or None. For audit and tests."""
        handle = self._open()
        if handle is None:
            return None
        try:
            found = handle.get(ids=[doc_id], include=["metadatas"])
        except Exception:  # noqa: BLE001
            return None
        return found["metadatas"][0] if found["ids"] else None

    def search(self, text: str, allowed: frozenset[str], limit: int = CANDIDATES) -> dict[str, float]:
        """Permitted record ids mapped to cosine similarity in 0..1.

        The permitted set filters inside the query, so what comes back is
        already allowed and a record this person may not see never takes a
        candidate slot. Empty means nothing close enough, which is also what a
        disabled or broken index returns. Not cached: every search embeds the
        query and asks the index afresh.
        """
        handle = self._open()
        text = text.strip()
        if handle is None or not text or not allowed:
            return {}
        try:
            found = handle.query(query_texts=[text], n_results=limit, where={"rid": {"$in": sorted(allowed)}})
        except Exception as exc:  # noqa: BLE001
            log.warning("%s query failed, using keyword search: %s", self.collection, type(exc).__name__)
            return {}
        # Cosine distance can drift marginally outside [0, 2]; clamp.
        return {i: max(0.0, min(1.0, 1.0 - float(d))) for i, d in zip(found["ids"][0], found["distances"][0])}

    @property
    def available(self) -> bool:
        """Open and populated. An empty collection must not answer "nothing";
        the agent falls back to keywords instead."""
        handle = self._open()
        if handle is None:
            return False
        try:
            return handle.count() > 0
        except Exception:  # noqa: BLE001
            return False


class KeywordIndex:
    """BM25 over the same texts, in process. At catalogue scale a query is
    scored in microseconds, so there is nothing to persist."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_source: dict[str, dict[str, list[str]]] = {}
        self._docs: dict[str, list[str]] = {}
        self._df: dict[str, int] = {}
        self._avgdl = 1.0

    def sync(self, source: Source, docs: list[Doc]) -> None:
        with self._lock:
            self._by_source[source] = {d.id: tokens(d.text) for d in docs}
            self._rebuild()

    def upsert(self, doc: Doc) -> None:
        with self._lock:
            self._by_source.setdefault(doc.source, {})[doc.id] = tokens(doc.text)
            self._rebuild()

    def remove(self, doc_id: str) -> None:
        with self._lock:
            for docs in self._by_source.values():
                docs.pop(doc_id, None)
            self._rebuild()

    def _rebuild(self) -> None:
        docs = {i: terms for source in self._by_source.values() for i, terms in source.items()}
        df: dict[str, int] = {}
        for terms in docs.values():
            for term in set(terms):
                df[term] = df.get(term, 0) + 1
        # Swapped in whole, so a search running alongside sees old or new.
        self._docs, self._df = docs, df
        self._avgdl = (sum(map(len, docs.values())) / len(docs)) if docs else 1.0

    def search(self, text: str, allowed: frozenset[str], limit: int = CANDIDATES) -> dict[str, float]:
        """Permitted record ids mapped to BM25 score, best first, hits only.
        Corpus statistics stay whole-index, so a term weighs the same for
        everyone; only the candidates are narrowed."""
        query = tokens(text)
        docs, df, avgdl = self._docs, self._df, self._avgdl
        if not query or not docs or not allowed:
            return {}
        n = len(docs)
        scored: dict[str, float] = {}
        for rid, doc in docs.items():
            if rid not in allowed:
                continue
            score = 0.0
            for term in query:
                f = df.get(term)
                tf = doc.count(term) if f else 0
                if not tf:
                    continue
                idf = math.log(1 + (n - f + 0.5) / (f + 0.5))
                score += idf * tf * (K1 + 1) / (tf + K1 * (1 - B + B * len(doc) / avgdl))
            if score > 0:
                scored[rid] = round(score, 4)
        return dict(sorted(scored.items(), key=lambda kv: -kv[1])[:limit])

    def coverage(self, text: str, ids) -> dict[str, float]:
        """The share of the query's distinct terms each record contains."""
        query = set(tokens(text))
        docs = self._docs
        if not query:
            return {}
        return {rid: len(query & set(docs.get(rid, ()))) / len(query) for rid in ids}

    @property
    def size(self) -> int:
        return len(self._docs)
