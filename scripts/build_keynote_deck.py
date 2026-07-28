"""Build a Keynote deck from a slug's HOUSES.md -- the normative sovereign list.

Reads output/{slug}/HOUSES.md (built by `wiki-kings houses`; see houses_writer.py),
which is the source of truth for the sovereign list, each one's House, and each
house's color -- NOT re-derived from the documents directory here, so hand-edits to
HOUSES.md (reassigning a house, tweaking a color) are picked up automatically.
HOUSES.md groups by house, so its line order isn't the true timeline; entries are
re-sorted here by the ISO date baked into each linked document's filename. For each
sovereign, pulls a few infobox fields and the saved thumbnail out of the linked
document itself, and emits an AppleScript file that drives Keynote to build one
slide per monarch. Doesn't touch the .key file format directly -- Keynote is
controlled the same way a human would use it, via its scripting dictionary.

Usage:
    python scripts/build_keynote_deck.py [--limit N] [--out deck.applescript]
    osascript deck.applescript
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BODY_FIELDS = ["Reign", "Birth Date", "Death Date"]  # House is shown separately, see below

# 1024x768 (4:3) is the "White" theme's default canvas. Photo box is right-aligned
# in the right-hand column; text box is the left-hand column. All text items get an
# explicit height -- Keynote vertically centers text within a text item's box, and an
# unset (default) height is tall enough that centered items visibly overlap.
SLIDE_WIDTH = 1024
HOUSE_BOX = {"x": 40, "y": 20, "width": 560, "height": 44}
TITLE_BOX = {"x": 40, "y": 74, "width": 560, "height": 70}
BODY_BOX = {"x": 40, "y": 184, "width": 560, "height": 380}
PHOTO_BOX = {"right": 984, "top": 90, "max_width": 340, "max_height": 560}


def hex_to_rgb65535(hex_color: str) -> tuple[int, int, int]:
    """Convert '#rrggbb' to the {R,G,B} 0-65535 triple Keynote's AppleScript color
    properties expect."""
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return tuple(round(c / 255 * 65535) for c in (r, g, b))


def image_pixel_size(image_path: Path) -> tuple[int, int] | None:
    try:
        output = subprocess.run(
            ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(image_path)],
            capture_output=True, text=True, check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    width = height = None
    for line in output.splitlines():
        if "pixelWidth" in line:
            width = int(line.split(":")[1])
        elif "pixelHeight" in line:
            height = int(line.split(":")[1])
    return (width, height) if width and height else None


def fitted_image_frame(image_path: Path) -> dict[str, float] | None:
    """Scale to fit PHOTO_BOX preserving aspect ratio; Keynote otherwise inserts
    at 1 image-pixel = 1 point, which is far larger than the slide for a full-res
    Wikipedia thumbnail."""
    size = image_pixel_size(image_path)
    if size is None:
        return None
    pixel_width, pixel_height = size
    scale = min(PHOTO_BOX["max_width"] / pixel_width, PHOTO_BOX["max_height"] / pixel_height)
    width = pixel_width * scale
    height = pixel_height * scale
    return {"x": PHOTO_BOX["right"] - width, "y": PHOTO_BOX["top"], "width": width, "height": height}

_HOUSE_HEADING = re.compile(r"^##\s+(.+?)\s*$")
_COLOR_LINE = re.compile(r"^Color:\s*(#[0-9a-fA-F]{6})\s*$")
_SOVEREIGN_LINE = re.compile(r"^-\s+\[(.+?)\]\((.+?)\)")
_LEADING_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})-")


def parse_houses_document(houses_md_path: Path) -> list[tuple[str, str, str, Path]]:
    """Parse HOUSES.md into (name, house, color, doc_path), one per sovereign, in
    true chronological order.

    HOUSES.md groups by house (see houses_writer.py), so its own line order
    interleaves differently from history -- e.g. all of Tudor's sovereigns,
    including Mary I after the "Grey" heading, appear together under one Tudor
    heading. Re-derive the real timeline from the ISO date at the start of each
    linked document's filename (the naming.py convention) rather than trusting
    file order.
    """
    if not houses_md_path.exists():
        raise FileNotFoundError(
            f"{houses_md_path} not found -- run `wiki-kings houses --slug ... --title ...` "
            "first; this script reads HOUSES.md as the normative sovereign/house/color list, "
            "rather than re-deriving them from the documents directory."
        )

    current_house = ""
    current_color = ""
    entries = []  # (sort_key, name, house, color, doc_path)
    for line in houses_md_path.read_text(encoding="utf-8").splitlines():
        heading_match = _HOUSE_HEADING.match(line)
        if heading_match:
            current_house = heading_match.group(1)
            current_color = ""
            continue
        color_match = _COLOR_LINE.match(line)
        if color_match:
            current_color = color_match.group(1)
            continue
        sovereign_match = _SOVEREIGN_LINE.match(line)
        if sovereign_match:
            name, link = sovereign_match.group(1), sovereign_match.group(2)
            doc_path = (houses_md_path.parent / link).resolve()
            date_match = _LEADING_DATE.match(Path(link).name)
            sort_key = date_match.group(1) if date_match else "9999-99-99"
            entries.append((sort_key, name, current_house, current_color, doc_path))

    entries.sort(key=lambda e: e[0])
    return [(name, house, color, doc_path) for _, name, house, color, doc_path in entries]


_HEADING = re.compile(r"^#\s+(.+?)\s*$")
_IMAGE_LINK = re.compile(r"!\[.*?\]\((.*?)\)")
_FIELD_LINE = re.compile(r"^-\s+\*\*(.+?)\*\*:\s*(.*)$")


def parse_doc(doc_path: Path) -> tuple[str, Path | None, dict[str, str]]:
    text = doc_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    heading_match = _HEADING.match(lines[0])
    heading = heading_match.group(1) if heading_match else doc_path.stem

    image_match = _IMAGE_LINK.search(text)
    image_path = (doc_path.parent / image_match.group(1)).resolve() if image_match else None

    fields: dict[str, str] = {}
    for line in lines:
        field_match = _FIELD_LINE.match(line)
        if field_match:
            fields[field_match.group(1)] = field_match.group(2)

    return heading, image_path, fields


def applescript_string(value: str) -> str:
    """Quote a Python string as an AppleScript string literal."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def applescript_multiline(lines: list[str]) -> str:
    """Join lines as an AppleScript expression using `return` for line breaks,
    since AppleScript string literals can't contain a literal newline."""
    if not lines:
        return '""'
    return " & return & ".join(applescript_string(line) for line in lines)


