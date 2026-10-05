"""Hybrid retrieval: metadata pre-filter -> semantic (Chroma) + BM25 -> weighted Reciprocal
Rank Fusion -> rerank."""

from dataclasses import dataclass, field

from langchain_core.documents import Document

from app.config import get_settings
from app.db import repository
from app.models.api import QueryFilters
from app.retrieval.bm25 import get_bm25_index
from app.retrieval.rerank import get_reranker
from app.retrieval.types import RetrievedChunk
from app.retrieval.vectorstore import semantic_search

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
        allowed = repository.find_doc_ids(
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
