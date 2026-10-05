from app.ingestion.chunking import chunk_document, count_tokens, split_sections
from app.models.enrichment import EnrichmentResult
from app.models.source import SourceDoc
from app.state import reset_all

ENRICHMENT = EnrichmentResult(
    topic_domain="yield",
    priority="high",
    products=["Eagle-5"],
    summary="s",
    key_topics=[],
    decisions=[],
    action_items=[],
)


def _src(content: str) -> SourceDoc:
    return SourceDoc(
        doc_id="d1",
        source_file="meetings/m.md",
        source_type="meeting",
        title="T",
        date="2025-01-01",
        attendees=["Sarah Chen"],
        content=content,
        content_hash="h",
    )


def test_sections_follow_headings_and_merge_small_ones():
    md = "# Title\n\n## A\n\n" + "alpha " * 120 + "\n\n## B\n\n" + "beta " * 120
    sections = split_sections(md)
    # "# Title" alone is under the min size, so it merges into its child section A.
    assert [p for p, _ in sections] == ["Title > A", "Title > B"]
    assert "alpha" in sections[0][1] and "beta" not in sections[0][1]


def test_oversized_section_split_recursively_within_budget(monkeypatch):
    monkeypatch.setenv("CHUNK_MAX_TOKENS", "120")
    monkeypatch.setenv("CHUNK_OVERLAP_TOKENS", "10")
    reset_all()
    turns = "\n\n".join(f"Speaker {i}: " + "yield data point " * 20 for i in range(8))
    chunks = chunk_document(_src(f"## Discussion\n\n{turns}"), ENRICHMENT)
    assert len(chunks) > 1
    header_tokens = 20
    assert all(count_tokens(c.page_content) <= 120 + header_tokens for c in chunks)
    # Turns fit the budget, so splits land on turn boundaries: every turn survives whole.
    for turn in turns.split("\n\n"):
        assert any(turn.strip() in c.page_content for c in chunks)


def test_small_section_kept_whole_with_metadata():
    chunks = chunk_document(_src("## Decisions\n\n- Hold lot 4412."), ENRICHMENT)
    assert len(chunks) == 1
    c = chunks[0]
    assert c.page_content.startswith("[T | 2025-01-01 | Decisions]")
    assert c.metadata["chunk_id"] == "d1:000"
    assert c.metadata["attendees"] == "Sarah Chen"
    assert c.metadata["topic_domain"] == "yield"
    assert c.metadata["products"] == "Eagle-5"
