"""Ingestion: load -> LLM enrichment -> business rules -> chunking -> Chroma + SQLite.

CLI: uv run python -m app.ingest [--force] [--dry-run]"""

import argparse
import json
import logging
import math
import re
import threading
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

import tiktoken
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from app import db
from app.config import get_settings
from app.db import init_db
from app.llm import collection_name, llm_identity, structured_llm
from app.loaders import (
    iter_document_files,
    iter_meeting_files,
    load_meeting,
    load_office,
    make_doc_id,
)
from app.rules import apply_ingest_rules
from app.schemas import EnrichmentResult, SourceDoc
from app.search import delete_doc_chunks, invalidate_bm25, replace_doc_chunks

# ---- enrich -------------------------------------------------------------------------------
# LLM metadata enrichment with structured output, cached by (content hash, model).

log = logging.getLogger(__name__)

PROMPT_VERSION = "v4"

SYSTEM = """You extract structured metadata from internal documents of a mid-size automotive
semiconductor company (HQ Austin TX, design center Portland OR, fab/test in Penang Malaysia)
that makes automotive microcontrollers and power management ICs.
Key concerns: yield, new product introduction (NPI) ramps, automotive qualification
(AEC-Q100, ISO 26262), customer deadlines, supply chain.

topic_domain (pick one):
- yield: fab/process yield, wafer lots, defect analysis
- design: chip design, design reviews, specs, tape-out, design handoff
- test_engineering: ATE test programs, test coverage, probe/sort, characterization
- npi_program: NPI ramp planning, milestones, gates, cross-functional program status
- supply_chain: vendors, materials, capacity, logistics
- customer: customer escalations, complaints, commitments
- quality_compliance: quality reports, AEC-Q100, audits, reliability
- executive_strategy: company strategy, financials, roadmap, leadership decisions
- other: none of the above

priority:
- critical: customer line-down, safety/AEC-Q100 failure, shipment stop, major revenue at risk
- high: active customer escalation, yield below target with revenue impact, schedule slip
- medium: active issue with mitigation in place, upcoming deadline
- low: routine status, informational
- none: priority not applicable

products: the company's own chips/devices only, exactly as named in the text (e.g.
"Volta-7"). Not customers or other companies, silicon revisions (Rev A, Rev B), sample
stages (ES1, CS), lot/wafer IDs, standards (AEC-Q100) or test names.

Rules: use only facts in the text.
Action item owners must be people named in the text. Do not invent dates."""

HUMAN = """Title: {title}
Date: {date}
Type: {doc_type}
Attendees/authors: {people}

Content:
{content}"""

_PROMPT = ChatPromptTemplate.from_messages([("system", SYSTEM), ("human", HUMAN)])

_PRODUCT_CODE = re.compile(r"^([A-Za-z]+)[\s_-]*(\d+[A-Za-z]?)$")
# Identifiers that small models list as products but are revisions, sample stages, lots or
# standards. The rule is generic (no product names), like the rest of the prompt.
_NOT_PRODUCT = re.compile(
    r"^(?:rev(?:ision)?[\s_-]*[a-z0-9]{1,2}|[ec]s[\s_-]*\d*|lot\b.*|wafer\b.*|aec-?q\d+.*)$",
    re.I,
)


def normalize_product(name: str) -> str:
    """'volta 7' / 'VOLTA7' / 'Volta-7' -> 'Volta-7'; other names are kept as written."""
    name = name.strip()
    if m := _PRODUCT_CODE.match(name):
        return f"{m.group(1).capitalize()}-{m.group(2).upper()}"
    return name


def _normalize(result: EnrichmentResult) -> EnrichmentResult:
    products = dict.fromkeys(
        normalize_product(p)
        for p in result.products
        if p.strip() and not _NOT_PRODUCT.match(p.strip())
    )
    return result.model_copy(update={"products": list(products)})


