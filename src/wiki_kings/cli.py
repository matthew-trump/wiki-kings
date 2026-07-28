"""End-to-end pipeline: Wikipedia page -> infobox Markdown doc + thumbnail image.

    wiki-kings fetch --page "Charles III" --slug kings_of_the_united_kingdom

    wiki-kings fetch --page "Charles III" --slug kings_of_the_united_kingdom \\
        --follow-predecessors --stop-at "William the Conqueror" --max-steps 60

    wiki-kings index --slug kings_of_the_united_kingdom \\
        --title "Kings and Queens of the United Kingdom"
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import dates, images, naming
from .index_writer import build_index
from .infobox import find_predecessor_target, parse_infobox, parse_infobox_raw
from .markdown_writer import render_markdown, write_markdown
from .wikipedia_client import WikipediaError, fetch_wikitext


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch = subparsers.add_parser("fetch", help="Save one Wikipedia page's infobox, optionally chained")
    fetch.add_argument("--page", required=True, help="Wikipedia article title, e.g. 'Charles III'")
    fetch.add_argument("--slug", required=True, help="Output slug title, e.g. 'kings_of_the_united_kingdom'")
    fetch.add_argument("--regnal-name", help="Defaults to --page (ignored with --follow-predecessors)")
    fetch.add_argument(
        "--start-date",
        help="YYYY-MM-DD; auto-detected from the infobox if omitted (ignored with --follow-predecessors)",
    )
    fetch.add_argument("--output-root", default="output", help="Defaults to ./output")
    fetch.add_argument("--thumb-width", type=int, default=400)
    fetch.add_argument(
        "--follow-predecessors",
        action="store_true",
        help="After saving --page, follow its infobox 'Predecessor' link backwards in "
        "time, saving each one in turn, until --stop-at is reached",
    )
    fetch.add_argument(
        "--stop-at",
        help="Page title at which to stop the --follow-predecessors chain (inclusive)",
    )
    fetch.add_argument(
        "--max-steps", type=int, default=25, help="Safety cap on --follow-predecessors chain length"
    )

    index = subparsers.add_parser("index", help="Build a chronological, linked INDEX.md for one slug")
    index.add_argument("--slug", required=True, help="Output slug title, e.g. 'kings_of_the_united_kingdom'")
    index.add_argument("--title", required=True, help="Heading for the index, e.g. 'Kings and Queens of the UK'")
    index.add_argument("--output-root", default="output", help="Defaults to ./output")

    return parser


def process_page(
    page: str,
    *,
    slug: str,
    output_root: Path,
    regnal_name: str | None,
    start_date: str | None,
    thumb_width: int,
) -> "OrderedDict[str, str] | None":
    """Save one page's infobox as Markdown + thumbnail.

    Returns the page's *raw* (unresolved-link) infobox fields, which callers can use to
    keep walking a chain (e.g. reading a fresh Predecessor link before it gets flattened
    to display text) -- or None if the page couldn't be processed.
    """
    try:
        wikitext = fetch_wikitext(page)
        fields = parse_infobox(wikitext)
        raw_fields = parse_infobox_raw(wikitext)
    except (WikipediaError, ValueError) as exc:
        print(f"error: {page}: {exc}", file=sys.stderr)
        return None

    resolved_regnal_name = regnal_name or page.replace("_", " ")

    if start_date:
        resolved_start_date = start_date
    else:
        detected = dates.find_start_date(fields)
        if detected is None:
            print(
                f"error: {page}: could not auto-detect a start date from the infobox "
                "(checked: reign, term_start, reign1) -- pass --start-date YYYY-MM-DD",
                file=sys.stderr,
            )
            return None
        resolved_start_date = detected.isoformat()

    doc_path = naming.document_path(output_root, slug, resolved_start_date, resolved_regnal_name)
    image_stem = naming.image_path_stem(output_root, slug, resolved_start_date, resolved_regnal_name)

    image_relpath = None
    image_file = fields.get("image")
    if image_file:
        image_dest = images.save_thumbnail(image_file, image_stem, thumb_width=thumb_width)
        image_relpath = os.path.relpath(image_dest, doc_path.parent)
        print(f"saved image: {image_dest}")

    content = render_markdown(regnal_name=resolved_regnal_name, fields=fields, image_relpath=image_relpath)
    write_markdown(doc_path, content)
    print(f"saved document: {doc_path}")
    return raw_fields


def run(args: argparse.Namespace) -> int:
    raw_fields = process_page(
        args.page,
        slug=args.slug,
        output_root=Path(args.output_root),
        regnal_name=args.regnal_name,
        start_date=args.start_date,
        thumb_width=args.thumb_width,
    )
    return 0 if raw_fields is not None else 1


def run_chain(args: argparse.Namespace) -> int:
    output_root = Path(args.output_root)
    stop_normalized = args.stop_at.strip().lower()
    page = args.page
    visited: set[str] = set()

    for step in range(args.max_steps):
        normalized = page.strip().lower()
        if normalized in visited:
            print(f"error: predecessor chain looped back to already-visited page {page!r}", file=sys.stderr)
            return 1
        visited.add(normalized)

        raw_fields = process_page(
            page,
            slug=args.slug,
            output_root=output_root,
            regnal_name=None,
            start_date=None,
            thumb_width=args.thumb_width,
        )
        if raw_fields is None:
            return 1

        if normalized == stop_normalized:
            print(f"reached stop page {page!r}; chain complete ({step + 1} page(s))")
            return 0

        predecessor = find_predecessor_target(raw_fields)
        if not predecessor:
            print(
                f"error: {page!r} has no linked Predecessor field; "
                f"stopped before reaching {args.stop_at!r}",
                file=sys.stderr,
            )
            return 1
        page = predecessor

    print(f"error: hit --max-steps={args.max_steps} without reaching {args.stop_at!r}", file=sys.stderr)
    return 1


def run_index(args: argparse.Namespace) -> int:
    index_path = build_index(Path(args.output_root), args.slug, args.title)
    print(f"saved index: {index_path}")
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "index":
        sys.exit(run_index(args))

    if args.follow_predecessors and not args.stop_at:
        parser.error("--follow-predecessors requires --stop-at")
    if args.follow_predecessors:
        sys.exit(run_chain(args))
    else:
        sys.exit(run(args))


if __name__ == "__main__":
    main()
