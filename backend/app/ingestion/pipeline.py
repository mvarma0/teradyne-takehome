"""Ingestion: load -> enrich -> business rules -> chunk -> Chroma + SQLite.

Sources: data/meetings/*.md and data/documents/**/*.{docx,pptx,xlsx,doc,ppt,xls}.
Idempotent per file content hash; files removed from data/ are pruned.
"""

import logging
import threading
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.answer.business_rules import apply_ingest_rules
from app.config import get_settings
from app.db import repository
from app.ingestion.chunking import chunk_document
from app.ingestion.enrich import enrich
from app.ingestion.loaders.meeting import iter_meeting_files, load_meeting, make_doc_id
from app.ingestion.loaders.office import iter_document_files, load_office
from app.llm.factory import collection_name
from app.models.source import SourceDoc
from app.retrieval.bm25 import invalidate_bm25
from app.retrieval.vectorstore import delete_doc_chunks, replace_doc_chunks

log = logging.getLogger(__name__)
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
    repository.upsert_document(src, enrichment, collection, len(chunks))
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
            state = repository.get_document_state(src.doc_id)
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

    for stale in set(repository.list_all_doc_ids()) - seen:
        delete_doc_chunks(stale)
        repository.delete_document(stale)
        report.removed += 1

    invalidate_bm25()
    report.by_type = dict(types)
    report.duration_s = round(time.perf_counter() - started, 2)
    log.info("ingestion finished: %s", report)
    return report
