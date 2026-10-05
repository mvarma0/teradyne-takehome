from typing import Literal

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
