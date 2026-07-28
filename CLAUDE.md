# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository. See `PROGRESS.md` for the narrative history of how this was built -- this repo has no git history, so it's the only record of *why* things are the way they are (particularly worth reading before touching `scripts/build_keynote_deck.py`, where most of the non-obvious bugs live).

## Commands

```bash
# setup (once)
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# run the pipeline for one subject
python -m wiki_kings.cli --page "Charles III" --slug kings_of_the_united_kingdom
# or, if installed: wiki-kings --page "Charles III" --slug kings_of_the_united_kingdom

# follow a chain of predecessors backwards in time, inclusive of --stop-at
python -m wiki_kings.cli --page "Charles III" --slug kings_of_the_united_kingdom \
    --follow-predecessors --stop-at "William the Conqueror" --max-steps 60

# tests (pure logic, no network calls)
python -m pytest -q
python -m pytest tests/test_infobox.py -q          # single file
python -m pytest tests/test_infobox.py::test_parse_infobox_flattens_nested_modules -q  # single test
```

`--page` is any English Wikipedia article title. `--slug` is the output folder name. `--regnal-name` and `--start-date` (YYYY-MM-DD) override the auto-detected values if the heuristics below get something wrong.

## Purpose

Create new media by extracting structured data from Wikipedia. The initial scope (see `PROJECT.md`) is to build up data entries for lines of sovereigns/leaders — starting with the United Kingdom's monarchs (e.g. Charles III) — by parsing each Wikipedia infobox into a Markdown document plus a saved profile image.

## Output conventions (defined in PROJECT.md)

For each subject, two artifacts are produced under `./output/{slug_title}/`:

1. **Infobox document** — everything inside the Wikipedia infobox, written as concise Markdown to:
   `./output/{slug_title}/documents/{YYYY-MM-DD start of reign}-{REGNAL_NAME_ALL_CAPS_WITH_UNDERSCORES}-INFOBOX.md`
   - Example: `./output/kings_of_the_united_kingdom/documents/2022-09-08-CHARLES_III-INFOBOX.md`
   - The document should include a link to the saved thumbnail image.

2. **Profile thumbnail image** — saved in its original format (typically JPEG) to:
   `./output/{slug_title}/images/{YYYY-MM-DD start of reign}-{REGNAL_NAME_ALL_CAPS_WITH_UNDERSCORES}`

Note: `output/kings_of_united_kingdom` and `output/presidents_of_the_united_states` are pre-existing empty placeholder folders that predate this slug convention (missing "the", no content) — leave them alone unless asked to clean them up; new runs correctly create `output/kings_of_the_united_kingdom/...`.

`output/kings_of_the_united_kingdom/` holds the confirmed English/British/UK line: Charles III back to William the Conqueror (1066), 42 monarchs, generated with `--follow-predecessors --stop-at "William the Conqueror"`. `output/kings_of_scotland/` holds 11 Scottish monarchs (John Balliol through Mary, Queen of Scots) that a first, buggy run of that same chain walked into by mistake at the England/Scotland fork described below — moved here rather than deleted once the fork was understood, since they're accurate data, just a different line of succession. It isn't itself the output of a `--follow-predecessors` run and doesn't currently connect any further back (e.g. to Kenneth MacAlpin); treat it as a manually-curated starting point if that line gets extended later.

`output/kings_of_the_united_kingdom/INDEX.md` is a generated, chronologically-ordered list linking to each of the 42 documents (`wiki-kings index --slug ...`), and `output/kings_of_the_united_kingdom/UK_Monarchs.key` is a Keynote deck (one slide per monarch: name, Reign/Birth Date/Death Date/House, thumbnail) built by `scripts/build_keynote_deck.py`, which isn't part of the installed package -- it drives Keynote directly via a generated AppleScript file (`scripts/deck.applescript`, gitignored) rather than touching the `.key` binary format. Regenerate with:
```bash
python scripts/build_keynote_deck.py   # writes scripts/deck.applescript
osascript scripts/deck.applescript     # builds the deck in a running Keynote
```
It leaves the result open and unsaved in Keynote; save it manually (`save document 1 in POSIX file "..."` via `osascript`, or Cmd-S in the app) once you're happy with it, since re-running the generator always creates a *new* Keynote document rather than updating one in place.