def enrich(src: SourceDoc, force: bool = False) -> EnrichmentResult:
    cache_key = f"{llm_identity()}:{PROMPT_VERSION}"
    if not force and (cached := db.get_cached_enrichment(src.content_hash, cache_key)):
        return cached
    log.info("enriching %s with %s", src.source_file, cache_key)
    result = (_PROMPT | structured_llm(EnrichmentResult)).invoke(
        {
            "title": src.title,
            "date": src.date or "unknown",
            "doc_type": src.extra.get("meeting_type") or src.source_type,
            "people": ", ".join(src.attendees or src.authors) or "unknown",
            "content": src.content[: get_settings().enrich_max_chars],
        }
    )
    result = _normalize(result)
    db.cache_enrichment(src.content_hash, cache_key, result)
    return result


# ---- chunking -----------------------------------------------------------------------------
# Structure-aware recursive chunking.
#
# 1. Split on markdown headings (h1-h3) so chunks never straddle sections.
# 2. Merge consecutive sections smaller than CHUNK_MIN_TOKENS (avoids heading-only fragments).
# 3. Recursively split only sections above CHUNK_MAX_TOKENS: paragraphs/speaker turns ->
#    lines -> sentences -> clauses -> words. Size is an upper bound, not a fixed width.
#    Markdown tables (spreadsheets, docx tables) split by rows with the header repeated.
# Each chunk is prefixed with a context line (title, date, section path) to help both
# semantic and BM25 retrieval.

