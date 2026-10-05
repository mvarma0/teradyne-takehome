from app.config import get_settings
from app.ingestion.loaders.meeting import iter_meeting_files, load_meeting, parse_meeting


def test_frontmatter_format():
    files = iter_meeting_files(get_settings().meetings_dir)
    doc = load_meeting(files[0], get_settings().data_dir)
    assert doc.source_file == "meetings/meeting_01_eagle5_yield.md"
    assert doc.title == "Eagle-5 Yield Excursion Review"
    assert doc.date == "2025-03-04"
    assert doc.attendees == ["Sarah Chen", "Marcus Rivera", "Tom Bradley", "Jennifer Liu"]
    assert doc.attendees_source == "frontmatter"
    assert doc.extra["meeting_number"] == 1


def test_label_line_format_strips_roles():
    files = iter_meeting_files(get_settings().meetings_dir)
    doc = load_meeting(files[1], get_settings().data_dir)
    assert doc.title == "Falcon-7 Design Review: Thermal and Power"
    assert doc.date == "2025-03-12"
    assert doc.attendees == ["Priya Patel", "Amanda Foster", "James Kim", "Rachel Adams"]
    assert doc.attendees_source == "header"


def test_attendees_heading_list():
    files = iter_meeting_files(get_settings().meetings_dir)
    doc = load_meeting(files[2], get_settings().data_dir)
    assert doc.date == "2025-04-02"
    assert doc.attendees == ["Mike O'Brien", "Jennifer Liu", "David Park"]


def test_bold_label_format():
    raw = "# Ops Sync\n\n**Date:** 2025-05-01\n**Attendees:** Lisa Wong, Kevin Nash\n\nText."
    parsed = parse_meeting(raw, "meeting_09.md")
    assert parsed["date"] == "2025-05-01"
    assert parsed["attendees"] == ["Lisa Wong", "Kevin Nash"]
    assert parsed["meeting_number"] == 9


def test_speaker_fallback_when_no_attendee_list():
    raw = "# Sync\n\n**Robert Zhang:** Revenue is flat.\n\n**Kevin Nash:** Agreed.\n"
    parsed = parse_meeting(raw, "m.md")
    assert parsed["attendees"] == ["Robert Zhang", "Kevin Nash"]
    assert parsed["attendees_source"] == "speakers"


def test_natural_file_order(isolated_env):
    (isolated_env / "meetings" / "meeting_2.md").write_text("# Two")
    names = [p.name for p in iter_meeting_files(isolated_env / "meetings")]
    assert names.index("meeting_2.md") < names.index("meeting_05_falcon7_design.md")


def test_plain_text_header_with_roles_and_inline_labels():
    raw = (
        "Meeting: Ramp Kickoff\n"
        "Date: 2024-01-08 Time: 09:00 AM CST Location: Room A (Austin HQ)\n"
        "Attendees: Ann Lee (VP, Engineering), Bo Diaz (PE Manager)\n"
        "Meeting Type: NPI Standup\n\nDiscussion\nAnn Lee: Go.\n"
    )
    p = parse_meeting(raw, "meeting_2024_01_08_kickoff.md")
    assert (p["title"], p["date"], p["meeting_type"]) == (
        "Ramp Kickoff",
        "2024-01-08",
        "NPI Standup",
    )
    assert p["attendees"] == ["Ann Lee", "Bo Diaz"]
    assert p["attendee_roles"] == {"Ann Lee": "VP, Engineering", "Bo Diaz": "PE Manager"}
    assert p["location"] == "Room A (Austin HQ)"


def test_plain_section_labels_become_headings():
    from app.ingestion.docling_md import promote_section_labels

    assert promote_section_labels("Decisions\n1. x\nAction Items\n- y") == (
        "## Decisions\n1. x\n## Action Items\n- y"
    )


def test_product_normalization():
    from app.ingestion.enrich import normalize_product

    assert [normalize_product(p) for p in ["volta 7", "VOLTA7", "Volta-7", "BCD node"]] == [
        "Volta-7",
        "Volta-7",
        "Volta-7",
        "BCD node",
    ]
