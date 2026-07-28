"""Render a parsed infobox dict into a simple Markdown document."""

from __future__ import annotations

from pathlib import Path


def humanize_field(name: str) -> str:
    return name.replace("_", " ").strip().title()


def render_markdown(*, regnal_name: str, fields: dict[str, str], image_relpath: str | None) -> str:
    lines = [f"# {regnal_name}", ""]
    if image_relpath:
        lines.append(f"![{regnal_name}]({image_relpath})")
        lines.append("")
    for key, value in fields.items():
        lines.append(f"- **{humanize_field(key)}**: {value}")
    lines.append("")
    return "\n".join(lines)


def write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
