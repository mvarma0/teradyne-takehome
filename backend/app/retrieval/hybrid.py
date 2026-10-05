"""Hybrid retrieval: semantic (Chroma) + BM25 -> weighted Reciprocal Rank Fusion -> rerank."""

from collections.abc import Callable
from dataclasses import dataclass

from langchain_core.documents import Document

from app.config import get_settings
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


def chroma_where(filters: QueryFilters | None) -> dict | None:
    if not filters:
        return None
    clauses = [{k: getattr(filters, k)} for k in _SCALAR_FILTERS if getattr(filters, k)]
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


def make_predicate(filters: QueryFilters | None) -> Callable[[Document], bool]:
    def predicate(doc: Document) -> bool:
        if not filters:
            return True
        m = doc.metadata
        for key in _SCALAR_FILTERS:
            want = getattr(filters, key)
            if want and m.get(key) != want:
                return False
        if filters.person and filters.person.lower() not in m.get("people", ""):
            return False
        date = m.get("date") or ""
        if filters.date_from and (not date or date < filters.date_from):
            return False
        if filters.date_to and (not date or date > filters.date_to):
            return False
        return True

    return predicate


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
    predicate = make_predicate(filters)

    semantic = [
        (d, sc)
        for d, sc in semantic_search(query, s.candidate_k, chroma_where(filters))
        if predicate(d)
    ]
    lexical = get_bm25_index().search(query, s.candidate_k, predicate)
    fused = fuse(semantic, lexical, s.semantic_weight, s.bm25_weight, s.rrf_k)[: s.candidate_k]

    reranker = get_reranker(rerank)
    ranked = reranker.rerank(query, fused)
    return RetrievalResult(
        chunks=ranked[:top_k],
        semantic_candidates=len(semantic),
        bm25_candidates=len(lexical),
        fused_candidates=len(fused),
        reranker=reranker.name,
    )
