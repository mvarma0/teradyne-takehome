"""Grounded answer generation with numbered [n] citations to retrieved chunks."""

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.llm.factory import get_llm
from app.retrieval.types import RetrievedChunk

NO_CONTEXT_ANSWER = "No relevant information was found in the ingested documents."

_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You answer questions for FastChip Semiconductor employees using ONLY the numbered "
            "context excerpts. Cite every factual statement with the excerpt number in square "
            "brackets, e.g. [1] or [2][3]. If the excerpts do not contain the answer, say so "
            "plainly and do not guess. Be concise (at most ~150 words).",
        ),
        ("human", "Context:\n{context}\n\nQuestion: {query}"),
    ]
)


def format_context(chunks: list[RetrievedChunk]) -> str:
    blocks = []
    for i, c in enumerate(chunks, start=1):
        m = c.document.metadata
        people = m.get("attendees") or m.get("authors") or "unknown"
        blocks.append(
            f"[{i}] source: {m['source_file']} | {m.get('title')} | {m.get('date') or 'undated'}"
            f" | people: {people}\n{c.document.page_content}"
        )
    return "\n\n".join(blocks)


def generate_answer(query: str, chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return NO_CONTEXT_ANSWER
    chain = _PROMPT | get_llm() | StrOutputParser()
    return chain.invoke({"query": query, "context": format_context(chunks)}).strip()
