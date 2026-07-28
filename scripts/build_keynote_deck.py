"""Build a Keynote deck from the generated monarch documents.

Reads output/{slug}/documents/*-INFOBOX.md (same chronological ordering as
index_writer.build_index), pulls out a title, a handful of infobox fields, and the
saved thumbnail, and emits an AppleScript file that drives Keynote to build one
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
FIELDS_TO_SHOW = ["Reign", "Birth Date", "Death Date", "House"]

# 1024x768 (4:3) is the "White" theme's default canvas. Photo box is right-aligned
# in the right-hand column; text box is the left-hand column. Both text items get an
# explicit height -- Keynote vertically centers text within a text item's box, and an
# unset (default) height is tall enough that centered title/body text visibly overlap.
SLIDE_WIDTH = 1024
TITLE_BOX = {"x": 40, "y": 40, "width": 560, "height": 70}
BODY_BOX = {"x": 40, "y": 150, "width": 560, "height": 400}
PHOTO_BOX = {"right": 984, "top": 90, "max_width": 340, "max_height": 560}


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


def build_slide_script(heading: str, image_path: Path | None, fields: dict[str, str]) -> str:
    body_lines = [f"{key}: {fields[key]}" for key in FIELDS_TO_SHOW if fields.get(key)]

    parts = [
        # Without an explicit base layout, a new slide inherits the theme's default
        # (here "Title, Bullets & Photo"), whose placeholder boxes ("Slide Title",
        # "Slide bullet text", ...) stay behind our own text items -- invisible in an
        # export (empty placeholders don't render) but visibly overlapping in edit
        # mode. "Blank" has no placeholders at all.
        "set s to make new slide at end of slides with properties "
        '{base layout:slide layout "Blank" of thePres}',
        "tell s",
        f"    make new text item with properties {{object text:{applescript_string(heading)}, "
        f"position:{{{TITLE_BOX['x']}, {TITLE_BOX['y']}}}, "
        f"width:{TITLE_BOX['width']}, height:{TITLE_BOX['height']}}}",
        "    set titleItem to text item 1 of s",
        "    set size of object text of titleItem to 36",
        f"    make new text item with properties {{object text:{applescript_multiline(body_lines)}, "
        f"position:{{{BODY_BOX['x']}, {BODY_BOX['y']}}}, "
        f"width:{BODY_BOX['width']}, height:{BODY_BOX['height']}}}",
        "    set bodyItem to text item 2 of s",
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
    documents_dir = ROOT / "output" / slug / "documents"
    doc_paths = sorted(documents_dir.glob("*-INFOBOX.md"))
    if limit:
        doc_paths = doc_paths[:limit]

    slide_scripts = []
    for doc_path in doc_paths:
        heading, image_path, fields = parse_doc(doc_path)
        slide_scripts.append(build_slide_script(heading, image_path, fields))

    header = f"""tell application "Keynote"
    activate
    set thePres to make new document with properties {{document theme:theme {applescript_string(theme)}}}
    tell thePres
        set object text of default title item of slide 1 to {applescript_string(deck_title)}
        try
            set object text of default body item of slide 1 to {applescript_string(f"{len(doc_paths)} monarchs")}
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
