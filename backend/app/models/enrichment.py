from typing import Literal

from pydantic import BaseModel, Field

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
