"""LLM metadata enrichment with structured output, cached by (content hash, model)."""

import logging
import re

from langchain_core.prompts import ChatPromptTemplate

from app.config import get_settings
from app.db import repository
from app.llm.factory import llm_identity, structured_llm
from app.models.enrichment import EnrichmentResult
from app.models.source import SourceDoc

log = logging.getLogger(__name__)

PROMPT_VERSION = "v3"

SYSTEM = """You extract structured metadata from internal documents of a mid-size automotive
semiconductor company (HQ Austin TX, design center Portland OR, fab/test in Penang Malaysia)
that makes automotive microcontrollers and power management ICs.
Key concerns: yield, new product introduction (NPI) ramps, automotive qualification
(AEC-Q100, ISO 26262), customer deadlines, supply chain.

topic_domain (pick one):
- yield: fab/process yield, wafer lots, defect analysis
- design: chip design, design reviews, specs, tape-out, design handoff
- test_engineering: ATE test programs, test coverage, probe/sort, characterization
- npi_program: NPI ramp planning, milestones, gates, cross-functional program status
- supply_chain: vendors, materials, capacity, logistics
- customer: customer escalations, complaints, commitments
- quality_compliance: quality reports, AEC-Q100, audits, reliability
- executive_strategy: company strategy, financials, roadmap, leadership decisions
- other: none of the above

priority:
- critical: customer line-down, safety/AEC-Q100 failure, shipment stop, major revenue at risk
- high: active customer escalation, yield below target with revenue impact, schedule slip
- medium: active issue with mitigation in place, upcoming deadline
- low: routine status, informational
- none: priority not applicable

Rules: use only facts in the text. Product names exactly as in the text (e.g. "Volta-7").
Action item owners must be people named in the text. Do not invent dates."""

HUMAN = """Title: {title}
Date: {date}
Type: {doc_type}
Attendees/authors: {people}

Content:
{content}"""

_PROMPT = ChatPromptTemplate.from_messages([("system", SYSTEM), ("human", HUMAN)])

_PRODUCT_CODE = re.compile(r"^([A-Za-z]+)[\s_-]*(\d+[A-Za-z]?)$")


def normalize_product(name: str) -> str:
    """'volta 7' / 'VOLTA7' / 'Volta-7' -> 'Volta-7'; other names are kept as written."""
    name = name.strip()
    if m := _PRODUCT_CODE.match(name):
        return f"{m.group(1).capitalize()}-{m.group(2).upper()}"
    return name


def _normalize(result: EnrichmentResult) -> EnrichmentResult:
    products = dict.fromkeys(normalize_product(p) for p in result.products if p.strip())
    return result.model_copy(update={"products": list(products)})


def enrich(src: SourceDoc, force: bool = False) -> EnrichmentResult:
    cache_key = f"{llm_identity()}:{PROMPT_VERSION}"
    if not force and (cached := repository.get_cached_enrichment(src.content_hash, cache_key)):
        return cached
    log.info("enriching %s with %s", src.source_file, cache_key)
    result = (_PROMPT | structured_llm(EnrichmentResult)).invoke(
        {
            "title": src.title,
            "date": src.date or "unknown",
            "doc_type": src.extra.get("meeting_type") or src.source_type,
            "people": ", ".join(src.attendees or src.authors) or "unknown",
            "content": src.content[: get_settings().enrich_max_chars],
        }
    )
    result = _normalize(result)
    repository.cache_enrichment(src.content_hash, cache_key, result)
    return result
