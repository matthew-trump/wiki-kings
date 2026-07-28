"""Output path conventions, per PROJECT.md.

Documents: ./output/{slug_title}/documents/{YYYY-MM-DD}-{REGNAL_NAME}-INFOBOX.md
Images:    ./output/{slug_title}/images/{YYYY-MM-DD}-{REGNAL_NAME}
where REGNAL_NAME is the regnal name, upper-cased with spaces replaced by underscores.
"""

from __future__ import annotations

from pathlib import Path


def regnal_slug(regnal_name: str) -> str:
    return regnal_name.strip().upper().replace(" ", "_")


def base_filename(start_date: str, regnal_name: str) -> str:
    return f"{start_date}-{regnal_slug(regnal_name)}"


def document_path(output_root: Path, slug_title: str, start_date: str, regnal_name: str) -> Path:
    name = f"{base_filename(start_date, regnal_name)}-INFOBOX.md"
    return output_root / slug_title / "documents" / name


def image_path_stem(output_root: Path, slug_title: str, start_date: str, regnal_name: str) -> Path:
    """Path with no extension yet -- the actual image format decides the suffix."""
    return output_root / slug_title / "images" / base_filename(start_date, regnal_name)
