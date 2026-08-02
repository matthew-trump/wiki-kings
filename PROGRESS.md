# PROGRESS.md

A narrative account of how wiki-kings got built, in the order things happened, with
emphasis on non-obvious bugs and the reasoning behind fixes. Sections 1-8 predate
this repo having git history at all, and even now the commit log is coarse (a few
large commits, not one per change) -- this file, not `git log`, is the record of
*why* the code looks the way it does. For the current architecture and command
reference, see `CLAUDE.md`; this file is the story behind it.

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

## 6. House color-coding, and putting House at the top

Once the deck itself was clean, the next ask was to make each monarch's Dynastic
House more prominent (moved from a body bullet line to its own colored label at the
top of the slide) and to color-code it per house, with nearby houses in the
chronological sequence kept visually distinct rather than similar.

This is a categorical-color-by-identity problem, so it went through the `dataviz`
skill rather than picking colors by eye: fixed hue order, never cycled past 8 without
a documented reason, and every claim about two colors being distinguishable run
through `scripts/validate_palette.js` (OKLab distance under simulated color-vision
deficiency, plus a stricter normal-vision floor) rather than eyeballed.

**Normalizing the House field came first, and mattered.** The raw data has 16
distinct strings but only 12 real dynasties: "Plantagenet-Angevin" and
"Plantagenet–Angevin" (different dash characters across different monarchs' infobox
authors) are the same continuous House of Plantagenet with no actual dynasty change
in between, and three monarchs whose reigns straddled the 1917 anti-German renaming
(Saxe-Coburg and Gotha -> Windsor) carry compound fields like `"Saxe-Coburg and Gotha
(until 1917); Windsor (from 1917)"`. Coloring `"Plantagenet"` and
`"Plantagenet-Angevin"` differently would have been actively *wrong* -- it would
visually assert a dynasty change across Henry II -> Richard II that never happened.
`normalize_house()` collapses both cases before anything else runs.

**12 houses, 8 fixed hues.** The reference palette (`references/palette.md`) is
deliberately 8 slots, never a generated 9th hue. With 12 houses, 4 must reuse an
earlier slot. The naive move -- cycle slots 1-8 then wrap to 1-2-3-4 -- silently
breaks: Hanover would land on slot 2 (orange) immediately after Stuart's slot 8
(red), and `validate_palette.js` confirms that specific pair is a hard fail (normal-
vision dE 7.1, floor is 15) even though neither color individually did anything
wrong. Fixed by checking each reused slot against its *actual* chronological
neighbors rather than trusting the cycle: Hanover reuses Grey's violet instead
(Stuart -> violet passes at dE 22.5), which also meant re-deriving where Saxe-Coburg
and Gotha and Windsor land so *their* transitions stayed clean too. Full assignment,
with the reasoning for each choice, is the `HOUSE_COLORS` dict and its comment in
`scripts/build_keynote_deck.py`.

**Why the mapping is hardcoded, not computed at deck-build time.** The validator
lives in the dataviz skill's bundled directory, a path that's specific to this
session and not guaranteed to exist the next time this script runs. Rather than a
Keynote-deck generator depending on a skill being loaded, the validation was done
once, by hand, with the exact commands recorded above, and the *result* -- a plain
Python dict of already-proven-good hex values -- is what's committed. This mirrors
how `references/palette.md` itself works: a pre-validated constant table, not
something recomputed live. `assign_house_colors()` still degrades gracefully for any
house name outside this table (a different slug/dataset) by cycling the same 8 hues
unvalidated, clearly commented as a best-effort fallback, not a substitute for
re-running the real check.

**Layout mechanics.** The House label is its own `text item` (`HOUSE_BOX`, top of
slide, ~26pt, uppercased, colored via `color of object text of houseItem` set from
an RGB-0..65535 triple -- Keynote's AppleScript color properties don't take hex),
sitting above the existing title/body boxes, which shifted down to make room. Text
item index bookkeeping (`text item 1 of s`, `2 of s`, ...) had to become dynamic
rather than hardcoded once the House label became a conditionally-present item ahead
of the title.