Default theme is `Basic Black` (`--theme` to override) specifically because manually-created `text item`s (as opposed to real placeholders) pick up a theme's default new-text color, and Basic Black's is white -- giving white-text-on-black with no per-element color styling needed. Don't assume that holds for an arbitrary theme; check a rendered slide before trusting it.

Each slide is created with `base layout:slide layout "Blank" of thePres`, not the theme's default new-slide layout -- without that, slides inherit whatever layout Keynote defaults to (observed: "Title, Bullets & Photo"), and its title/subtitle/bullet placeholders sit behind our own text items. Harmless in an *export* (empty placeholders don't render there) but visibly overlapping, confusing prompt text ("Slide Title", "Slide bullet text", ...) in Keynote's actual edit view -- exporting to PNG to sanity-check a slide will not catch this class of bug, only opening the real `.key` file will. Even "Blank" layout slides carry a couple of empty, zero-position text item objects that Keynote won't let you `delete` (fails with "AppleEvent handler failed") -- leave them; `title showing`/`body showing` are `false` by default on Blank, which is what actually suppresses them, and they trail after (not before) the text items we create, so `text item 1`/`text item 2` still correctly address our own title/body.

## Reference material

`reference/wp-charles-iii-title.png` and `reference/wp-charles-iii-infobox.png` are screenshots of the target Wikipedia page structure (title and infobox).

## Architecture

The pipeline (`src/wiki_kings/`) goes: MediaWiki API → raw wikitext → parsed infobox dict → Markdown + image files.

