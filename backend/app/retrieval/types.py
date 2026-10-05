from dataclasses import dataclass

from langchain_core.documents import Document


@dataclass
class RetrievedChunk:
    document: Document
    semantic_score: float | None = None
    semantic_rank: int | None = None
    bm25_score: float | None = None
    bm25_rank: int | None = None
    fused_score: float = 0.0
    rerank_score: float | None = None

    @property
    def chunk_id(self) -> str:
        return self.document.metadata["chunk_id"]
