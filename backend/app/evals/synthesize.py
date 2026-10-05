"""Generate a synthetic eval set from ingested chunks: the LLM writes one question per
sampled chunk that the chunk answers; the chunk's file becomes the expected source."""

import json
import logging
import random

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.evals.runner import DATASETS
from app.llm.factory import structured_llm
from app.retrieval.vectorstore import all_chunks

log = logging.getLogger(__name__)


class SyntheticCase(BaseModel):
    question: str = Field(description="A specific question an employee might ask")
    expected_keywords: list[str] = Field(description="2-4 short facts the answer must contain")


_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Write one realistic, specific question that the excerpt below fully "
            "answers, as an engineer at the company would ask it. Do not mention "
            "'the excerpt' or 'the document'. Also list 2-4 short key facts "
            "(names, numbers, dates) the correct answer must contain.",
        ),
        ("human", "{excerpt}"),
    ]
)


def synthesize(n: int = 20, seed: int = 7) -> int:
    chunks = [c for c in all_chunks() if len(c.page_content) > 300]
    by_doc: dict[str, list] = {}
    for c in chunks:
        by_doc.setdefault(c.metadata["doc_id"], []).append(c)
    rng = random.Random(seed)
    pools = [rng.sample(v, len(v)) for v in by_doc.values()]
    rng.shuffle(pools)
    picked = []  # round-robin across documents for coverage
    while len(picked) < n and any(pools):
        for pool in pools:
            if pool and len(picked) < n:
                picked.append(pool.pop())
    results = (_PROMPT | structured_llm(SyntheticCase)).batch(
        [{"excerpt": c.page_content[:2000]} for c in picked],
        config={"max_concurrency": 4},
        return_exceptions=True,
    )
    lines = []
    for i, (chunk, res) in enumerate(zip(picked, results, strict=True), start=1):
        if isinstance(res, Exception):
            log.warning("synthesis failed for %s: %s", chunk.metadata["chunk_id"], res)
            continue
        lines.append(
            json.dumps(
                {
                    "id": f"syn-{i:02d}",
                    "question": res.question,
                    "answerable": True,
                    "expected_sources": [chunk.metadata["source_file"]],
                    "expected_keywords": res.expected_keywords,
                }
            )
        )
    DATASETS["synthetic"].parent.mkdir(parents=True, exist_ok=True)
    DATASETS["synthetic"].write_text("\n".join(lines) + "\n")
    return len(lines)