_HEADERS = [("#", "h1"), ("##", "h2"), ("###", "h3")]
_SEPARATORS = ["\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " ", ""]


_WORDS = re.compile(r"\w+|[^\w\s]")


@lru_cache(maxsize=1)
def _encoding() -> tiktoken.Encoding | None:
    """cl100k_base, downloaded once by tiktoken; None when offline and not cached."""
    try:
        return tiktoken.get_encoding("cl100k_base")
    except Exception as exc:  # network / proxy errors from the first download
        log.warning("tiktoken encoding unavailable (%s); using an estimated token count", exc)
        return None


def count_tokens(text: str) -> int:
    enc = _encoding()
    if enc is not None:
        return len(enc.encode(text))
    # Offline estimate: ~4 characters per token per word, each punctuation mark one token.
    # It slightly overestimates cl100k, which is safe because budgets are upper bounds.
    return sum(max(1, math.ceil(len(w) / 4)) for w in _WORDS.findall(text))


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


# ---- pipeline -----------------------------------------------------------------------------
# Ingestion: load -> enrich -> business rules -> chunk -> Chroma + SQLite.
#
# Sources: data/meetings/*.md and data/documents/**/*.{docx,pptx,xlsx,doc,ppt,xls}.
# Idempotent per file content hash; files removed from data/ are pruned.

_lock = threading.Lock()

Loader = Callable[[Path, Path], SourceDoc]


@dataclass
class IngestReport:
    collection: str
    files_found: int = 0
    ingested: int = 0
    skipped_unchanged: int = 0
    removed: int = 0
    chunks_written: int = 0
    duration_s: float = 0.0
    by_type: dict = field(default_factory=dict)
    ingested_files: list[str] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def discover_sources() -> tuple[list[tuple[Path, Loader]], list[str]]:
    s = get_settings()
    warnings = []
    sources: list[tuple[Path, Loader]] = []
    for folder, finder, loader in (
        (s.meetings_dir, iter_meeting_files, load_meeting),
        (s.documents_dir, iter_document_files, load_office),
    ):
        if not folder.is_dir():
            warnings.append(f"Folder not found: {folder}")
            continue
        found = finder(folder)
        if not found:
            warnings.append(f"No supported files in {folder}")
        sources += [(p, loader) for p in found]
    return sources, warnings


def run_ingestion(force: bool = False) -> IngestReport:
    if not _lock.acquire(blocking=False):
        raise RuntimeError("An ingestion run is already in progress")
    try:
        return _run(force)
    finally:
        _lock.release()


def _ingest_one(src: SourceDoc, force: bool, collection: str) -> int:
    enrichment = enrich(src, force=force)
    enrichment, applied = apply_ingest_rules(src, enrichment)
    if applied:
        src.extra["rules_applied"] = applied
    chunks = chunk_document(src, enrichment)
    replace_doc_chunks(src.doc_id, chunks)
    db.upsert_document(src, enrichment, collection, len(chunks))
    return len(chunks)


def _run(force: bool) -> IngestReport:
    s = get_settings()
    started = time.perf_counter()
    report = IngestReport(collection=collection_name())
    sources, report.warnings = discover_sources()
    report.files_found = len(sources)
    types: Counter = Counter()

    seen: set[str] = set()
    for i, (path, loader) in enumerate(sources, start=1):
        rel = path.relative_to(s.data_dir).as_posix()
        seen.add(make_doc_id(rel))
        try:
            src = loader(path, s.data_dir)
            types[src.source_type] += 1
            report.warnings += src.extra.pop("warnings", [])
            state = db.get_document_state(src.doc_id)
            unchanged = (
                state
                and state["content_hash"] == src.content_hash
                and state["collection"] == report.collection
            )
            if unchanged and not force:
                report.skipped_unchanged += 1
                log.info("[%d/%d] %s unchanged, skipped", i, len(sources), rel)
                continue
            t0 = time.perf_counter()
            n = _ingest_one(src, force, report.collection)
            report.ingested += 1
            report.chunks_written += n
            report.ingested_files.append(rel)
            log.info(
                "[%d/%d] %s: %d chunks (%.1fs)", i, len(sources), rel, n, time.perf_counter() - t0
            )
            if src.attendees_source == "none":
                report.warnings.append(f"{rel}: no attendees/authors found")
        except Exception as exc:  # keep going; report per-file failures
            log.exception("failed to ingest %s", rel)
            report.failed.append({"file": rel, "error": f"{type(exc).__name__}: {exc}"})

    for stale in set(db.list_all_doc_ids()) - seen:
        delete_doc_chunks(stale)
        db.delete_document(stale)
        report.removed += 1

    invalidate_bm25()
    report.by_type = dict(types)
    report.duration_s = round(time.perf_counter() - started, 2)
    log.info("ingestion finished: %s", report)
    return report


# ---- main ---------------------------------------------------------------------------------
# CLI: uv run python -m app.ingest [--force] [--dry-run]


def dry_run() -> None:
    """Parse + chunk without calling any model; prints what would be ingested."""
    s = get_settings()
    placeholder = EnrichmentResult(
        topic_domain="other",
        priority="none",
        products=[],
        summary="",
        key_topics=[],
        decisions=[],
        action_items=[],
    )
    sources, warnings = discover_sources()
    print(f"{len(sources)} source files under {s.data_dir}")
    for w in warnings:
        print(f"warning: {w}")
    for path, loader in sources:
        src = loader(path, s.data_dir)
        chunks = chunk_document(src, placeholder)
        sizes = [count_tokens(c.page_content) for c in chunks]
        print(
            json.dumps(
                {
                    "file": src.source_file,
                    "title": src.title,
                    "date": src.date,
                    "type": src.source_type,
                    "attendees": src.attendees,
                    "authors": src.authors,
                    "people_source": src.attendees_source,
                    "format": src.extra.get("format", "markdown"),
                    "chunks": len(chunks),
                    "chunk_tokens": sizes,
                }
            )
        )


def main() -> None:
    ap = argparse.ArgumentParser(description="Ingest data/ into SQLite + ChromaDB")
    ap.add_argument("--force", action="store_true", help="re-enrich and re-embed everything")
    ap.add_argument("--dry-run", action="store_true", help="parse and chunk only (no models)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if args.dry_run:
        dry_run()
        return
    init_db()
    print(json.dumps(run_ingestion(force=args.force).to_dict(), indent=2))


if __name__ == "__main__":
    main()
