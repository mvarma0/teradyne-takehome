from pydantic import BaseModel, Field

from app.models.enrichment import ActionItem


class QueryFilters(BaseModel):
    topic_domain: str | None = None
    priority: str | None = None
    source_type: str | None = None
    person: str | None = Field(
        None, description="Attendee/author name (substring, case-insensitive)"
    )
    date_from: str | None = Field(None, description="ISO date, inclusive")
    date_to: str | None = Field(None, description="ISO date, inclusive")


class QueryRequest(BaseModel):
    query: str = Field(min_length=1)
    filters: QueryFilters | None = None
    top_k: int | None = Field(None, ge=1, le=20)
    rerank: bool = True
    generate_answer: bool = True


class ChunkScores(BaseModel):
    semantic: float | None = None
    semantic_rank: int | None = None
    bm25: float | None = None
    bm25_rank: int | None = None
    fused: float
    rerank: float | None = None


class ResultItem(BaseModel):
    rank: int
    chunk_id: str
    doc_id: str
    text: str
    section: str | None
    source_file: str
    source_type: str
    title: str
    date: str | None
    attendees: list[str]
    topic_domain: str | None
    priority: str | None
    products: list[str]
    scores: ChunkScores


class DocumentMetadata(BaseModel):
    doc_id: str
    source_file: str
    source_type: str
    title: str | None
    date: str | None
    attendees: list[str]
    attendees_source: str | None
    attendee_roles: dict[str, str] = Field(default_factory=dict)
    authors: list[str]
    meeting_type: str | None = None
    location: str | None = None
    topic_domain: str | None
    priority: str | None
    products: list[str]
    key_topics: list[str]
    summary: str | None
    decisions: list[str]
    action_items: list[ActionItem]
    n_chunks: int
    ingested_at: str


class RetrievalStats(BaseModel):
    semantic_candidates: int
    bm25_candidates: int
    fused_candidates: int
    reranker: str
    latency_ms: int


class QueryResponse(BaseModel):
    query: str
    answer: str | None
    results: list[ResultItem]
    documents: list[DocumentMetadata]
    retrieval: RetrievalStats


class IngestRequest(BaseModel):
    force: bool = Field(False, description="Re-enrich and re-embed even if unchanged")
