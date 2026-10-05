from pydantic import BaseModel, Field


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
