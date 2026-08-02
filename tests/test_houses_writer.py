from pathlib import Path

from wiki_kings.houses_writer import _end_year, _primary_reign_end_source, build_houses_document


def _write_doc(output_root: Path, slug: str, filename: str, heading: str, fields: dict[str, str]) -> None:
    documents_dir = output_root / slug / "documents"
    documents_dir.mkdir(parents=True, exist_ok=True)
    lines = [f"# {heading}", ""]
    lines += [f"- **{key}**: {value}" for key, value in fields.items()]
    (documents_dir / filename).write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_end_year_present():
    assert _end_year("8 September 2022–present") == "present"


def test_end_year_last_year_token_survives_artifacts():
    assert _end_year("30 September 1399 –; 20 March 1413") == "1413"


def test_end_year_no_year_found():
    assert _end_year("unknown") == "?"


def test_end_year_three_digit_year():
    assert _end_year("23 April 871 – c. 886") == "886"


def test_primary_reign_end_source_uses_later_stint_of_same_title():
    # Edward IV: deposed 1470 (Readeption of Henry VI), restored 1471. Reign1 has
    # no Succession1 of its own -- it's the same "King of England" title, just a
    # second stint -- so it's the real end date, not Reign's first-stint end.
    fields = {
        "Reign": "4 March 1461 – 3 October 1470",
        "Reign1": "11 April 1471 – 9 April 1483",
    }
    assert _primary_reign_end_source("Edward IV", fields) == "11 April 1471 – 9 April 1483"


def test_primary_reign_end_source_ignores_different_titled_reign_field():
    # Charles II: Reign1 ("King of Scotland", 1649-1651) is an earlier, different,
    # lesser realm with its own Succession1 -- not a continuation, must be ignored
    # even though it's structurally a numbered Reign field just like Edward IV's.
    fields = {
        "Reign": "29 May 1660 – 6 February 1685",
        "Succession1": "King of Scotland",
        "Reign1": "30 January 1649 – 3 September 1651",
    }
    assert _primary_reign_end_source("Charles II of England", fields) == "29 May 1660 – 6 February 1685"


def test_primary_reign_end_source_anne_override():
    # Anne's Reign1 ("Queen of Great Britain", from the 1707 Acts of Union) DOES
    # have its own Succession1 -- structurally identical to Charles II's excluded
    # case -- but it's a rename of the same sovereignty, not a different realm, so
    # it needs an explicit override rather than the general structural rule.
    fields = {
        "Reign": "8 March 1702 – 1 May 1707",
        "Succession1": "Queen of Great Britain and Ireland",
        "Reign1": "1 May 1707 – 1 August 1714",
    }
    assert _primary_reign_end_source("Anne, Queen of Great Britain", fields) == "1 May 1707 – 1 August 1714"


def test_primary_reign_end_source_falls_back_to_plain_field():
    assert _primary_reign_end_source("William the Conqueror", {"Reign": "1066 – 1087"}) == "1066 – 1087"


def test_build_houses_document_groups_and_orders(tmp_path):
    slug = "test_kings"
    _write_doc(
        tmp_path, slug, "1461-03-04-EDWARD_IV-INFOBOX.md", "Edward IV",
        {
            "House": "York",
            "Reign": "4 March 1461 – 3 October 1470",
            "Reign1": "11 April 1471 – 9 April 1483",
        },
    )
    _write_doc(
        tmp_path, slug, "1483-06-26-RICHARD_III-INFOBOX.md", "Richard III",
        {"House": "York", "Reign": "26 June 1483 – 22 August 1485"},
    )
    _write_doc(
        tmp_path, slug, "1485-08-22-HENRY_VII-INFOBOX.md", "Henry VII",
        {"House": "Tudor", "Reign": "22 August 1485 – 21 April 1509"},
    )

    doc_path = build_houses_document(tmp_path, slug, "Test Houses")
    content = doc_path.read_text(encoding="utf-8")

    assert doc_path == tmp_path / slug / "HOUSES.md"
    assert content.startswith("# Test Houses\n")
    # Edward IV's end year comes from Reign1 (his actual death), not Reign (deposed),
    # and each sovereign is linked to their own document.
    assert "[Edward IV](documents/1461-03-04-EDWARD_IV-INFOBOX.md) (1461–1483)" in content
    assert "[Richard III](documents/1483-06-26-RICHARD_III-INFOBOX.md) (1483–1485)" in content
    # Two houses, in first-appearance order, each with its own heading and a
    # recorded color line right below it.
    york_idx = content.index("## York")
    york_color_idx = content.index("Color: #", york_idx)
    tudor_idx = content.index("## Tudor")
    tudor_color_idx = content.index("Color: #", tudor_idx)
    henry_idx = content.index("Henry VII")
    assert york_idx < york_color_idx < tudor_idx < tudor_color_idx < henry_idx


def test_build_houses_document_regroups_interrupted_house(tmp_path):
    slug = "test_kings"
    _write_doc(
        tmp_path, slug, "1547-01-28-EDWARD_VI-INFOBOX.md", "Edward VI",
        {"House": "Tudor", "Reign": "28 January 1547 – 6 July 1553"},
    )
    _write_doc(
        tmp_path, slug, "1553-07-10-LADY_JANE_GREY-INFOBOX.md", "Lady Jane Grey",
        {"House": "Grey", "Reign": "10 July 1553 – 19 July 1553"},
    )
    _write_doc(
        tmp_path, slug, "1553-07-19-MARY_I-INFOBOX.md", "Mary I",
        {"House": "Tudor", "Reign": "19 July 1553 – 17 November 1558"},
    )

    content = build_houses_document(tmp_path, slug, "Test").read_text(encoding="utf-8")

    # Tudor appears once (not split into two sections around Grey's interruption),
    # with BOTH Edward VI and Mary I grouped under that single heading.
    assert content.count("## Tudor") == 1
    assert content.count("## Grey") == 1
    tudor_section = content.split("## Tudor")[1].split("## Grey")[0]
    assert "Edward VI" in tudor_section and "Mary I" in tudor_section
    # Single-year-precision collapsing: a reign entirely within one year shows once.
    assert "[Lady Jane Grey](documents/1553-07-10-LADY_JANE_GREY-INFOBOX.md) (1553)" in content


def test_build_houses_document_records_color_and_link_for_unknown_house(tmp_path):
    # A house outside the hardcoded UK table (a different slug/dataset) still gets
    # a color line, via assign_house_colors()'s cycling fallback, plus a link.
    slug = "test_kings"
    _write_doc(
        tmp_path, slug, "1000-01-01-SOMEONE-INFOBOX.md", "Someone",
        {"House": "Made Up House", "Reign": "1 January 1000 – 1 January 1010"},
    )
    content = build_houses_document(tmp_path, slug, "Test").read_text(encoding="utf-8")
    assert "## Made Up House" in content
    assert "Color: #3987e5" in content  # first fallback slot, in fixed palette order
    assert "[Someone](documents/1000-01-01-SOMEONE-INFOBOX.md) (1000–1010)" in content