## 7. HOUSES.md, and the reign-date bugs it dragged into the light

The ask was simple -- a Markdown document with each House as a heading and its
sovereigns (with reign dates) listed underneath, chronological within each house --
but getting *correct* end dates turned into the biggest data-accuracy pass this
project has had. `normalize_house()` moved into its own module
(`src/wiki_kings/houses.py`) so both this and `build_keynote_deck.py` share one
implementation instead of two copies drifting apart; `houses_writer.py` groups by
house in first-appearance order (an interrupted house, e.g. Tudor around Lady Jane
Grey, still gets one heading with all its monarchs, not two split sections).

**Why "next monarch's start date" was rejected as the end-date source.** The obvious
approach -- end year = next monarch's start year -- is wrong at exactly one point:
James VI and I's own start date (1567) is his *Scottish* accession, since he'd
already been King of Scots for decades before inheriting England in 1603. Inferring
Elizabeth I's end date from his start date would show her reign ending in 1567, 36
years before she actually died. Used each monarch's own Reign field instead.

**The Reign field itself is unreliable for end dates, for a genuinely new reason.**
14 of the 42 monarchs have more than one Reign/ReignN field, and a first pass that
just took the highest-numbered one broke several: Charles II's Reign1 is a 1649-1651
Scotland-only reign that PRECEDES his main 1660-1685 reign as Reign, not a later
stint -- the generated document briefly showed his dates as `1660–1651`, the negative
range. Henry VI's Reign2 is a disputed claim to the *French* throne, unrelated to his
English one. George IV's Reign2 is his years as Prince Regent, before he was king.
The correct rule turned out to be structural: a numbered ReignN with no matching
SuccessionN of its own is just another stint of the *same* title (Edward IV: deposed
1470, restored 1471 -- no Succession1 exists, so Reign1's end, 1483, is his real
death); a ReignN that DOES have its own SuccessionN is a different title and must be
excluded (Charles II, Henry VI, George IV, Victoria, George VI all fit this). Anne is
the sole exception the structural rule gets wrong: her Reign1 has a Succession1
("Queen of Great Britain") but it's a *rename* of the same sovereignty at the 1707
Acts of Union, not a different realm -- needs an explicit, documented override
(`_REIGN_END_OVERRIDES`) rather than a cleverer general rule. All 14 cases are
individually verified against Wikipedia's actual infobox fields; see
`_primary_reign_end_source()`'s docstring in `houses_writer.py`.

**Investigating that surfaced a real, separate bug in `dates.py` -- the START date
pipeline, not just this new document.** Mary I's infobox `reign` field is `"July
1553"` -- no day, because sources genuinely disagree whether it was the 6th or the
24th. `parse_wiki_date()` had no month-year-only pattern, so it silently failed on
the *correct* field and `find_start_date()` fell through its priority list to
`reign1` -- Mary's *Queen consort of Spain* title, which happens to have full day
precision (16 January 1556) for a completely different reason. The result: her
document, filename, and every downstream artifact were dated 1556, three years
late, under a wrong title's date, purely because that wrong field happened to be
more precise. Fixed by adding month-year parsing to `parse_wiki_date()` itself (so
the correct, higher-priority field succeeds on its own and `reign1` is never
reached) rather than restructuring `find_start_date()`'s field-priority loop -- an
earlier attempt at the latter would have also broken the deliberate
coronation-over-year-only-reign fallback from section 2 (added for Henry III's
`reign = 1216 – 1272`, no month/day anywhere). While fixing this, also reordered
`REIGN_START_FIELDS` to check
`coronation` before `reign1`: a synthetic regression test (year-only reign + a
full-precision but WRONG-title reign1 + a full-precision coronation) showed the old
order would let reign1 win by precision alone, the same class of bug, even though no
monarch in the current 42 happened to trigger it.

