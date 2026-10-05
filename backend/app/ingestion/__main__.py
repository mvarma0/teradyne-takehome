"""CLI: uv run python -m app.ingestion [--force] [--dry-run]"""

import argparse
import json
import logging

from app.config import get_settings
from app.db.sqlite import init_db
from app.ingestion.chunking import chunk_document, count_tokens
from app.ingestion.pipeline import discover_sources, run_ingestion
from app.models.enrichment import EnrichmentResult


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
