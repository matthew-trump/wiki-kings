"""Build HOUSES.md: the normative, machine-readable list of a slug's sovereigns.

Groups sovereigns by dynastic House (heading order = each house's first
chronological appearance; sovereigns within a house in their own chronological
order), links each one to its own *-INFOBOX.md document, and records the color
assigned to each house. This file is meant to be iterated over programmatically --
scripts/build_keynote_deck.py reads it rather than re-deriving house/color
assignments from the documents directory, so editing HOUSES.md by hand (reassigning
a sovereign to a different house, tweaking a color) is picked up automatically on
the deck's next build.
"""

from __future__ import annotations

import re
from pathlib import Path

from .houses import assign_house_colors, normalize_house

_HEADING = re.compile(r"^#\s+(.+?)\s*$")
_FIELD_LINE = re.compile(r"^-\s+\*\*(.+?)\*\*:\s*(.*)$")
_LEADING_YEAR = re.compile(r"^(\d{4})-\d{2}-\d{2}-")  # filenames: date.isoformat() always zero-pads to 4 digits
_REIGN_FIELD = re.compile(r"^Reign(\d*)$")
_ANY_YEAR = re.compile(r"\d{3,4}")  # free-text Reign field: 9th/10th-century years are plain 3-digit


def _read_entry(doc_path: Path) -> tuple[str, str, str]:
    """Return (name, normalized house, 'startyear-endyear') for one *-INFOBOX.md file."""
    start_match = _LEADING_YEAR.match(doc_path.name)
    start_year = start_match.group(1) if start_match else "?"

    name = doc_path.stem
    fields: dict[str, str] = {}
    with doc_path.open(encoding="utf-8") as f:
        for line in f:
            heading_match = _HEADING.match(line)
            if heading_match:
                name = heading_match.group(1)
                continue
            field_match = _FIELD_LINE.match(line)
            if field_match:
                fields[field_match.group(1)] = field_match.group(2)

    house = normalize_house(fields.get("House", ""))
    end_year = _end_year(_primary_reign_end_source(name, fields))
    date_range = start_year if start_year == end_year else f"{start_year}–{end_year}"
    return name, house, date_range


# Monarchs whose end date needs a numbered ReignN field even though that field has
# its own SuccessionN label -- see _primary_reign_end_source's docstring. Anne's
# Reign1 ("Queen of Great Britain and Ireland") isn't a different, lesser realm the
# way Charles II's Reign1 ("King of Scotland", pre-Restoration) or George VI's
# ("Emperor of India") are -- it's the same sovereignty continuing under the name
# adopted at the 1707 Acts of Union. Checked by hand against every monarch with a
# numbered Reign field; see PROGRESS.md for the full table.
_REIGN_END_OVERRIDES = {
    "Anne, Queen of Great Britain": "Reign1",
}


def _primary_reign_end_source(name: str, fields: dict[str, str]) -> str:
    """Find the Reign-field text to pull this monarch's *English/UK-throne* end
    date from.

    Defaults to the plain 'Reign' field. Some monarchs split their time on that
    same throne across more than one stint -- Edward IV (deposed 1470, restored
    1471) and Henry VI (deposed 1461, restored 1470, deposed again 1471) -- and
    record each stint in a numbered ReignN field with no SuccessionN of its own
    (nothing marks it as a *different* title, just a break in the same one); the
    highest such N is the real end. ReignN fields that DO have a matching
    SuccessionN are a genuinely different, usually lesser or foreign title --
    Charles II's earlier Scotland-only reign, Henry VI's disputed claim to the
    French throne, George IV's stint as Prince Regent, Victoria/George VI's
    Empress/Emperor of India -- and must not be used here, even though they're
    structurally identical (a numbered Reign field) to the Edward IV/Henry VI
    case. `_REIGN_END_OVERRIDES` covers the one monarch (Anne) where that
    structural test gives the wrong answer.
    """
    if name in _REIGN_END_OVERRIDES:
        return fields.get(_REIGN_END_OVERRIDES[name], fields.get("Reign", ""))

    best_suffix = 0
    best_value = fields.get("Reign", "")
    for key, value in fields.items():
        match = _REIGN_FIELD.match(key)
        if not match or not match.group(1):
            continue
        suffix = int(match.group(1))
        if f"Succession{suffix}" in fields:
            continue  # a different (usually lesser/foreign) title, not a continuation
        if suffix > best_suffix:
            best_suffix = suffix
            best_value = value
    return best_value


def _end_year(reign: str) -> str:
    """Best-effort end year out of a free-text Reign field: take the last 4-digit
    year token, robust to the field's inconsistent dashes/spacing/artifacts --
    e.g. '8 September 2022-present' -> 'present', '30 September 1399 -; 20 March
    1413' -> '1413'."""
    reign = reign.strip()
    if reign.lower().endswith("present"):
        return "present"
    years = _ANY_YEAR.findall(reign)
    return years[-1] if years else "?"


def build_houses_document(output_root: Path, slug: str, title: str) -> Path:
    """Write output/{slug}/HOUSES.md: each House as a heading, ordered by when it
    first appears chronologically, with its sovereigns listed underneath in their
    own chronological order (including ones after a different house briefly
    interrupts, e.g. Tudor's Mary I appearing after the "Grey" heading), each
    linked to its own document and with its (start-end) year range.
    """
    documents_dir = output_root / slug / "documents"
    doc_paths = sorted(documents_dir.glob("*-INFOBOX.md"))

    entries = []  # (name, house, link, date_range), one per sovereign, chronological
    for doc_path in doc_paths:
        name, house, date_range = _read_entry(doc_path)
        entries.append((name, house, f"documents/{doc_path.name}", date_range))

    house_colors = assign_house_colors([house for _, house, _, _ in entries])

    house_order: list[str] = []
    house_members: dict[str, list[str]] = {}
    for name, house, link, date_range in entries:
        if house not in house_members:
            house_members[house] = []
            house_order.append(house)
        house_members[house].append(f"- [{name}]({link}) ({date_range})")

    lines = [f"# {title}", ""]
    for house in house_order:
        lines.append(f"## {house or '(house not recorded)'}")
        lines.append("")
        color = house_colors.get(house)
        if color:
            lines.append(f"Color: {color}")
            lines.append("")
        lines += house_members[house]
        lines.append("")

    doc_path = output_root / slug / "HOUSES.md"
    doc_path.write_text("\n".join(lines), encoding="utf-8")
    return doc_path