**The cascade.** Both bugs required re-running the full `--follow-predecessors`
chain (42 network fetches) rather than hand-patching one file, since the fix changes
which *filename* a monarch gets (the ISO date is baked into it). This also
fixed a data problem noticed but not chased down earlier in this project: William
III & II's old date (1672, his Dutch Stadtholder accession -- `reign1`, again beating
`reign`'s less-precise value) had him sorting *before* James II & VII, backwards
from real history; his corrected date (1689-04-11, from `coronation`) now sorts
correctly. Old-dated files (`1556-01-16-MARY_I-*`, `1672-07-04-WILLIAM_III_&_II-*`)
were deleted as orphans once the corrected ones existed; `INDEX.md` and
`UK_Monarchs.key` were both regenerated afterward to match.

## 8. HOUSES.md becomes normative: links, recorded colors, and the deck reads it

Three asks, all pointed the same direction: link each sovereign to their document,
record each house's chosen color as its own line, and make HOUSES.md the source of
truth for "which sovereigns, in which houses, with which colors" -- rather than
`build_keynote_deck.py` independently re-scanning the documents directory and
re-running `normalize_house()`/`assign_house_colors()` from scratch, the way it had
been doing since section 6.

**Shared color logic moved into `houses.py`.** `CATEGORICAL_PALETTE_DARK`,
`HOUSE_COLORS`, and `assign_house_colors()` lived in `scripts/build_keynote_deck.py`
alone before this; moved next to `normalize_house()` (which was already shared) so
there's one definition of "what color is this house," not two that could drift.

**HOUSES.md's format**: under each `## House` heading, a `Color: #hex` line, then
each sovereign as `- [Name](documents/....md) (start–end)`. The color line's
placement (right under the heading, before any sovereigns) was specified directly --
"below the name of the house."

**Why `build_keynote_deck.py` can't just read HOUSES.md's bullets in file order.**
HOUSES.md groups by house, so a house that gets interrupted (Tudor around Lady Jane
Grey) has its sovereigns listed together under one heading, not interleaved with
Grey's -- which is exactly what makes it readable as a *houses* document, but wrong
as a slide *timeline*. `parse_houses_document()` re-derives the true order by
sorting every entry on the ISO date baked into its linked document's filename
(the naming.py convention) rather than trusting HOUSES.md's line order -- the same
insight that made `_end_year()` avoid "next monarch's start date" in section 7.
Verified by round-tripping the real 42-sovereign file and confirming Mary I lands
back between Lady Jane Grey and Elizabeth I, not after all of Tudor's other members.

**What "normative" means in practice**: `build_keynote_deck.py` no longer imports
`normalize_house` or `assign_house_colors` at all -- it has no independent opinion
about which house a sovereign belongs to or what color that house is, only what
HOUSES.md says. Hand-editing HOUSES.md (reassigning a sovereign, tweaking a hex
value) changes the next deck build without touching any code. The tradeoff: the
deck now hard-requires HOUSES.md to exist first (`wiki-kings houses --slug ...`),
where it previously worked from the documents directory alone.

## 9. Going before 1066: the Anglo-Saxon kings, and three more real bugs

