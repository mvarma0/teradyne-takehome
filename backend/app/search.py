"""Hybrid retrieval: Chroma (semantic) + BM25 -> weighted RRF -> pointwise LLM rerank."""

import logging
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Protocol

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from rank_bm25 import BM25Okapi

from app import db
from app.config import get_settings
from app.llm import collection_name, get_embeddings, structured_llm
from app.schemas import QueryFilters, RetrievedChunk

# ---- vectorstore --------------------------------------------------------------------------
# ChromaDB wrapper (cosine space; relevance = 1 - cosine distance).


@lru_cache(maxsize=1)
def get_vectorstore() -> Chroma:
    s = get_settings()
    s.chroma_dir.mkdir(parents=True, exist_ok=True)
    return Chroma(
        collection_name=collection_name(),
        embedding_function=get_embeddings(),
        persist_directory=str(s.chroma_dir),
        collection_metadata={"hnsw:space": "cosine"},
    )


def delete_doc_chunks(doc_id: str) -> None:
    vs = get_vectorstore()
    ids = vs.get(where={"doc_id": doc_id}, include=["metadatas"])["ids"]
    if ids:
        vs.delete(ids=ids)


def replace_doc_chunks(doc_id: str, chunks: list[Document]) -> None:
    delete_doc_chunks(doc_id)
    if chunks:
        get_vectorstore().add_documents(chunks, ids=[c.metadata["chunk_id"] for c in chunks])


def count_chunks() -> int:
    return get_vectorstore()._collection.count()


def all_chunks() -> list[Document]:
    got = get_vectorstore().get(include=["documents", "metadatas"])
    return [
        Document(id=i, page_content=d, metadata=m)
        for i, d, m in zip(got["ids"], got["documents"], got["metadatas"], strict=True)
    ]


def semantic_search(query: str, k: int, where: dict | None) -> list[tuple[Document, float]]:
    if count_chunks() == 0:
        return []
    pairs = get_vectorstore().similarity_search_with_score(query, k=k, filter=where)
    return [(doc, 1.0 - dist) for doc, dist in pairs]


def doc_chunks(doc_id: str) -> list[dict]:
    got = get_vectorstore().get(where={"doc_id": doc_id}, include=["documents", "metadatas"])
    rows = [
        {
            "chunk_id": i,
            "chunk_index": m.get("chunk_index", 0),
            "section": m.get("section"),
            "text": d.split("\n", 1)[-1],
        }
        for i, d, m in zip(got["ids"], got["documents"], got["metadatas"], strict=True)
    ]
    return sorted(rows, key=lambda r: r["chunk_index"])


def chunk_texts(chunk_ids: list[str]) -> dict[str, str]:
    """Full chunk text by id (citations only carry a short snippet)."""
    if not chunk_ids:
        return {}
    got = get_vectorstore().get(ids=chunk_ids, include=["documents"])
    return dict(zip(got["ids"], got["documents"], strict=True))


# ---- bm25 ---------------------------------------------------------------------------------
# In-memory BM25 index over all Chroma chunks; rebuilt lazily after ingestion.

_STOPWORDS = frozenset(
    "a an and are as at be by did do does for from has have how in is it its of on or "
    "that the this to was were what when where which who why will with".split()
)
_TOKEN = re.compile(r"[a-z0-9]+(?:[-.][a-z0-9]+)*")


def tokenize(text: str) -> list[str]:
    """Lowercase tokens; compound terms like 'eagle-5' also emit their parts."""
    tokens: list[str] = []
    for tok in _TOKEN.findall(text.lower()):
        if tok in _STOPWORDS:
            continue
        tokens.append(tok)
        if "-" in tok or "." in tok:
            tokens += [p for p in re.split(r"[-.]", tok) if p and p not in _STOPWORDS]
    return tokens


