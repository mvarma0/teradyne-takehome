"""Structure-aware recursive chunking.

1. Split on markdown headings (h1-h3) so chunks never straddle sections.
2. Merge consecutive sections smaller than CHUNK_MIN_TOKENS (avoids heading-only fragments).
3. Recursively split only sections above CHUNK_MAX_TOKENS: paragraphs/speaker turns ->
   lines -> sentences -> clauses -> words. Size is an upper bound, not a fixed width.
   Markdown tables (spreadsheets, docx tables) split by rows with the header repeated.
Each chunk is prefixed with a context line (title, date, section path) to help both
semantic and BM25 retrieval.
"""

import re
from functools import lru_cache

import tiktoken
from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from app.config import get_settings
from app.models.enrichment import EnrichmentResult
from app.models.source import SourceDoc

_HEADERS = [("#", "h1"), ("##", "h2"), ("###", "h3")]
_SEPARATORS = ["\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " ", ""]


@lru_cache(maxsize=1)
def _encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_encoding().encode(text))


def _section_path(meta: dict) -> str:
    return " > ".join(meta[k] for k in ("h1", "h2", "h3") if meta.get(k))


def split_sections(markdown: str) -> list[tuple[str, str]]:
    """Return (section_path, text) pairs, merging undersized neighbours."""
    splitter = MarkdownHeaderTextSplitter(headers_to_split_on=_HEADERS, strip_headers=False)
    sections = [
        (_section_path(d.metadata), d.page_content.strip()) for d in splitter.split_text(markdown)
    ]
    sections = [(p, t) for p, t in sections if t]
    min_tokens = get_settings().chunk_min_tokens

    merged: list[tuple[str, str]] = []
    for path, text in sections:
        if merged and count_tokens(merged[-1][1]) < min_tokens:
            prev_path, prev_text = merged[-1]
            # Label the merged chunk with the path of its dominant (larger) section.
            keep = path if count_tokens(text) >= count_tokens(prev_text) else prev_path
            merged[-1] = (keep, f"{prev_text}\n\n{text}")
        else:
            merged.append((path, text))
    return merged


def _recursive_splitter() -> RecursiveCharacterTextSplitter:
    s = get_settings()
    return RecursiveCharacterTextSplitter(
        chunk_size=s.chunk_max_tokens,
        chunk_overlap=s.chunk_overlap_tokens,
        length_function=count_tokens,
        separators=_SEPARATORS,
        keep_separator="end",
    )


_TABLE_ROW = re.compile(r"^\s*\|")


def _blocks(text: str) -> list[tuple[bool, str]]:
    """Split text into (is_table, block) runs of markdown-table vs other lines."""
    blocks: list[tuple[bool, list[str]]] = []
    for line in text.splitlines():
        is_table = bool(_TABLE_ROW.match(line))
        if blocks and blocks[-1][0] == is_table:
            blocks[-1][1].append(line)
        else:
            blocks.append((is_table, [line]))
    return [(t, "\n".join(lines).strip()) for t, lines in blocks if "\n".join(lines).strip()]


def split_table(table: str, max_tokens: int) -> list[str]:
    """Split a markdown table by rows, repeating the header row + separator in every piece."""
    lines = table.splitlines()
    header, rows = lines[:2], lines[2:]
    pieces, current = [], list(header)
    for row in rows:
        if len(current) > 2 and count_tokens("\n".join([*current, row])) > max_tokens:
            pieces.append("\n".join(current))
            current = list(header)
        current.append(row)
    pieces.append("\n".join(current))
    return pieces


def split_oversized(text: str, max_tokens: int) -> list[str]:
    """Recursive split for prose; row-wise split (header kept) for tables."""
    splitter = _recursive_splitter()
    out: list[str] = []
    for is_table, block in _blocks(text):
        if count_tokens(block) <= max_tokens:
            out.append(block)
        elif is_table:
            out += split_table(block, max_tokens)
        else:
            out += [t.strip() for t in splitter.split_text(block) if t.strip()]
    # Re-merge neighbouring small blocks so prose + its table stay together when they fit.
    merged: list[str] = []
    for piece in out:
        if merged and count_tokens(f"{merged[-1]}\n\n{piece}") <= max_tokens:
            merged[-1] = f"{merged[-1]}\n\n{piece}"
        else:
            merged.append(piece)
    return merged


def chunk_document(src: SourceDoc, enrichment: EnrichmentResult) -> list[Document]:
    max_tokens = get_settings().chunk_max_tokens
    pieces: list[tuple[str, str]] = []
    for path, text in split_sections(src.content):
        if count_tokens(text) <= max_tokens:
            pieces.append((path, text))
        else:
            pieces += [(path, t) for t in split_oversized(text, max_tokens)]

    people = ", ".join(src.attendees or src.authors)
    docs = []
    for i, (path, text) in enumerate(pieces):
        header = f"[{src.title} | {src.date or 'undated'}{f' | {path}' if path else ''}]"
        docs.append(
            Document(
                page_content=f"{header}\n{text}",
                metadata={
                    "chunk_id": f"{src.doc_id}:{i:03d}",
                    "doc_id": src.doc_id,
                    "chunk_index": i,
                    "source_file": src.source_file,
                    "source_type": src.source_type,
                    "title": src.title,
                    "date": src.date or "",
                    "section": path,
                    "attendees": ", ".join(src.attendees),
                    "authors": ", ".join(src.authors),
                    "people": people.lower(),
                    "topic_domain": enrichment.topic_domain,
                    "priority": enrichment.priority,
                    "products": ", ".join(enrichment.products),
                    "meeting_type": src.extra.get("meeting_type") or "",
                },
            )
        )
    return docs
