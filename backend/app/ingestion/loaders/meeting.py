"""Meeting transcript loader.

Title, date and attendees are parsed deterministically from the raw text. Supports
YAML frontmatter, label lines ("Meeting: ...", "**Date:** ...", "Attendees: a (Role), b"),
an "## Attendees" bullet list, and falls back to speaker names when no attendee list exists.
Attendee roles in parentheses are kept separately (attendee_roles) for routing.
"""

import hashlib
import re
from pathlib import Path

import frontmatter
from dateutil import parser as dateparser

from app.ingestion.docling_md import normalize_markdown
from app.models.source import SourceDoc

_LABEL = r"^[\s>*_\-]*(?:{labels})[\s*_]*[:：][\s*_]*(?P<value>.*?)[\s*_]*$"
_DATE_RE = re.compile(_LABEL.format(labels="date|meeting date|when"), re.I | re.M)
_ATTENDEES_RE = re.compile(
    _LABEL.format(labels="attendees|participants|present|attendance"), re.I | re.M
)
_TITLE_RE = re.compile(_LABEL.format(labels="title|subject|meeting title|meeting"), re.I | re.M)
_TYPE_RE = re.compile(_LABEL.format(labels="meeting type|type"), re.I | re.M)
_LOCATION_RE = re.compile(r"\blocation\s*[:：]\s*(?P<value>[^\n]+?)\s*$", re.I | re.M)
# Inline labels that may follow the date on the same line ("Date: x Time: y Location: z")
_INLINE_LABEL = re.compile(r"\s+(?:time|location|venue|duration)\s*[:：].*$", re.I)
_ATTENDEES_HEADING = re.compile(r"^#{1,6}\s*(attendees|participants|present)\b.*$", re.I | re.M)
_H1 = re.compile(r"^#\s+(.+?)\s*#*\s*$", re.M)
_ISO_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_SPEAKER = re.compile(
    r"^\s*(?:\*\*|__)?(?P<name>[A-Z][\w.'\-]+(?:\s[A-Z][\w.'\-]+){1,3})"
    r"\s*(?::\s*(?:\*\*|__)|(?:\*\*|__)?:)",
    re.M,
)
_NOT_PEOPLE = {
    "action item",
    "action items",
    "next steps",
    "key decision",
    "meeting notes",
    "open issues",
}


def _clean_name(raw: str) -> str:
    name = re.sub(r"[*_`\[\]]", "", raw)
    name = re.sub(r"\(.*?\)", "", name)
    name = re.split(r"\s+[-–—]\s+|,\s*(?=[A-Z][a-z]+\s*$)", name)[0]
    return re.sub(r"\s+", " ", name).strip(" .:")


def parse_people(value: str | list) -> dict[str, str | None]:
    """Name -> role (role from a trailing '(Role)' or ' - Role'), order preserved."""
    if isinstance(value, list):
        parts = [str(v) for v in value]
    else:
        # Protect commas inside parentheses before splitting the list.
        protected = re.sub(
            r"\(([^)]*)\)", lambda m: "(" + m.group(1).replace(",", "\x00") + ")", value
        )
        parts = [p.replace("\x00", ",") for p in re.split(r",|;|\||\band\b|&", protected)]
    people: dict[str, str | None] = {}
    for p in parts:
        role_match = re.search(r"\(([^)]*)\)", p) or re.search(r"\s[-–—]\s+(.+)$", p)
        name = _clean_name(p)
        if len(name) > 1 and name.lower() not in _NOT_PEOPLE and name not in people:
            people[name] = role_match.group(1).strip() if role_match else None
    return people


def split_names(value: str | list) -> list[str]:
    return list(parse_people(value))


def parse_date(value: object) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()[:10]
    if m := _ISO_DATE.search(str(value)):
        return m.group(1)
    value = _INLINE_LABEL.sub("", str(value))
    try:
        return dateparser.parse(str(value), fuzzy=True).date().isoformat()
    except (ValueError, OverflowError):
        return None


def _attendees_from_heading(body: str) -> dict[str, str | None]:
    m = _ATTENDEES_HEADING.search(body)
    if not m:
        return {}
    names: dict[str, str | None] = {}
    for line in body[m.end() :].splitlines():
        stripped = line.strip()
        if not stripped:
            if names:
                break
            continue
        if stripped.startswith("#"):
            break
        if re.match(r"^([-*+]|\d+[.)])\s+", stripped):
            names |= parse_people(re.sub(r"^([-*+]|\d+[.)])\s+", "", stripped))
        elif names:
            break
    return names


def parse_meeting(raw: str, filename: str) -> dict:
    post = frontmatter.loads(raw)
    meta = {str(k).lower(): v for k, v in post.metadata.items()}
    body = post.content
    head = "\n".join(body.splitlines()[:40])

    title = meta.get("title")
    if not title and (m := _TITLE_RE.search(head)):
        title = m.group("value")
    if not title and (m := _H1.search(body)):
        title = m.group(1)
    title = re.sub(r"[*_`]", "", str(title)).strip() if title else Path(filename).stem

    date = parse_date(meta.get("date"))
    if not date and (m := _DATE_RE.search(head)):
        date = parse_date(m.group("value"))
    if not date and (m := _ISO_DATE.search(head) or _ISO_DATE.search(filename)):
        date = m.group(1)

    people: dict[str, str | None] = {}
    source = "none"
    if raw_att := meta.get("attendees") or meta.get("participants"):
        people, source = parse_people(raw_att), "frontmatter"
    elif (m := _ATTENDEES_RE.search(head)) and m.group("value"):
        people, source = parse_people(m.group("value")), "header"
    if not people and (people := _attendees_from_heading(body)):
        source = "header"
    if not people:
        people = parse_people([m.group("name") for m in _SPEAKER.finditer(body)])
        source = "speakers" if people else "none"

    meeting_type = meta.get("type") or meta.get("meeting_type")
    if not meeting_type and (m := _TYPE_RE.search(head)):
        meeting_type = m.group("value")
    location = meta.get("location")
    if not location and (m := _LOCATION_RE.search(head)):
        location = m.group("value")

    number = re.search(r"\d+", Path(filename).stem)
    return {
        "title": title,
        "date": date,
        "attendees": list(people),
        "attendee_roles": {n: r for n, r in people.items() if r},
        "attendees_source": source,
        "meeting_type": str(meeting_type).strip() if meeting_type else None,
        "location": str(location).strip() if location else None,
        "body": body,
        "meeting_number": int(number.group()) if number else None,
    }


def make_doc_id(source_file: str) -> str:
    return hashlib.sha1(source_file.encode()).hexdigest()[:16]


def iter_meeting_files(meetings_dir: Path) -> list[Path]:
    if not meetings_dir.is_dir():
        return []

    def natural_key(p: Path):
        return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)]

    return sorted(meetings_dir.rglob("*.md"), key=natural_key)


def load_meeting(path: Path, data_dir: Path) -> SourceDoc:
    raw = path.read_text(encoding="utf-8")
    rel = path.relative_to(data_dir).as_posix()
    parsed = parse_meeting(raw, path.name)
    return SourceDoc(
        doc_id=make_doc_id(rel),
        source_file=rel,
        source_type="meeting",
        title=parsed["title"],
        date=parsed["date"],
        attendees=parsed["attendees"],
        attendees_source=parsed["attendees_source"],
        content=normalize_markdown(parsed["body"], path.name),
        content_hash=hashlib.sha256(raw.encode()).hexdigest(),
        extra={
            k: parsed[k]
            for k in ("meeting_number", "meeting_type", "location", "attendee_roles")
            if parsed[k]
        },
    )