class BM25Index:
    def __init__(self, docs: list[Document]) -> None:
        self.docs = docs
        self._tokens = [set(tokenize(d.page_content)) for d in docs]
        self._bm25 = BM25Okapi([tokenize(d.page_content) for d in docs]) if docs else None

    def search(
        self, query: str, k: int, predicate: Callable[[Document], bool] | None = None
    ) -> list[tuple[Document, float]]:
        q = tokenize(query)
        if not self._bm25 or not q:
            return []
        scores = self._bm25.get_scores(q)
        q_set = set(q)
        ranked = sorted(range(len(self.docs)), key=lambda i: scores[i], reverse=True)
        out: list[tuple[Document, float]] = []
        for i in ranked:
            if not (self._tokens[i] & q_set):
                continue  # require lexical overlap
            if predicate and not predicate(self.docs[i]):
                continue
            out.append((self.docs[i], float(scores[i])))
            if len(out) >= k:
                break
        return out


_lock = threading.Lock()
_index: tuple[str, BM25Index] | None = None


def get_bm25_index() -> BM25Index:
    global _index
    with _lock:
        name = collection_name()
        if _index is None or _index[0] != name:
            _index = (name, BM25Index(all_chunks()))
        return _index[1]


def invalidate_bm25() -> None:
    global _index
    with _lock:
        _index = None


# ---- rerank -------------------------------------------------------------------------------
# Rerankers.
#
# 'llm' is a pointwise LLM judge: each fused candidate gets its own relevance call (run
# concurrently with ``batch``), so scores can never be misaligned with passages, which
# listwise prompts suffer from on small local models. Works with any configured provider.
# 'none' keeps the fused order.

log = logging.getLogger(__name__)


class RelevanceJudgement(BaseModel):
    reason: str = Field(description="One short sentence: what in the passage relates to the query")
    relevance: int = Field(
        description="0 = unrelated, 3 = same topic but does not answer, "
        "7 = partially answers, 10 = directly answers the query"
    )


_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You judge search relevance for FastChip Semiconductor's internal knowledge base. "
            "Rate how well the passage helps answer the query on a 0-10 scale. Judge the "
            "information, not the wording: if the passage contains the facts needed to answer "
            "(e.g. who is assigned a task answers 'who owns' it), score it high. Products are "
            "different things: a passage about Eagle-5 does not answer a Falcon-7 question.",
        ),
        ("human", "Query: {query}\n\nPassage:\n{passage}"),
    ]
)


class Reranker(Protocol):
    name: str

    def rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]: ...


class NoopReranker:
    name = "none"

    def rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        return chunks


class LLMReranker:
    name = "llm"

    def rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        s = get_settings()
        head, tail = chunks[: s.rerank_top_n], chunks[s.rerank_top_n :]
        if len(head) <= 1:
            return chunks
        inputs = [
            {"query": query, "passage": c.document.page_content[: s.rerank_max_chars]} for c in head
        ]
        chain = _PROMPT | structured_llm(RelevanceJudgement)
        results = chain.batch(
            inputs, config={"max_concurrency": s.rerank_concurrency}, return_exceptions=True
        )
        failures = 0
        for chunk, res in zip(head, results, strict=True):
            if isinstance(res, RelevanceJudgement):
                chunk.rerank_score = float(max(0, min(10, res.relevance)))
            else:
                failures += 1
                log.warning("rerank judgement failed for %s: %s", chunk.chunk_id, res)
        if failures == len(head):
            log.error("LLM rerank failed for all candidates; keeping fused order")
            return chunks
        # Stable sort: ties (and failed judgements) keep their fused order.
        head = sorted(
            head, key=lambda c: -1.0 if c.rerank_score is None else c.rerank_score, reverse=True
        )
        return head + tail


def get_reranker(enabled: bool = True) -> Reranker:
    if not enabled or get_settings().reranker == "none":
        return NoopReranker()
    return LLMReranker()


# ---- hybrid -------------------------------------------------------------------------------
# Hybrid retrieval: metadata pre-filter -> semantic (Chroma) + BM25 -> weighted Reciprocal
# Rank Fusion -> rerank.

