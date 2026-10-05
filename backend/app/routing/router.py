"""Routing: when the system can't answer confidently, suggest who to ask, why, and a draft.

Candidates are the attendees (meetings) and authors (documents) of the retrieved sources,
plus action-item owners, weighted by how relevant each source was. The 'why' cites the
matched files; the draft question is written by the LLM (template fallback).
"""

import logging
import re
from dataclasses import dataclass, field

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.config import get_settings
from app.llm.factory import get_llm
from app.retrieval.types import RetrievedChunk

log = logging.getLogger(__name__)

_DRAFT_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Write a short, polite message (2-4 sentences) from an employee to a colleague "
            "asking them to answer a question the internal knowledge base could not answer "
            "confidently. Reference the specific meeting/document that suggests they know. "
            "Ask one clear question. No greeting line like 'Subject:'; no sign-off name.",
        ),
        (
            "human",
            "Colleague: {person} ({role})\nWhy them: {reason}\nOriginal question: {question}\n"
            "Context: {context}",
        ),
    ]
)


@dataclass
class Candidate:
    person: str
    score: float = 0.0
    role: str | None = None
    sources: dict[str, dict] = field(default_factory=dict)  # source_file -> info
    tasks: list[str] = field(default_factory=list)


def _key(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def _overlap(question: str, text: str) -> float:
    q = {t for t in re.findall(r"[a-z0-9][a-z0-9-]+", question.lower()) if len(t) > 2}
    return len(q & set(re.findall(r"[a-z0-9][a-z0-9-]+", text.lower()))) / len(q) if q else 0.0


def rank_people(
    chunks: list[RetrievedChunk], documents: dict[str, dict], question: str = ""
) -> list[Candidate]:
    people: dict[str, Candidate] = {}
    for rank, chunk in enumerate(chunks):
        m = chunk.document.metadata
        doc = documents.get(m["doc_id"])
        if not doc:
            continue
        weight = 1.0 / (rank + 1) + ((chunk.rerank_score or 0) / 10)
        roles = {**doc.get("attendee_roles", {}), **doc.get("author_roles", {})}
        relations = (
            [(p, "author") for p in doc.get("authors", [])]
            + [(p, "reviewer") for p in doc.get("reviewers", [])]
            + [(p, "attendee") for p in doc.get("attendees", [])]
        )
        owners = {_key(a["owner"]): a["task"] for a in doc.get("action_items", [])}
        snippet = chunk.document.page_content.split("\n", 1)[-1][:160].strip()
        for name, relation in relations:
            cand = people.setdefault(_key(name), Candidate(person=name))
            cand.role = cand.role or roles.get(name)
            bonus = {"author": 1.0, "reviewer": 0.5}.get(relation, 0.0)
            task = owners.get(_key(name))
            if task:
                bonus += 1.0 + 3.0 * _overlap(question, task)
                if task not in cand.tasks:
                    cand.tasks.append(task)
            cand.score += weight * (1 + bonus)
            info = cand.sources.setdefault(
                doc["source_file"],
                {
                    "source_file": doc["source_file"],
                    "title": doc.get("title"),
                    "date": doc.get("date"),
                    "relation": relation,
                    "snippet": snippet,
                },
            )
            info["relation"] = "author" if relation == "author" else info["relation"]
    return sorted(people.values(), key=lambda c: c.score, reverse=True)


def _reason(c: Candidate) -> str:
    parts = []
    if c.tasks:
        parts.append(f'owns related action item "{c.tasks[0]}"')
    for src in list(c.sources.values())[:2]:
        verb = {"author": "authored", "reviewer": "reviewed"}.get(src["relation"], "attended")
        when = f" ({src['date']})" if src.get("date") else ""
        parts.append(f'{verb} "{src["title"]}"{when}')
    text = "; ".join(parts)
    return text[:1].upper() + text[1:] + "."


def _template_draft(c: Candidate, question: str) -> str:
    src = next(iter(c.sources.values()), None)
    ref = f' since you were involved in "{src["title"]}"' if src else ""
    return (
        f"Hi {c.person.split()[0]}, I'm trying to find out: {question} The knowledge base "
        f"couldn't answer this confidently, and I thought you might know{ref}. "
        "Could you help clarify?"
    )


def suggest_routing(
    question: str,
    chunks: list[RetrievedChunk],
    documents: dict[str, dict],
    situation: str = "The knowledge base could not answer confidently.",
) -> list[dict]:
    top = rank_people(chunks, documents, question)[: get_settings().routing_max_people]
    if not top:
        return []
    inputs = [
        {
            "person": c.person,
            "role": c.role or "colleague",
            "reason": _reason(c),
            "question": question,
            "context": situation
            + " Matched: "
            + "; ".join(s["snippet"] for s in list(c.sources.values())[:2]),
        }
        for c in top
    ]
    drafts = (_DRAFT_PROMPT | get_llm() | StrOutputParser()).batch(
        inputs, config={"max_concurrency": 3}, return_exceptions=True
    )
    out = []
    for c, inp, draft in zip(top, inputs, drafts, strict=True):
        if isinstance(draft, Exception) or not str(draft).strip():
            log.warning("draft generation failed for %s: %s", c.person, draft)
            draft = _template_draft(c, question)
        out.append(
            {
                "person": c.person,
                "role": c.role,
                "reason": inp["reason"],
                "matched_sources": list(c.sources.values())[:3],
                "draft_question": str(draft).strip(),
                "score": round(c.score, 3),
            }
        )
    return out
