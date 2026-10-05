"""Reset cached singletons (settings, models, vector store, BM25). Used after config changes."""

from app.config import get_settings
from app.ingestion.chunking import _encoding
from app.llm.factory import get_embeddings, get_llm
from app.retrieval.bm25 import invalidate_bm25
from app.retrieval.vectorstore import get_vectorstore


def reset_all() -> None:
    for fn in (get_settings, get_llm, get_embeddings, get_vectorstore, _encoding):
        fn.cache_clear()
    invalidate_bm25()
