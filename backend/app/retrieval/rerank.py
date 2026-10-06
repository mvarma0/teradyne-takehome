"""Rerankers.

'llm' is a pointwise LLM judge: each fused candidate gets its own relevance call (run
concurrently with ``batch``), so scores can never be misaligned with passages, which
listwise prompts suffer from on small local models. Works with any configured provider.
'none' keeps the fused order.
"""

import logging
from typing import Protocol

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.config import get_settings
from app.llm.factory import structured_llm
from app.retrieval.types import RetrievedChunk

log = logging.getLogger(__name__)


class RelevanceJudgement(BaseModel):
    reason: str = Field(description="One short sentence: what in the passage relates to the query")
    relevance: int = Field(
        description="0 = unrelated, 3 = same topic but does not answer, "
        "7 = partially answers, 10 = directly answers the query"
    )


_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You judge search relevance for FastChip Semiconductor's internal knowledge base. "
            "Rate how well the passage helps answer the query on a 0-10 scale. Judge the "
            "information, not the wording: if the passage contains the facts needed to answer "
            "(e.g. who is assigned a task answers 'who owns' it), score it high. Products are "
            "different things: a passage about Eagle-5 does not answer a Falcon-7 question.",
        ),
        ("human", "Query: {query}\n\nPassage:\n{passage}"),
    ]
)


class Reranker(Protocol):
    name: str

    def rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]: ...


class NoopReranker:
    name = "none"

    def rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        return chunks


class LLMReranker:
    name = "llm"

    def rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        s = get_settings()
        head, tail = chunks[: s.rerank_top_n], chunks[s.rerank_top_n :]
        if len(head) <= 1:
            return chunks
        inputs = [
            {"query": query, "passage": c.document.page_content[: s.rerank_max_chars]} for c in head
        ]
        chain = _PROMPT | structured_llm(RelevanceJudgement)
        results = chain.batch(
            inputs, config={"max_concurrency": s.rerank_concurrency}, return_exceptions=True
        )
        failures = 0
        for chunk, res in zip(head, results, strict=True):
            if isinstance(res, RelevanceJudgement):
                chunk.rerank_score = float(max(0, min(10, res.relevance)))
            else:
                failures += 1
                log.warning("rerank judgement failed for %s: %s", chunk.chunk_id, res)
        if failures == len(head):
            log.error("LLM rerank failed for all candidates; keeping fused order")
            return chunks
        # Stable sort: ties (and failed judgements) keep their fused order.
        head = sorted(
            head, key=lambda c: -1.0 if c.rerank_score is None else c.rerank_score, reverse=True
        )
        return head + tail


def get_reranker(enabled: bool = True) -> Reranker:
    if not enabled or get_settings().reranker == "none":
        return NoopReranker()
    return LLMReranker()
