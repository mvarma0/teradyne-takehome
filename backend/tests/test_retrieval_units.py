from langchain_core.documents import Document

from app.db import repository
from app.db.sqlite import init_db
from app.models.api import QueryFilters
from app.models.enrichment import EnrichmentResult
from app.models.source import SourceDoc
from app.retrieval.bm25 import BM25Index, tokenize
from app.retrieval.hybrid import fuse, plan_filters, retrieve


def _doc(cid: str, text: str, **meta) -> Document:
    return Document(page_content=text, metadata={"chunk_id": cid, **meta})


def test_tokenize_keeps_compound_terms_and_parts():
    assert tokenize("The Eagle-5 yield") == ["eagle-5", "eagle", "5", "yield"]


def test_bm25_ranks_exact_term_and_requires_overlap():
    docs = [
        _doc("a", "Lot 4412 failed etch inspection"),
        _doc("b", "Falcon-7 tape-out schedule"),
        _doc("c", "Vendor scorecard for substrates"),
    ]
    hits = BM25Index(docs).search("what happened to lot 4412", k=5)
    assert [d.metadata["chunk_id"] for d, _ in hits] == ["a"]


def test_rrf_fusion_rewards_agreement():
    a, b, c = _doc("a", "x"), _doc("b", "y"), _doc("c", "z")
    fused = fuse([(a, 0.9), (b, 0.8)], [(b, 5.0), (c, 3.0)], 1.0, 1.0, 60)
    assert [x.chunk_id for x in fused] == ["b", "a", "c"]
    assert fused[0].semantic_rank == 2 and fused[0].bm25_rank == 1


def _store(doc_id: str, attendees: list[str], date: str, topic: str) -> None:
    src = SourceDoc(
        doc_id=doc_id,
        source_file=f"meetings/{doc_id}.md",
        source_type="meeting",
        title=doc_id,
        date=date,
        attendees=attendees,
        content="x",
        content_hash=doc_id,
    )
    enr = EnrichmentResult(
        topic_domain=topic,
        priority="high",
        products=[],
        summary="",
        key_topics=[],
        decisions=[],
        action_items=[],
    )
    repository.upsert_document(src, enr, "c", 1)


def test_pre_filter_plan_resolves_person_and_date_to_doc_ids():
    init_db()
    _store("d1", ["Lisa Park", "Mike Chen"], "2024-01-08", "yield")
    _store("d2", ["Lisa Park"], "2024-02-20", "design")
    _store("d3", ["Sara Nolan"], "2024-01-15", "yield")

    plan = plan_filters(QueryFilters(topic_domain="yield", person="lisa", date_to="2024-01-31"))
    assert plan.allowed_doc_ids == {"d1"}
    assert plan.where == {"$and": [{"topic_domain": "yield"}, {"doc_id": {"$in": ["d1"]}}]}
    assert plan.predicate(_doc("a", "", doc_id="d1", topic_domain="yield"))
    assert not plan.predicate(_doc("b", "", doc_id="d3", topic_domain="yield"))

    assert plan_filters(QueryFilters(priority="high")).where == {"priority": "high"}
    assert plan_filters(QueryFilters(date_from="2024-02-01")).allowed_doc_ids == {"d2"}
    assert plan_filters(None).where is None


def test_unmatched_filter_returns_nothing_instead_of_searching_everything():
    init_db()
    _store("d1", ["Lisa Park"], "2024-01-08", "yield")
    assert plan_filters(QueryFilters(person="nobody")).matches_nothing
    assert retrieve("yield", QueryFilters(person="nobody")).chunks == []
