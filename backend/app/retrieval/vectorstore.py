"""ChromaDB wrapper (cosine space; relevance = 1 - cosine distance)."""

from functools import lru_cache

from langchain_chroma import Chroma
from langchain_core.documents import Document

from app.config import get_settings
from app.llm.factory import collection_name, get_embeddings


@lru_cache(maxsize=1)
def get_vectorstore() -> Chroma:
    s = get_settings()
    s.chroma_dir.mkdir(parents=True, exist_ok=True)
    return Chroma(
        collection_name=collection_name(),
        embedding_function=get_embeddings(),
        persist_directory=str(s.chroma_dir),
        collection_metadata={"hnsw:space": "cosine"},
    )


def delete_doc_chunks(doc_id: str) -> None:
    vs = get_vectorstore()
    ids = vs.get(where={"doc_id": doc_id}, include=["metadatas"])["ids"]
    if ids:
        vs.delete(ids=ids)


def replace_doc_chunks(doc_id: str, chunks: list[Document]) -> None:
    delete_doc_chunks(doc_id)
    if chunks:
        get_vectorstore().add_documents(chunks, ids=[c.metadata["chunk_id"] for c in chunks])


def count_chunks() -> int:
    return get_vectorstore()._collection.count()


def all_chunks() -> list[Document]:
    got = get_vectorstore().get(include=["documents", "metadatas"])
    return [
        Document(id=i, page_content=d, metadata=m)
        for i, d, m in zip(got["ids"], got["documents"], got["metadatas"], strict=True)
    ]


def semantic_search(query: str, k: int, where: dict | None) -> list[tuple[Document, float]]:
    if count_chunks() == 0:
        return []
    pairs = get_vectorstore().similarity_search_with_score(query, k=k, filter=where)
    return [(doc, 1.0 - dist) for doc, dist in pairs]