def build_slide_script(
    heading: str, image_path: Path | None, fields: dict[str, str],
    house: str, house_color_hex: str | None,
) -> str:
    body_lines = [f"{key}: {fields[key]}" for key in BODY_FIELDS if fields.get(key)]

    parts = [
        # Without an explicit base layout, a new slide inherits the theme's default
        # (here "Title, Bullets & Photo"), whose placeholder boxes ("Slide Title",
        # "Slide bullet text", ...) stay behind our own text items -- invisible in an
        # export (empty placeholders don't render) but visibly overlapping in edit
        # mode. "Blank" has no placeholders at all.
        "set s to make new slide at end of slides with properties "
        '{base layout:slide layout "Blank" of thePres}',
        "tell s",
    ]

    item_index = 0

    if house:
        item_index += 1
        r, g, b = hex_to_rgb65535(house_color_hex or "#ffffff")
        parts += [
            f"    make new text item with properties {{object text:{applescript_string(house.upper())}, "
            f"position:{{{HOUSE_BOX['x']}, {HOUSE_BOX['y']}}}, "
            f"width:{HOUSE_BOX['width']}, height:{HOUSE_BOX['height']}}}",
            f"    set houseItem to text item {item_index} of s",
            "    set size of object text of houseItem to 26",
            f"    set color of object text of houseItem to {{{r}, {g}, {b}}}",
        ]

    item_index += 1
    parts += [
        f"    make new text item with properties {{object text:{applescript_string(heading)}, "
        f"position:{{{TITLE_BOX['x']}, {TITLE_BOX['y']}}}, "
        f"width:{TITLE_BOX['width']}, height:{TITLE_BOX['height']}}}",
        f"    set titleItem to text item {item_index} of s",
        "    set size of object text of titleItem to 36",
    ]

    item_index += 1
    parts += [
        f"    make new text item with properties {{object text:{applescript_multiline(body_lines)}, "
        f"position:{{{BODY_BOX['x']}, {BODY_BOX['y']}}}, "
        f"width:{BODY_BOX['width']}, height:{BODY_BOX['height']}}}",
        f"    set bodyItem to text item {item_index} of s",
        "    set size of object text of bodyItem to 20",
    ]
    frame = fitted_image_frame(image_path) if image_path is not None and image_path.exists() else None
    if frame is not None:
        posix_path = applescript_string(str(image_path))
        parts.append(
            f"    try\n"
            f"        make new image with properties {{file:(POSIX file {posix_path} as alias), "
            f"position:{{{frame['x']:.1f}, {frame['y']:.1f}}}, "
            f"width:{frame['width']:.1f}, height:{frame['height']:.1f}}}\n"
            "    end try"
        )
    parts.append("end tell")
    return "\n".join(parts)


def build_deck_script(slug: str, deck_title: str, limit: int | None, theme: str) -> str:
    houses_md_path = ROOT / "output" / slug / "HOUSES.md"
    entries = parse_houses_document(houses_md_path)
    if limit:
        entries = entries[:limit]

    slide_scripts = []
    for name, house, color, doc_path in entries:
        _, image_path, fields = parse_doc(doc_path)
        slide_scripts.append(
            build_slide_script(name, image_path, fields, house, color or None)
        )

    header = f"""tell application "Keynote"
    activate
    set thePres to make new document with properties {{document theme:theme {applescript_string(theme)}}}
    tell thePres
        set object text of default title item of slide 1 to {applescript_string(deck_title)}
        try
            set object text of default body item of slide 1 to {applescript_string(f"{len(entries)} monarchs")}
        end try
"""
    footer = """    end tell
end tell
"""
    return header + "\n\n".join(slide_scripts) + "\n" + footer


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", default="kings_of_the_united_kingdom")
    parser.add_argument("--title", default="Kings and Queens of the United Kingdom")
    parser.add_argument("--limit", type=int, default=None, help="Only build the first N slides (for testing)")
    parser.add_argument("--out", default=str(ROOT / "scripts" / "deck.applescript"))
    parser.add_argument("--theme", default="Basic Black", help="Keynote theme name; new text items inherit its default text color")
    args = parser.parse_args()

    script = build_deck_script(args.slug, args.title, args.limit, args.theme)
    out_path = Path(args.out)
    out_path.write_text(script, encoding="utf-8")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
