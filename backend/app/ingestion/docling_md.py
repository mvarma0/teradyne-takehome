"""Docling-based markdown normalization.

Docling parses markdown into a DoclingDocument and re-exports clean markdown. Before that:
- standalone section labels in plain-text transcripts ("Discussion", "Action Items") are
  promoted to "## " headings so the structure-aware chunker can split on them;
- speaker turns / label lines get a blank line first, because docling merges soft line
  breaks into paragraphs; this keeps them as separate paragraphs (natural split points).
"""

import re
from functools import lru_cache
from io import BytesIO

from app.config import get_settings

# "**Sarah Chen:** ...", "Sarah Chen: ...", "**Decision:** ..." at line start
_TURN_LINE = re.compile(
    r"^\s*(?:\*\*|__)?[A-Z][\w.'\-]*(?:\s[A-Z][\w.'\-]*){0,3}\s*(?::\s*(?:\*\*|__)|(?:\*\*|__)?:)"
)

_SECTION_LABELS = (
    "agenda|attendees|participants|discussion|discussion points|notes|meeting notes|summary|"
    "decisions|key decisions|decisions made|action items|actions|next steps|follow-ups|"
    "open issues|risks|risks and issues|updates|status updates|key takeaways|background"
)
_SECTION_LINE = re.compile(rf"^\s*(?:\*\*|__)?({_SECTION_LABELS})(?:\*\*|__)?\s*:?\s*$", re.I)


def promote_section_labels(md: str) -> str:
    """'Decisions' on its own line -> '## Decisions' (lines already headings are untouched)."""
    lines = md.splitlines()
    for i, line in enumerate(lines):
        if m := _SECTION_LINE.match(line):
            lines[i] = f"## {m.group(1).strip()}"
    return "\n".join(lines)


def separate_turns(md: str) -> str:
    out: list[str] = []
    for line in md.splitlines():
        starts_block = _TURN_LINE.match(line) or line.startswith("#")
        if starts_block and out and out[-1].strip():
            out.append("")
        out.append(line)
    return "\n".join(out)


@lru_cache(maxsize=1)
def _converter():
    from docling.datamodel.base_models import InputFormat
    from docling.document_converter import DocumentConverter

    return DocumentConverter(allowed_formats=[InputFormat.MD])


def normalize_markdown(md: str, name: str = "document.md") -> str:
    md = separate_turns(promote_section_labels(md))
    if not get_settings().use_docling:
        return md
    from docling.datamodel.base_models import DocumentStream

    stream = DocumentStream(
        name=name if name.endswith(".md") else f"{name}.md", stream=BytesIO(md.encode())
    )
    return _converter().convert(stream).document.export_to_markdown()
