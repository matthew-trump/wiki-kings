"""Build a chronological, linked index of every monarch document under one slug."""

from __future__ import annotations

import re
from pathlib import Path

_HEADING = re.compile(r"^#\s+(.+?)\s*$")
_LEADING_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})-")


def _read_entry(doc_path: Path) -> tuple[str, str]:
    """Return (reign-start date, display name) for one *-INFOBOX.md file."""
    date_match = _LEADING_DATE.match(doc_path.name)
    start_date = date_match.group(1) if date_match else ""

    name = doc_path.stem
    with doc_path.open(encoding="utf-8") as f:
        for line in f:
            heading = _HEADING.match(line)
            if heading:
                name = heading.group(1)
                break
    return start_date, name


def build_index(output_root: Path, slug: str, title: str) -> Path:
    """Write output/{slug}/INDEX.md: a chronological list linking to each document.

    Ordering and the displayed date both come from each document's filename (the
    naming.py convention always starts it with an ISO reign-start date), so this
    stays correct without re-parsing each document's free-text Reign field.
    """
    documents_dir = output_root / slug / "documents"
    doc_paths = sorted(documents_dir.glob("*-INFOBOX.md"))

    lines = [f"# {title}", ""]
    for i, doc_path in enumerate(doc_paths, start=1):
        start_date, name = _read_entry(doc_path)
        link = f"documents/{doc_path.name}"
        suffix = f" — reign began {start_date}" if start_date else ""
        lines.append(f"{i}. [{name}]({link}){suffix}")
    lines.append("")

    index_path = output_root / slug / "INDEX.md"
    index_path.write_text("\n".join(lines), encoding="utf-8")
    return index_path
