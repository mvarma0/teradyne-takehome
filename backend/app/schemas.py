"""Schemas shared across the app: source documents, enrichment, API bodies, retrieved chunks."""

from dataclasses import dataclass
from typing import Literal

from langchain_core.documents import Document
from pydantic import BaseModel, Field

# ---- source -------------------------------------------------------------------------------


class SourceDoc(BaseModel):
    """A loaded source file. People/date/title fields are parsed deterministically, never by LLM."""

    doc_id: str
    source_file: str  # relative to DATA_DIR
    source_type: str  # "meeting" (Exercise 2 adds docx / pptx / xlsx)
    title: str
    date: str | None = None  # ISO yyyy-mm-dd when parseable
    attendees: list[str] = Field(default_factory=list)
    attendees_source: str = "none"  # frontmatter | header | speakers | none
    authors: list[str] = Field(default_factory=list)
    content: str  # normalized markdown (docling output) used for chunking + enrichment
    content_hash: str  # sha256 of the raw file
    extra: dict = Field(default_factory=dict)


# ---- enrichment ---------------------------------------------------------------------------

TopicDomain = Literal[
    "yield",
    "design",
    "test_engineering",
    "npi_program",
    "supply_chain",
    "customer",
    "quality_compliance",
    "executive_strategy",
    "other",
]
Priority = Literal["critical", "high", "medium", "low", "none"]


class ActionItem(BaseModel):
    owner: str = Field(
        description="Person responsible, as named in the text ('unassigned' if none)"
    )
    task: str = Field(description="What must be done")
    due_date: str | None = Field(
        description="Due date exactly as written in the text (e.g. 'March 7', 'this week'), "
        "else null. Never compute or infer a date."
    )


class EnrichmentResult(BaseModel):
    """LLM-derived metadata for one source document."""

    topic_domain: TopicDomain = Field(description="Single best-fitting business domain")
    priority: Priority = Field(description="Business urgency; 'none' if not applicable")
    products: list[str] = Field(description="Product names discussed, exactly as named in the text")
    summary: str = Field(description="2-3 sentence factual summary")
    key_topics: list[str] = Field(description="3-6 short topic tags")
    decisions: list[str] = Field(description="Decisions explicitly made")
    action_items: list[ActionItem] = Field(description="Action items explicitly assigned")


# ---- api ----------------------------------------------------------------------------------


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
    author_roles: dict[str, str] = Field(default_factory=dict)
    reviewers: list[str] = Field(default_factory=list)
    format: str | None = None
    pages: int | None = None
    rules_applied: list[str] = Field(default_factory=list)
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


class IngestRequest(BaseModel):
    force: bool = Field(False, description="Re-enrich and re-embed even if unchanged")


class ChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None
    filters: QueryFilters | None = None
    top_k: int | None = Field(None, ge=1, le=20)
    rerank: bool = True


class CorrectBody(BaseModel):
    correction: str = Field(min_length=1)
    submitted_by: str | None = None


class RejectBody(BaseModel):
    reason: str | None = None
    submitted_by: str | None = None


class FeedbackBody(BaseModel):
    rating: Literal["up", "down"] | None


class SendRoutingBody(BaseModel):
    question: str = Field(min_length=1)
    sent_by: str | None = None


class ReviewBody(BaseModel):
    review_status: Literal["pending", "reviewed", "resolved"]
    reviewer_note: str | None = None


class RenameBody(BaseModel):
    title: str = Field(min_length=1, max_length=80)


class EvalRunBody(BaseModel):
    dataset: Literal["golden", "synthetic", "all"] = "golden"


class SynthesizeBody(BaseModel):
    n: int = Field(20, ge=1, le=100)


# ---- types --------------------------------------------------------------------------------


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