The user had already hand-drafted `HOUSES_ANGLO-SAXON.md` -- Alfred the Great
through Harold Godwinson, grouped by house, with the double reign of AEthelred the
Unready (deposed by Swein Forkbeard in 1013, restored 1014) already correctly laid
out as two separate entries under "Wessex". The ask: fetch each of these from
Wikipedia the normal way, link them into that file in the same normative format as
the main `HOUSES.md`, pick validated colors for the new houses, and build a second
Keynote deck (Alfred -> Harold Godwinson) reading it -- explicitly requiring that
whatever color Godwin (Harold Godwinson's house) got had to be distinct from
Normandy's blue, since Godwinson is immediately followed, chronologically, by
William the Conqueror at the start of the *existing* deck.

**Wikipedia title resolution needed real checking, not guessing.** Several of the
16 listed names aren't the actual article title: "Edgar" alone is a disambiguation
page (needed "Edgar, King of England"); "AEthelred II" doesn't resolve at all
(needed "AEthelred the Unready"); "Cnut the Great" and "Harold I" are redirects
(to "Cnut" and "Harold Harefoot" respectively -- both fine to fetch directly, since
`fetch_wikitext` already passes `redirects=1`). Checked every title against the
live API (`has_infobox` / `is_disambiguation`) before running any fetches, rather
than discovering a wrong title after the fact.

**Fetching immediately broke on the earliest 8 kings (Alfred through Edward the
Martyr), and the reason was a real, previously-latent bug, not bad luck.** Alfred's
`reign` field is `"23 April 871 -- {{circa|886}}"`. Two problems compounded:

1. `{{circa}}` was sitting in `infobox.py`'s `_DROP_TEMPLATES` -- the set for
   citations and footnotes that carry no display value. It's neither; it's an
   approximate-date marker, and dropping it silently deleted Alfred's reign end
   entirely (`clean_value` rendered the field as `"23 April 871 --"`). Moved it to
   its own handled case, rendering `{{circa|886}}` as `"c. 886"` (matching
   Wikipedia's own visual rendering of the template) rather than either dropping it
   or silently treating an approximate date as exact.
2. Even with `{{circa}}` fixed, the *year itself* broke parsing: `dates.py`'s
   regexes required exactly 4 digits (`\d{4}`), and 871 CE is 3 digits in the
   source wikitext (`date.isoformat()` zero-pads it to `"0871"` in our own
   filenames, but the infobox text doesn't). Every date regex in `dates.py`
   (day-month-year, month-day-year, month-year, and the year-only fallback), plus
   `houses_writer.py`'s end-year extraction, needed `\d{3,4}` instead of `\d{4}`.
   This is exactly the kind of assumption ("years are always 4 digits") that holds
   for the entire rest of this project's data and silently breaks the moment you go
   back before 1000 CE.

A third, unrelated template bug turned up investigating a separate cosmetic glitch:
Edmund I's reign rendered as `"27 October 939 26 May 946"` (no separator at all).
His wikitext uses `{{dash}}`, a *different* template from `{{sndash}}`/`{{ndash}}`
and not in `_DASH_TEMPLATES` -- fell through to the generic unknown-template
fallback, which returns the first positional argument, and `{{dash}}` has none, so
it silently vanished. Added `"dash"` to `_DASH_TEMPLATES`.

**Fixing the parser didn't fix the data already fetched.** 8 monarchs (AEthelred
through Harold Godwinson) had already been fetched *before* these three fixes, using
the broken 4-digit-only year regex -- and for several of them that produced a
*wrong but non-obviously-wrong* result rather than an outright failure, because the
old code's fallback (search the whole field for a `\d{4}` match) would skip a
correct 3-digit year and grab an unrelated 4-digit one instead:
- AEthelred: `reign1 = "18 March 978 - December 1013"` (no month/day precision
  needed here, both already present) -- but the OLD code's year-only fallback,
  unable to match "978" (3 digits), searched the whole string and found "1013"
  instead, dating his document to his *deposition*, not his accession 35 years
  earlier.
- Similarly Swein Forkbeard and Harthacnut each looked "successful" but were
  silently 20-30 years off before the fix.

Re-fetched all 8 after the fixes landed and deleted the orphaned wrong-dated files
-- the same "fix the parser, then redo the fetch, then clean up the orphan" pattern
from section 7's Mary I / William III & II fix, now recurring for a second, unrelated
root cause.

**Multiple realms strike again, for start dates this time.** Section 7 built
`_primary_reign_end_source()` to pick the right numbered Reign field for *end*
dates (a monarch's numbered ReignN field can be a different, lesser realm, not a
later stint of the same one). The exact same ambiguity exists for *start* dates and
`dates.py` has no equivalent mechanism -- it just takes whichever
`REIGN_START_FIELDS` entry parses first, with no concept of "which realm is this
deck actually about." Found by inspection, not by a crash:
- **Swein Forkbeard**: unnumbered `Succession`/`Reign` = King of *Denmark* (from
  c. 986); `Succession2`/`Reign2` = King of *England* (from December 1013, his
  actual, brief English conquest). The unnumbered field silently won by priority,
  dating a "Kings of England" document to 986.
- **Harthacnut**: same shape -- unnumbered = King of Denmark (1035), numbered
  Succession1/Reign1 = King of England (1040).
- **Edmund Ironside vs. Cnut**: not a multi-realm issue but the same class of
  "silently plausible but wrong" outcome -- Edmund's reign is written as
  `"23 April-30 November 1016"` (year stated once, for the whole range, not
  attached to the start day/month), which no current pattern parses, so it fell all
  the way to the year-only fallback. Cnut's own reign field is *only* year
  precision (`"1016-1035"`). Both landed on the same year-only date, 1 January
  1016, which put them in the WRONG RELATIVE ORDER once alphabetically
  tie-broken (Cnut before Edmund Ironside, backwards from history -- Edmund reigned
  April-November 1016, then Cnut became sole king).

None of these are `dates.py` bugs in the sense of a wrong regex; they're a missing
"prefer the realm this project is actually about" mechanism that section 7 built
for end dates but never generalized to start dates. Given only 3 monarchs out of the
whole 58-person dataset (so far) need it, fixed each with an explicit `--start-date`
override at fetch time rather than building that generalization now: Swein ->
`1013-12-01` (month precision from his English Reign2 field), Harthacnut ->
`1040-01-01` (year precision only, no more specific date statement found), Edmund
Ironside -> `1016-04-23` (his reign's own stated start), Cnut -> `1016-11-30` (the
day Edmund Ironside's reign explicitly ends, i.e. when Cnut became sole king). If a
*third* line of succession surfaces the same pattern, that's the signal to build the
general fix rather than a fourth override.

**Colors: an initial choice had to be abandoned mid-derivation.** Tried Wessex=
orange first (following the established palette order). Turned out orange has bad
CVD separation against several colors under protanopia specifically (green ΔE 2.7,
a hard fail) and fails the normal-vision floor against several more (yellow ΔE
10.6, magenta ΔE 11.6, red ΔE 7.1) -- of the 8 hues, almost nothing pairs safely
with orange on both sides. Since Wessex needs a safe neighbor on *both* sides
(Knytlinga, and Godwin), and Godwin *also* has to clear Normandy's blue, there was
no single choice that satisfied every constraint with orange in the mix. Restarted
from Godwin's constraint outward instead of Wessex's: blue's known-good partners
are {orange, red, green, yellow} (from prior validator runs); picked Godwin=red
(clears blue at dE 29.0); then picked Wessex from red's good partners
({blue, green, violet, aqua}), landing on green (clears red at dE 32.6, and
critically doesn't reuse blue, which would sit one house away from Normandy's own
blue in the same combined timeline); then Knytlinga from green's good partners,
landing on magenta (clears green at dE 34.5 -- aqua was the other candidate but
fails the normal-vision floor against green at dE 11.9, both being cool/green-ish).
All three pairs -- Wessex<->Knytlinga, Wessex<->Godwin, Godwin<->Normandy -- pass.

**HOUSES_ANGLO-SAXON.md was hand-assembled, not run through `build_houses_document()`.**
That function assumes one document = one chronological entry and merges same-named
house headings together; the user's draft deliberately keeps three separate
"Wessex" headings (interrupted first by Swein Forkbeard's "(No House)" reign, then
by the Knytlinga/Danish kings) to show the narrative structure, and needs one
document (AEthelred's) linked twice under two different dates. Preserved that
structure by hand rather than forcing it through the automated grouper, computing
each entry's date range with the same `houses_writer.py` logic (`_read_entry`) used
for the main file, for consistency.

**The double-reign listing needed two small, genuinely new mechanisms in
`build_keynote_deck.py`'s `parse_houses_document()`:**
1. *Sort ambiguity*: both AEthelred entries link to the same file, so the existing
   "sort by the linked filename's date" logic gives them the same sort key. Added an
   optional `<!-- sort:YYYY-MM-DD -->` HTML comment on a bullet line that overrides
   the filename-derived date for that one entry -- invisible in a rendered view of
   the Markdown, present only for the parser.
2. *Missing Reign field*: AEthelred's infobox has no plain `Reign` field at all
   (only numbered `Reign1`/`Reign2`), so his slide's body text was silently missing
   the Reign line entirely -- and even fixing that generically by falling back to
   `Reign1` would show the *same* text ("978-1013") on *both* of his slides, wrong
   for the second one. Fixed by extending the bullet-line regex to also capture each
   entry's own `(date range)` text and threading it through as a fallback the slide
   builder only uses when the document's own `Reign` field is absent -- preserves
   full-precision text everywhere else (all 41 other UK monarchs, 15 of these 16
   Anglo-Saxon ones) and correctly differentiates AEthelred's two listings even
   though they pull from one shared document.

**"(No House)" needed to not render as a slide label.** Swein Forkbeard's heading
is a deliberate placeholder for "not really an established dynasty," not a color
slot -- `build_deck_script` treats any `"(...)"` -parenthesized heading the same as
no house at all (no colored label, matching `build_slide_script`'s existing
`if house:` guard for an empty string).

Verified end to end: `parse_houses_document()` round-trips all 17 listed entries
(16 sovereigns, AEthelred twice) into the correct chronological order; the deck
built cleanly (18 slides including the title slide) with WESSEX/green,
"(No House)"/no label, and GODWIN/red all rendering as expected in exported checks;
saved as `output/kings_of_the_united_kingdom/Anglo-Saxon_Kings.key`, kept separate
from `UK_Monarchs.key` rather than merged into one deck. Rebuilt and re-verified
`UK_Monarchs.key` too, since the Reign-fallback change touched shared code -- no
regression, all 42 main entries still show their full-precision Reign text.

## Current state

- Tests: 60/60 passing (`python -m pytest -q`), all pure-logic, no network calls.
- `output/kings_of_the_united_kingdom/`: 42 monarchs, William the Conqueror (1066) ->
  Charles III (2022) -- `documents/`, `images/`, `INDEX.md`, `HOUSES.md` (the
  normative sovereign/house/color list -- see section 8), `UK_Monarchs.key`
  (color-coded by House, House shown at the top of each slide, built by reading
  HOUSES.md rather than the documents directory directly).
- The same directory also holds 16 Anglo-Saxon-era documents/images, Alfred the
  Great (871) -> Harold Godwinson (1066) -- `documents/`, `images/`,
  `HOUSES_ANGLO-SAXON.md` (hand-assembled, normative for this line -- see section
  9), `Anglo-Saxon_Kings.key` (a separate deck from `UK_Monarchs.key`, not merged
  into it). AEthelred the Unready's single document is linked twice in the houses
  file (his two reigns) and appears as two slides in the deck.
- `output/kings_of_scotland/`: 11 monarchs, John Balliol -> Mary, Queen of Scots --
  the England/Scotland fork byproduct (section 3), `documents/` + `images/` only.
- `output/kings_of_united_kingdom/` and `output/presidents_of_the_united_states/`:
  still-empty placeholders that predate this project's slug convention.

## Not done yet

- `kings_of_scotland` doesn't extend further back (e.g. to Kenneth MacAlpin) and has
  no `INDEX.md`, `HOUSES.md`, or Keynote deck of its own -- and its documents predate
  the section-7 *and* section-9 date-accuracy fixes (multi-Reign-field end/start
  dates, month-year dates, 3-digit years, `{{circa}}`/`{{dash}}` templates), so it
  hasn't been checked for any of these bug classes.
- `presidents_of_the_united_states` is unstarted -- would need its own categorical
  mapping (political party, presumably) validated the same way, not reuse of
  `HOUSE_COLORS`.
- The Keynote deck's body fields (Birth Date / Death Date, plus Reign when
  available) are a fixed list in `build_keynote_deck.py`, not configurable per run.
- `_REIGN_END_OVERRIDES` in `houses_writer.py` is a by-hand table verified against
  the current 58 UK+Anglo-Saxon monarchs; extending this project to another line of
  succession with its own multi-title monarchs would need the same manual check,
  not an assumption that the structural rule (no-SuccessionN-means-continuation) is
  enough on its own -- Anne already proves it isn't.
- `dates.py` has no "prefer this realm" mechanism for *start* dates the way
  `houses_writer.py` has one for end dates (`_primary_reign_end_source`) -- three
  Anglo-Saxon monarchs needed a manual `--start-date` override instead (section 9).
  Fine at this scale; worth generalizing if a fourth case turns up.