- **`wikipedia_client.py`** — talks to the MediaWiki API (`action=parse` for wikitext, `action=query&prop=imageinfo` to resolve a `File:` name to a thumbnail URL).
- **`infobox.py`** — the core parser, and the part most likely to need extending for new subjects. Wikipedia infoboxes are MediaWiki templates whose values are themselves wikitext (citations, footnotes, links, formatting templates), and royalty/officeholder infoboxes nest sub-infoboxes via `module = {{Infobox person | embed = yes | ... | module = {{Infobox officeholder | ... }} }}`. `parse_infobox()` recursively flattens all of that into one ordered `{field: plain_text}` dict:
  - `find_first_infobox()` extracts the first top-level `{{Infobox ...}}` block by brace-matching (not regex-only, since infobox bodies contain arbitrarily nested `{{ }}`).
  - `_flatten_template()` walks `module=` nesting and merges child infobox fields into the same flat dict, dropping plumbing params (`module`, `embed`, `child`, ...).
  - `clean_value()` renders one field's raw wikitext to plain text: strips comments/`<ref>` tags, then resolves templates via `_resolve_templates()`, then unwraps `[[wikilinks]]` and `'''bold'''`/`''italics''`.
  - `_resolve_templates()` only rewrites **top-level** templates in a value, once, via a snapshot list — deliberately not a "re-scan and repeat" loop. wikitextparser leaves a mutated template span still tagged as a template, so re-querying `.templates` after a rewrite picks the same span back up (e.g. a rewritten `{{sndash}}` → `–` gets treated as a new unrecognized template and blanked out on the next scan). Nested templates are handled separately: `_render_template()` recurses into each argument via `clean_value()` on a fresh, independent parse tree, so top-level-only replacement is sufficient and the zombie-span bug never triggers.
  - `_render_template()` special-cases the templates that actually show up in these infoboxes (`{{sndash}}`, `{{nowrap}}`, `{{marriage}}`, `{{birth date and age}}`, `{{plainlist}}`/`{{ubl}}`/list templates, citation/footnote templates that should just disappear) and falls back to a template's first positional argument for anything unrecognized, since name/link-formatting templates conventionally put their display text there.
- **`dates.py`** — best-effort extraction of the reign/term start date (for the output filename) out of infobox prose like `8 September 2022–present`, checked in `REIGN_START_FIELDS` order (`reign`, `term_start`, `reign1`, `coronation`, `coronation1`). Falls back to a year-only date (1 January) when even `coronation` lacks day/month precision, which starts happening for reigns before roughly Henry III (1216) — better than failing outright this far back. Override with `--start-date` for a single `--page` run when a subject's infobox doesn't fit any of this.
- **`naming.py`** — the exact output path convention from `PROJECT.md` (`document_path()`, `image_path_stem()`); this is the single source of truth for the file-naming scheme, don't recompute it inline elsewhere.
- **`images.py`** / **`markdown_writer.py`** — save the thumbnail (extension taken from the resolved URL, so SVG/PNG/JPEG all come out correctly) and render the field dict to Markdown with a relative link to the saved image.
- **`cli.py`** — wires the above together. `process_page()` does the single-page fetch/parse/save and returns that page's *raw* (unresolved-link) infobox fields; both `run()` (one page) and `run_chain()` (`--follow-predecessors`) call it. `run_chain()` re-derives the next page from `find_predecessor_target(raw_fields)` each iteration rather than reusing the already-cleaned display text, since the cleaned "Predecessor" value (e.g. `"George VI"`) has lost the wikilink target needed to fetch that page. It stops when the current page matches `--stop-at` (case-insensitive, inclusive), a page repeats (cycle guard), no predecessor link can be found, or `--max-steps` is hit.

Infobox quirks worth knowing before touching `infobox.py` again:
- Some infoboxes write dates/links with `&nbsp;` instead of a literal space (e.g. Elizabeth II's `predecessor = [[George&nbsp;VI]]`). `html.unescape()` turns that into U+00A0 (a *non-breaking* space), not ASCII `" "` — code that later does `.replace(" ", "_")` (see `naming.regnal_slug`) or whitespace-sensitive regex matching (see `dates.py`) will silently miss it unless the value is re-normalized with `\s+` first. Both `clean_value()` and `first_wikilink_target()` do this; keep doing it in anything new that touches raw wikitext.
- Mutating a `wikitextparser` `Template.string` doesn't remove that span's "this is a template" tag even once it's plain text — re-scanning `.templates` afterward can pick the same span back up and re-process it as an (unrecognized) template, silently wiping out the replacement. `_resolve_templates()` avoids this by only ever taking one snapshot of the *top-level* templates and rewriting each once.
- Multi-throne monarchs number their succession-box fields (`predecessor1`, `successor1`, `succession1`, ...) instead of, or alongside, unnumbered ones. Usually any of them lead to the same next monarch (e.g. George V, also Emperor of India), but at the *start* of a personal union it's a genuine fork: James VI and I has an unnumbered Scotland box (`predecessor` → Mary, Queen of Scots) and a numbered England box (`predecessor1` → Elizabeth I) leading to two different lines of succession. `find_predecessor_target()` handles this by preferring whichever candidate's sibling `succession`/`successionN` field mentions `prefer_realm` (default `"england"`); pass `prefer_realm=None` for the old "prefer unnumbered, then lowest-numbered" behavior. Walking the Scotland branch instead of correcting this is exactly how `output/kings_of_scotland/` came to exist (see above) — it never reaches William the Conqueror, an English king.
- A file name pasted into an infobox can itself be URL-encoded by mistake (Mary, Queen of Scots' portrait is `François Clouet - Mary%2C Queen of Scots %281542-87%29 - ....jpg` in the wikitext). `wikipedia_client.fetch_thumbnail_url()` unconditionally `unquote()`s the filename before querying — safe to do unconditionally since MediaWiki titles can never legitimately contain a raw `%XX` sequence.
