"""Answer confidence in [0, 1] from retrieval strength and citation grounding."""

from app.answer.citations import ClaimsResult
from app.config import get_settings
from app.retrieval.types import RetrievedChunk


def score_confidence(chunks: list[RetrievedChunk], claims: ClaimsResult) -> dict:
    if not chunks:
        return {"confidence": 0.0, "components": {}}
    semantic = sorted((c.semantic_score or 0.0 for c in chunks), reverse=True)
    reranked = [c.rerank_score for c in chunks if c.rerank_score is not None]
    top_semantic = semantic[0]
    sem_mean = sum(semantic[:3]) / min(3, len(semantic))
    retrieval = max(reranked) / 10 if reranked else top_semantic

    components = {
        "retrieval": round(retrieval, 3),
        "semantic_top3": round(sem_mean, 3),
        "citation_coverage": round(claims.coverage, 3),
        "has_support": 1.0 if claims.facts else 0.0,
    }
    conf = (
        0.4 * retrieval + 0.2 * sem_mean + 0.3 * claims.coverage + 0.1 * components["has_support"]
    )
    caps = []
    if claims.insufficient:
        conf = min(conf, 0.25)
        caps.append("answer_insufficient")
    if top_semantic < get_settings().min_retrieval_score:
        conf = min(conf, 0.3)
        caps.append("weak_retrieval")
    return {
        "confidence": round(max(0.0, min(1.0, conf)), 3),
        "components": components,
        "caps": caps,
        "top_semantic": round(top_semantic, 3),
        "top_rerank": max(reranked) if reranked else None,
    }