_SCALAR_FILTERS = ("topic_domain", "priority", "source_type")


@dataclass
class RetrievalResult:
    chunks: list[RetrievedChunk]
    semantic_candidates: int
    bm25_candidates: int
    fused_candidates: int
    reranker: str


@dataclass
class FilterPlan:
    """Pre-filter applied to both retrievers before ranking.

    Scalar chunk metadata (topic, priority, source type) is filtered natively by Chroma.
    Person and date filters are resolved to the matching doc ids in SQLite (source of truth
    for attendees/dates) and pushed into Chroma as ``doc_id $in [...]``.
    ``allowed_doc_ids`` is None when there is no doc-level filter; an empty set means no
    document can match.
    """

    where: dict | None = None
    scalars: dict[str, str] = field(default_factory=dict)
    allowed_doc_ids: set[str] | None = None

    @property
    def matches_nothing(self) -> bool:
        return self.allowed_doc_ids is not None and not self.allowed_doc_ids

    def predicate(self, doc: Document) -> bool:
        m = doc.metadata
        if any(m.get(k) != v for k, v in self.scalars.items()):
            return False
        return self.allowed_doc_ids is None or m.get("doc_id") in self.allowed_doc_ids


def plan_filters(filters: QueryFilters | None) -> FilterPlan:
    if not filters:
        return FilterPlan()
    scalars = {k: getattr(filters, k) for k in _SCALAR_FILTERS if getattr(filters, k)}
    clauses: list[dict] = [{k: v} for k, v in scalars.items()]

    allowed: set[str] | None = None
    if filters.person or filters.date_from or filters.date_to:
        allowed = db.find_doc_ids(
            person=filters.person, date_from=filters.date_from, date_to=filters.date_to, **scalars
        )
        if not allowed:
            return FilterPlan(scalars=scalars, allowed_doc_ids=set())
        clauses.append({"doc_id": {"$in": sorted(allowed)}})

    where = None if not clauses else clauses[0] if len(clauses) == 1 else {"$and": clauses}
    return FilterPlan(where=where, scalars=scalars, allowed_doc_ids=allowed)


def fuse(
    semantic: list[tuple[Document, float]],
    lexical: list[tuple[Document, float]],
    semantic_weight: float,
    bm25_weight: float,
    rrf_k: int,
) -> list[RetrievedChunk]:
    by_id: dict[str, RetrievedChunk] = {}
    for rank, (doc, score) in enumerate(semantic, start=1):
        c = by_id.setdefault(doc.metadata["chunk_id"], RetrievedChunk(document=doc))
        c.semantic_score, c.semantic_rank = score, rank
        c.fused_score += semantic_weight / (rrf_k + rank)
    for rank, (doc, score) in enumerate(lexical, start=1):
        c = by_id.setdefault(doc.metadata["chunk_id"], RetrievedChunk(document=doc))
        c.bm25_score, c.bm25_rank = score, rank
        c.fused_score += bm25_weight / (rrf_k + rank)
    return sorted(by_id.values(), key=lambda c: c.fused_score, reverse=True)


def retrieve(
    query: str,
    filters: QueryFilters | None = None,
    top_k: int | None = None,
    rerank: bool = True,
) -> RetrievalResult:
    s = get_settings()
    top_k = top_k or s.top_k
    plan = plan_filters(filters)
    reranker = get_reranker(rerank)
    if plan.matches_nothing:
        return RetrievalResult([], 0, 0, 0, reranker.name)

    semantic = semantic_search(query, s.candidate_k, plan.where)
    lexical = get_bm25_index().search(query, s.candidate_k, plan.predicate)
    fused = fuse(semantic, lexical, s.semantic_weight, s.bm25_weight, s.rrf_k)[: s.candidate_k]

    ranked = reranker.rerank(query, fused)
    return RetrievalResult(
        chunks=ranked[:top_k],
        semantic_candidates=len(semantic),
        bm25_candidates=len(lexical),
        fused_candidates=len(fused),
        reranker=reranker.name,
    )
