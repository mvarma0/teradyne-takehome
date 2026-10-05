"""In-memory BM25 index over all Chroma chunks; rebuilt lazily after ingestion."""

import re
import threading
from collections.abc import Callable

from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from app.llm.factory import collection_name
from app.retrieval.vectorstore import all_chunks

_STOPWORDS = frozenset(
    "a an and are as at be by did do does for from has have how in is it its of on or "
    "that the this to was were what when where which who why will with".split()
)
_TOKEN = re.compile(r"[a-z0-9]+(?:[-.][a-z0-9]+)*")


def tokenize(text: str) -> list[str]:
    """Lowercase tokens; compound terms like 'eagle-5' also emit their parts."""
    tokens: list[str] = []
    for tok in _TOKEN.findall(text.lower()):
        if tok in _STOPWORDS:
            continue
        tokens.append(tok)
        if "-" in tok or "." in tok:
            tokens += [p for p in re.split(r"[-.]", tok) if p and p not in _STOPWORDS]
    return tokens


class BM25Index:
    def __init__(self, docs: list[Document]) -> None:
        self.docs = docs
        self._tokens = [set(tokenize(d.page_content)) for d in docs]
        self._bm25 = BM25Okapi([tokenize(d.page_content) for d in docs]) if docs else None

    def search(
        self, query: str, k: int, predicate: Callable[[Document], bool] | None = None
    ) -> list[tuple[Document, float]]:
        q = tokenize(query)
        if not self._bm25 or not q:
            return []
        scores = self._bm25.get_scores(q)
        q_set = set(q)
        ranked = sorted(range(len(self.docs)), key=lambda i: scores[i], reverse=True)
        out: list[tuple[Document, float]] = []
        for i in ranked:
            if not (self._tokens[i] & q_set):
                continue  # require lexical overlap
            if predicate and not predicate(self.docs[i]):
                continue
            out.append((self.docs[i], float(scores[i])))
            if len(out) >= k:
                break
        return out


_lock = threading.Lock()
_index: tuple[str, BM25Index] | None = None


def get_bm25_index() -> BM25Index:
    global _index
    with _lock:
        name = collection_name()
        if _index is None or _index[0] != name:
            _index = (name, BM25Index(all_chunks()))
        return _index[1]


def invalidate_bm25() -> None:
    global _index
    with _lock:
        _index = None
