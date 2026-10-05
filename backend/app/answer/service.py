"""Query orchestration: retrieve -> (answer) -> attach derived document metadata."""

import time

from app.answer.generate import generate_answer
from app.db import repository
from app.models.api import (
    ChunkScores,
    DocumentMetadata,
    QueryRequest,
    QueryResponse,
    ResultItem,
    RetrievalStats,
)
from app.retrieval.hybrid import retrieve


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()] if value else []


def run_query(req: QueryRequest) -> QueryResponse:
    started = time.perf_counter()
    result = retrieve(req.query, req.filters, req.top_k, req.rerank)

    results = []
    for rank, c in enumerate(result.chunks, start=1):
        m = c.document.metadata
        results.append(
            ResultItem(
                rank=rank,
                chunk_id=c.chunk_id,
                doc_id=m["doc_id"],
                text=c.document.page_content,
                section=m.get("section") or None,
                source_file=m["source_file"],
                source_type=m["source_type"],
                title=m.get("title", ""),
                date=m.get("date") or None,
                attendees=_split(m.get("attendees", "")),
                topic_domain=m.get("topic_domain"),
                priority=m.get("priority"),
                products=_split(m.get("products", "")),
                scores=ChunkScores(
                    semantic=c.semantic_score,
                    semantic_rank=c.semantic_rank,
                    bm25=c.bm25_score,
                    bm25_rank=c.bm25_rank,
                    fused=c.fused_score,
                    rerank=c.rerank_score,
                ),
            )
        )

    doc_ids = list(dict.fromkeys(r.doc_id for r in results))
    docs = repository.get_documents(doc_ids)
    documents = [DocumentMetadata(**docs[d]) for d in doc_ids if d in docs]

    answer = generate_answer(req.query, result.chunks) if req.generate_answer else None
    return QueryResponse(
        query=req.query,
        answer=answer,
        results=results,
        documents=documents,
        retrieval=RetrievalStats(
            semantic_candidates=result.semantic_candidates,
            bm25_candidates=result.bm25_candidates,
            fused_candidates=result.fused_candidates,
            reranker=result.reranker,
            latency_ms=int((time.perf_counter() - started) * 1000),
        ),
    )
