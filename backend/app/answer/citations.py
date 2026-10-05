"""Claim extraction and citation validation (business rule R5).

The answer is split into claims (sentences / bullet lines). Each claim's [n] markers are
validated against the retrieved excerpts; markers pointing at non-existent excerpts are
removed, and factual claims left without any valid citation are dropped from the answer.
"""

import re
from dataclasses import dataclass, field

_CITATION = re.compile(r"\[(\d+(?:\s*[,;]\s*\d+)*)\]")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(*_\[])")
_LIST_MARKER = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_INSUFFICIENT = re.compile(
    r"\b(?:don't|do not|doesn't|does not|cannot|can't|couldn't|could not|unable to|no)\b"
    r"[^.]{0,60}\b(?:information|enough|find|mention|answer|context|details|data|record)",
    re.I,
)
INSUFFICIENT_ANSWER = (
    "I don't have enough information in the meetings and documents to answer that confidently."
)


@dataclass
class Claim:
    text: str
    citations: list[int]
    kind: str  # fact | meta | structure
    supported: bool


@dataclass
class ClaimsResult:
    answer: str
    claims: list[Claim] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    total_markers: int = 0
    valid_markers: int = 0
    insufficient: bool = False

    @property
    def facts(self) -> list[Claim]:
        return [c for c in self.claims if c.kind == "fact"]

    @property
    def coverage(self) -> float:
        facts = len(self.facts) + len(self.dropped)
        return len(self.facts) / facts if facts else 0.0

    @property
    def citation_valid_ratio(self) -> float:
        return self.valid_markers / self.total_markers if self.total_markers else 0.0

    @property
    def cited_sources(self) -> list[int]:
        return sorted({n for c in self.claims for n in c.citations})


def _classify(sentence: str, cited: bool) -> str:
    plain = _CITATION.sub("", sentence).strip(" *_-#>:")
    if cited:
        return "fact"
    if _INSUFFICIENT.search(plain):
        return "meta"
    if (
        len(plain.split()) < 4
        or sentence.rstrip().endswith(":")
        or sentence.lstrip().startswith("#")
    ):
        return "structure"
    return "fact"


def _validate_markers(sentence: str, n_sources: int, result: ClaimsResult) -> tuple[str, list[int]]:
    """Drop [n] markers that point at no excerpt; return cleaned text + valid numbers."""
    numbers: list[int] = []

    def _fix(m: re.Match) -> str:
        nums = [int(x) for x in re.split(r"\s*[,;]\s*", m.group(1))]
        result.total_markers += len(nums)
        valid = [n for n in nums if 1 <= n <= n_sources]
        result.valid_markers += len(valid)
        numbers.extend(valid)
        return "".join(f"[{n}]" for n in valid)

    return _CITATION.sub(_fix, sentence), numbers


_MARKERS = r"((?:\[\d+(?:\s*[,;]\s*\d+)*\][ \t]*)+)"


def normalize_citation_placement(answer: str) -> str:
    """Attach citations the model placed after the period or on their own line to the
    sentence they belong to: 'Due March 7. [1]' / 'Due March 7.\n[1]' -> 'Due March 7 [1].'"""
    answer = re.sub(r"([^\n])[ \t]*\n+[ \t]*" + _MARKERS + r"(?=\n|$)", r"\1 \2", answer)
    answer = re.sub(
        r"([.!?])[ \t]*" + _MARKERS, lambda m: f" {m.group(2).strip()}{m.group(1)} ", answer
    )
    return re.sub(r"[ \t]+\n", "\n", re.sub(r" {2,}", " ", answer)).strip()


def build_claims(answer: str, n_sources: int) -> ClaimsResult:
    result = ClaimsResult(answer="")
    kept_lines: list[str] = []
    for line in normalize_citation_placement(answer).splitlines():
        if not line.strip():
            kept_lines.append("")
            continue
        kept: list[str] = []
        for sentence in _SENTENCE_END.split(line):
            if not sentence.strip():
                continue
            cleaned, numbers = _validate_markers(sentence, n_sources, result)
            kind = _classify(cleaned, bool(numbers))
            plain = _LIST_MARKER.sub("", cleaned).strip()
            if kind == "fact" and not numbers:
                result.dropped.append(plain)
                continue
            result.claims.append(
                Claim(plain, sorted(set(numbers)), kind, kind != "fact" or bool(numbers))
            )
            kept.append(cleaned.strip())
        line_text = " ".join(kept)
        # Keep list markers only when the bullet still has content.
        if line_text and line_text.strip(" -*0123456789."):
            prefix = re.match(r"^\s*(?:[-*+]|\d+[.)])\s+", line)
            if prefix and not re.match(r"^\s*(?:[-*+]|\d+[.)])\s+", line_text):
                line_text = prefix.group(0) + line_text
            kept_lines.append(line_text)

    text = re.sub(r"\n{3,}", "\n\n", "\n".join(kept_lines)).strip()
    has_meta = any(c.kind == "meta" for c in result.claims)
    result.insufficient = not result.facts and (has_meta or bool(result.dropped) or not text)
    if not result.facts and not has_meta:
        text = INSUFFICIENT_ANSWER
        result.claims = [Claim(text, [], "meta", True)]
    result.answer = text
    return result


def strip_citations(text: str) -> str:
    return _CITATION.sub("", text)
