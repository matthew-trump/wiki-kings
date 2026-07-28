# PROGRESS.md

A narrative account of how wiki-kings got built, in the order things happened, with
emphasis on non-obvious bugs and the reasoning behind fixes. This repo has no git
history to fall back on (it isn't a git repository), so this file -- not `git log` --
is the record of *why* the code looks the way it does. For the current architecture
and command reference, see `CLAUDE.md`; this file is the story behind it.

## 1. Core pipeline: one Wikipedia page -> Markdown doc + thumbnail

Built `src/wiki_kings/` as a small package rather than a script: `wikipedia_client.py`
(MediaWiki API), `infobox.py` (wikitext -> clean field dict), `dates.py`, `naming.py`,
`images.py`, `markdown_writer.py`, `cli.py`. Verified end to end against the real
Charles III Wikipedia page before generalizing.

The hard part was `infobox.py`. Infobox values are full wikitext -- citations,
footnotes, nested templates, sub-infoboxes (`module = {{Infobox person | embed = yes |
... }}`) -- not plain text. `clean_value()` strips comments/`<ref>` tags, resolves
templates via `_resolve_templates()`, then unwraps `[[wikilinks]]` and markup. One real
bug here: `wikitextparser` leaves a rewritten template's span still tagged as a
template even once it's plain text, so a naive "re-scan `.templates` and repeat until
none are left" loop would pick its own `{{sndash}}` -> `–` replacement back up as an
unrecognized template and blank it out. Fixed by taking one snapshot of top-level
templates and rewriting each exactly once.

## 2. Walking the predecessor chain backwards

Added `--follow-predecessors --stop-at "..."` to `cli.py`: fetch a page, save it,
follow its infobox's Predecessor link, repeat. Needed the *raw* (unresolved-link)
infobox fields alongside the cleaned display fields, since the cleaned "Predecessor"
value (e.g. `"George VI"`) has already lost the wikilink target needed to fetch that
page -- `parse_infobox_raw()` and `find_predecessor_target()` exist because of this.

Running it from Charles III toward William the Conqueror surfaced a run of real
wikitext quirks, fixed one at a time as they broke the chain:
- `&nbsp;` in dates/links decodes to U+00A0, not ASCII space -- was corrupting
  filenames (`GEORGE VI` instead of `GEORGE_VI`).
- `{{Start and end dates|...}}` (single-year reigns, e.g. Edward VIII) wasn't handled.
- Pre-1752 Old Style/New Style dual dates (`11/22 June 1727`) broke date parsing.
- A file name pasted into an infobox as literal `%2C`/`%28...%29` (URL-encoded by
  mistake) needed `unquote()`-ing before it was a valid MediaWiki title.
- Medieval reigns recorded to year-only precision (`reign = 1216 – 1272`) needed a
  `coronation`-field fallback, then a last-resort year-only (Jan 1) approximation.

## 3. The England/Scotland fork

The chain reached James VI and I -- the start of the personal union -- and picked the
wrong predecessor: his infobox has an unnumbered Scotland succession box
(`predecessor` -> Mary, Queen of Scots) *and* a numbered England one (`predecessor1`
-> Elizabeth I). The "prefer the unnumbered field" heuristic (correct for
single-fork cases like George V, who's also Emperor of India) walked into Scottish
history and would never reach William the Conqueror. By the time this was caught, 11
Scottish-line documents had already been generated.

Fixed `find_predecessor_target()` to prefer whichever candidate's sibling
`succession`/`successionN` field mentions England when a real fork exists. Rather than
delete the 11 already-generated Scottish files, moved them into their own
`output/kings_of_scotland/` slug -- accurate data, just a different line, worth
keeping. The corrected chain then ran clean all the way to William the Conqueror: 42
monarchs, one run, no further errors.

## 4. INDEX.md

`index_writer.py` builds a chronological, linked list from the documents directory
alone -- ordering and the displayed date both come from each filename's leading ISO
date (the `naming.py` convention), so it doesn't need to re-parse each document's
free-text Reign field to stay correct.

## 5. The Keynote deck -- most of the trial and error happened here

`scripts/build_keynote_deck.py` is deliberately not part of the installed package: it
doesn't touch the `.key` file format directly (it's a protobuf/IWA binary archive, not
worth reverse-engineering) but drives a running Keynote via AppleScript, the same way
a person would. It reads the same 42 documents as `INDEX.md`, generates one big
`.applescript` file, and runs it once via `osascript` -- far more reliable than many
small `osascript` calls, since each one is a slow round trip and Keynote state needs
to stay consistent across all 42 slides.

**Text overlapping text.** The first version positioned title and body text items with
only `position` set, no `height`. Keynote vertically centers text within a text item's
box, and an unset (large default) box height meant the centered title visibly spilled
into the body's space. Fixed by giving both boxes explicit heights and a real gap
(`TITLE_BOX`, `BODY_BOX` constants).

**Images the size of the slide.** Images inserted via `make new image` default to 1
source pixel = 1 point. A 500x833px Wikipedia thumbnail came in at nearly the size of
the entire 1024x768 slide canvas. Fixed by shelling out to `sips -g pixelWidth -g
pixelHeight` for each image's real dimensions and computing a scaled `width`/`height`
that fits a fixed photo box while preserving aspect ratio (`fitted_image_frame()`).

**White text on black background.** Rather than fight Keynote's scripting dictionary
for background-fill and text-color properties (slide objects don't expose a
`background` property at all, per `sdef`), switched the whole document to the `Basic
Black` theme. Manually-created `text item`s (as opposed to real theme placeholders)
pick up a theme's default *new-text* color, and Basic Black's happens to already be
white -- confirmed by creating one bare text item and exporting before trusting it,
rather than assuming.

**The ghost-placeholder bug (the one that actually reached the user).** The deck
looked completely clean in every exported-PNG check along the way -- because Keynote
does not render empty placeholder prompt text ("Slide Title", "Slide bullet text",
...) in an *export*, only in its live edit view. New slides, created without an
explicit layout, were inheriting the theme's default new-slide layout ("Title,
Bullets & Photo"), whose title/subtitle/bullet placeholders sat directly behind the
manually-added text items -- invisible in every PNG this session generated, but
visibly overlapping garbled text the moment the user actually opened the `.key` file
in Keynote. This is the reason `scripts/build_keynote_deck.py`'s slide-creation line
explicitly requests `base layout:slide layout "Blank" of thePres` now, and it's the
reason to distrust "I exported it and it looks fine" as proof of a clean Keynote
*document* going forward -- it only proves the rendered content is fine, not that the
file is free of stray editable objects.

Chasing that bug down turned up one more wrinkle: even a `Blank`-layout slide still
carries two empty, zero-position text item objects, and Keynote refuses to `delete`
them via scripting (`AppleEvent handler failed`, error -10000) -- they appear to be
tied to the layout itself, not regular deletable shapes. Left alone rather than
fought: `title showing`/`body showing` are `false` by default on `Blank` (unlike the
old default layout, where they were `true` with no content -- exactly what made the
prompt text render), and the two phantom items consistently appear *after* the ones
this script creates, so `text item 1`/`text item 2` still correctly address the real
title/body without any extra bookkeeping.

**Verifying any of this was its own obstacle.** `screencapture -l<window id>` failed
outright ("could not create image from window"). `System Events` UI-element access was
denied (-25211, no Accessibility permission granted to this terminal). Full-screen
`screencapture` worked as a raw command but repeatedly captured the wrong
frontmost window/Space rather than Keynote's actual document window, so it couldn't be
used to positively confirm edit-mode appearance from this side. Landed on querying
Keynote's own object model instead (item counts, index order, `title showing`/`body
showing`) as a substitute for a screenshot, then asked the user to do the actual visual
confirmation in their own Keynote session -- which is what caught the bug in the first
place, and what ultimately confirmed the fix.

## Current state

- Tests: 35/35 passing (`python -m pytest -q`), all pure-logic, no network calls.
- `output/kings_of_the_united_kingdom/`: 42 monarchs, William the Conqueror (1066) ->
  Charles III (2022) -- `documents/`, `images/`, `INDEX.md`, `UK_Monarchs.key`.
- `output/kings_of_scotland/`: 11 monarchs, John Balliol -> Mary, Queen of Scots --
  the England/Scotland fork byproduct (section 3), `documents/` + `images/` only.
- `output/kings_of_united_kingdom/` and `output/presidents_of_the_united_states/`:
  still-empty placeholders that predate this project's slug convention.

## Not done yet

- `kings_of_scotland` doesn't extend further back (e.g. to Kenneth MacAlpin) and has
  no `INDEX.md` or Keynote deck of its own.
- `presidents_of_the_united_states` is unstarted.
- The Keynote deck's body fields (Reign / Birth Date / Death Date / House) are a fixed
  list in `build_keynote_deck.py`, not configurable per run.
