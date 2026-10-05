from langchain_core.documents import Document

from app.models.api import QueryFilters
from app.retrieval.bm25 import BM25Index, tokenize
from app.retrieval.hybrid import chroma_where, fuse, make_predicate


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


def test_filters():
    f = QueryFilters(topic_domain="yield", person="marcus", date_from="2025-03-01")
    assert chroma_where(f) == {"topic_domain": "yield"}
    pred = make_predicate(f)
    ok = _doc("a", "", topic_domain="yield", people="sarah chen, marcus rivera", date="2025-03-04")
    assert pred(ok)
    assert not pred(_doc("b", "", topic_domain="yield", people="sarah chen", date="2025-03-04"))
    assert not pred(_doc("c", "", topic_domain="yield", people="marcus", date="2025-02-01"))
    two = QueryFilters(topic_domain="yield", priority="high")
    assert chroma_where(two) == {"$and": [{"topic_domain": "yield"}, {"priority": "high"}]}
