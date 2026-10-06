"""Business rules, applied identically to every source type.

Ingest time (apply_ingest_rules):
  R1 priority floor: line-down / stop-ship / safety / recall language -> critical;
     escalation / field returns / 8D / qualification failure / ISO 26262 -> at least high.
  R2 action-item owners must be named in the source text, else "unassigned".
  R3 products must be mentioned in the source text.
  R4 people (attendees/authors) only ever come from source parsing, never the LLM
     (enforced structurally: the loaders set them, enrichment has no people fields).
Answer time (see app/answer.py):
  R5 every claim must cite a retrieved excerpt; uncited claims are dropped.
  R6 when sources conflict, prefer the most recent and surface the conflict (answer prompt)."""

import re

from app.schemas import EnrichmentResult, SourceDoc

PRIORITY_ORDER = ["none", "low", "medium", "high", "critical"]

_CRITICAL = [
    r"\bline[- ]down\b",
    r"\bline (?:stop|stoppage)\b",
    r"production line[^.]{0,40}\b(?:stop|halt|at risk)",
    r"\bstop[- ]ship\b",
    r"\b(?:vehicle|field|product) recall\b",
    r"\bsafety[- ](?:critical|risk|issue|hazard)\b",
]
_HIGH = [
    r"\bescalat",
    r"\bfield returns?\b",
    r"\bcustomer complaints?\b",
    r"\b8d\b",
    r"\b(?:aec-q100|qualification)\b[^.]{0,60}\bfail",
    r"\biso 26262\b",
    r"\bcontainment\b",
]


def _rank(priority: str) -> int:
    return PRIORITY_ORDER.index(priority) if priority in PRIORITY_ORDER else 0


def priority_floor(text: str) -> str | None:
    low = text.lower()
    if any(re.search(p, low) for p in _CRITICAL):
        return "critical"
    if any(re.search(p, low) for p in _HIGH):
        return "high"
    return None


def _named_in(name: str, text: str) -> bool:
    parts = [p for p in re.split(r"\s+", name.lower()) if len(p) > 1]
    return bool(parts) and all(p in text for p in parts)


def apply_ingest_rules(
    src: SourceDoc, enrichment: EnrichmentResult
) -> tuple[EnrichmentResult, list[str]]:
    text = src.content.lower()
    applied: list[str] = []
    update: dict = {}

    floor = priority_floor(src.content)
    if floor and _rank(enrichment.priority) < _rank(floor):
        update["priority"] = floor
        applied.append(f"R1:priority {enrichment.priority}->{floor}")

    items = []
    for item in enrichment.action_items:
        if item.owner.lower() != "unassigned" and not _named_in(item.owner, text):
            applied.append(f"R2:owner '{item.owner}' not in source -> unassigned")
            item = item.model_copy(update={"owner": "unassigned"})
        items.append(item)
    update["action_items"] = items

    flat = re.sub(r"[\s-]", "", text)
    products = [p for p in enrichment.products if re.sub(r"[\s-]", "", p.lower()) in flat]
    if len(products) != len(enrichment.products):
        dropped = sorted(set(enrichment.products) - set(products))
        applied.append(f"R3:dropped products not in source {dropped}")
    update["products"] = products

    return enrichment.model_copy(update=update), applied
