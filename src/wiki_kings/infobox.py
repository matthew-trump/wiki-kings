"""Extract an Infobox template out of article wikitext as an ordered, human-readable dict.

Wikipedia infoboxes are MediaWiki templates whose parameter values are themselves
full wikitext: links, citations, footnotes, and formatting templates (dates, name
lists, nowrap, etc). This module pulls out the raw {name: value} pairs -- including
values nested inside a `module = {{Infobox ...}}` sub-infobox, a common pattern for
royalty/officeholder infoboxes -- and renders each value down to plain text.
"""

from __future__ import annotations

import html
import re
from collections import OrderedDict
from typing import Callable

import wikitextparser as wtp

# Parameters that are infobox plumbing rather than displayable data.
_SKIP_PARAMS = {"module", "embed", "child", "subheader", "italic title"}

# Templates that carry no display value (citations, footnotes, editorial asides).
_DROP_TEMPLATES = {
    "efn", "efn-ua", "refn", "sfn", "r", "rp",
    "cite", "cite web", "cite news", "cite book", "cite journal",
    "citation", "cn", "citation needed", "clarify", "better source",
    "circa",
}

_DASH_TEMPLATES = {"sndash", "spaced ndash", "snd", "ndash", "endash"}
_UNWRAP_TEMPLATES = {"nowrap", "small", "smaller", "nobold", "resize", "midsize"}
_LIST_TEMPLATES = {
    "br separated entries", "ubl", "unbulleted list", "plainlist",
    "hlist", "flatlist", "collapsible list",
}


def find_first_infobox(wikitext: str) -> str | None:
    """Return the raw wikitext of the first top-level {{Infobox ...}} template, or None."""
    match = re.search(r"\{\{\s*Infobox", wikitext, re.IGNORECASE)
    if not match:
        return None
    start = match.start()
    depth = 0
    for i in range(start, len(wikitext)):
        ch = wikitext[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return wikitext[start:i + 1]
    return None


def parse_infobox(wikitext: str) -> "OrderedDict[str, str]":
    """Parse the first infobox in `wikitext` into an ordered {parameter: clean text} dict."""
    return _flatten_template(_get_infobox_template(wikitext), clean_value)


def parse_infobox_raw(wikitext: str) -> "OrderedDict[str, str]":
    """Like `parse_infobox`, but values are left as raw wikitext (still containing
    [[links]], templates, etc). Used to chase a field's link target -- e.g. Predecessor
    -- before it gets flattened down to display text."""
    return _flatten_template(_get_infobox_template(wikitext), lambda v: v)


def _get_infobox_template(wikitext: str) -> wtp.Template:
    raw = find_first_infobox(wikitext)
    if raw is None:
        raise ValueError("No {{Infobox ...}} template found in wikitext")
    return wtp.parse(raw).templates[0]


def _flatten_template(
    template: wtp.Template, transform: Callable[[str], str]
) -> "OrderedDict[str, str]":
    fields: "OrderedDict[str, str]" = OrderedDict()
    for arg in template.arguments:
        name = arg.name.strip()
        if name == "module":
            # Sub-infobox (royalty infoboxes nest Infobox person/officeholder/etc via
            # `module = {{Infobox ... | embed = yes | ...}}`); descend and merge its fields.
            nested = wtp.parse(arg.value).templates
            if nested:
                fields.update(_flatten_template(nested[0], transform))
            continue
        if not name or name in _SKIP_PARAMS or name.isdigit():
            continue
        value = transform(arg.value)
        if value and value.strip():
            fields[name] = value
    return fields


def first_wikilink_target(raw_value: str) -> str | None:
    """Pull the article title out of the first [[wikilink]] in a raw (uncleaned)
    infobox value, e.g. '[[George&nbsp;VI]]' -> 'George VI'. Returns None if there's
    no link (a plain-text or empty Predecessor field, typically the start of a line)."""
    links = wtp.parse(raw_value).wikilinks
    if not links:
        return None
    # html.unescape('&nbsp;') yields U+00A0, not an ASCII space -- normalize it so
    # downstream page titles and regnal-name filenames don't end up with an invisible
    # non-breaking space where a plain " " (and later "_") is expected.
    target = re.sub(r"\s+", " ", html.unescape(links[0].target)).strip()
    return target or None


_PREDECESSOR_FIELD = re.compile(r"^predecessor\d*$")


def find_predecessor_target(
    raw_fields: "OrderedDict[str, str]", prefer_realm: str | None = "england"
) -> str | None:
    """Find the link target of a Predecessor field for chain-walking purposes.

    Monarchs with more than one title/succession box number their fields
    (predecessor1, predecessor2, ...) instead of -- or as well as -- a plain
    'predecessor'. Usually that's just multiple honorifics for the same throne
    (e.g. George V, also Emperor of India) and any of them lead to the same next
    monarch. But at a personal union's *start* it can be a genuine fork: James VI
    and I has an unnumbered Scotland box (predecessor -> Mary, Queen of Scots) and
    a numbered England box (predecessor1 -> Elizabeth I) that lead to two entirely
    different lines of succession. When more than one candidate exists, prefer
    whichever one's sibling succession/successionN field mentions `prefer_realm`
    (case-insensitive); otherwise prefer the unnumbered field, then the lowest
    numbered one, same as before.
    """
    candidates = sorted(
        (key for key in raw_fields if _PREDECESSOR_FIELD.match(key)),
        key=lambda k: (k != "predecessor", k),
    )
    if prefer_realm and len(candidates) > 1:
        realm_matches = [
            key for key in candidates
            if prefer_realm.lower() in raw_fields.get(_succession_key(key), "").lower()
        ]
        if realm_matches:
            candidates = realm_matches + [k for k in candidates if k not in realm_matches]
    for key in candidates:
        target = first_wikilink_target(raw_fields[key])
        if target:
            return target
    return None


def _succession_key(predecessor_key: str) -> str:
    return "succession" + predecessor_key[len("predecessor"):]


def clean_value(text: str) -> str:
    """Render a raw wikitext fragment (an infobox parameter value) down to plain text."""
    parsed = wtp.parse(text)

    for comment in reversed(parsed.comments):
        comment.string = ""

    for tag in reversed(parsed.get_tags()):
        if tag.name == "ref":
            tag.string = ""
        elif tag.name == "br":
            tag.string = "; "
        else:
            tag.string = tag.contents or ""

    _resolve_templates(parsed)

    for link in reversed(parsed.wikilinks):
        link.string = link.text if link.text else link.target

    s = html.unescape(str(parsed))
    s = re.sub(r"'''''(.*?)'''''", r"\1", s)
    s = re.sub(r"'''(.*?)'''", r"\1", s)
    s = re.sub(r"''(.*?)''", r"\1", s)
    s = re.sub(r"\s*;\s*(;\s*)+", "; ", s)
    s = re.sub(r"\s+", " ", s).strip(" ;\n\t")
    return s


def _resolve_templates(parsed: wtp.WikiText) -> None:
    """Replace each top-level template in `parsed` with its rendered text.

    Only top-level templates are touched: `_render_template` already resolves
    nested templates recursively (via `clean_value` on each argument, which
    parses a fresh, independent tree). Re-querying `parsed.templates` after
    mutating a span is unsafe -- wikitextparser leaves the mutated span tagged
    as a template, so a plain-text replacement like an en dash gets picked
    back up as a "template" on the next scan and wiped out.
    """
    top_level = [
        t for t in parsed.templates
        if not any(isinstance(a, wtp.Template) for a in t.ancestors())
    ]
    for template in reversed(top_level):
        template.string = _render_template(template)


def _render_template(template: wtp.Template) -> str:
    name = template.normal_name(capitalize=False).strip().lower()
    positional = [clean_value(a.value) for a in template.arguments if a.positional]
    named = {
        a.name.strip().lower(): clean_value(a.value)
        for a in template.arguments if not a.positional
    }

    if name in _DROP_TEMPLATES or name.startswith("efn"):
        return ""
    if name in _DASH_TEMPLATES:
        return "–"
    if name in _UNWRAP_TEMPLATES:
        return positional[0] if positional else ""
    if name in _LIST_TEMPLATES:
        if len(positional) > 1:
            items = positional
        elif positional:
            # A single positional arg holding raw "*"-bulleted lines (the common
            # {{plainlist|\n* a\n* b}} form) -- whitespace is already collapsed
            # by this point, so split on the surviving "*" markers instead.
            items = [item.strip() for item in positional[0].split("*")]
        else:
            items = list(named.values())
        return "; ".join(item for item in items if item)
    if name in {"marriage"}:
        return _render_marriage(positional, named)
    if name in {"birth date and age", "birth-date and age", "birth date", "birth date and age2"}:
        return _render_date(positional) or " ".join(positional)
    if name in {"death date and age", "death-date and age", "death date"}:
        # First three positional args are the death date; a "death date and age" with
        # six args leads with the death date and follows with the birth date.
        return _render_date(positional[:3]) or " ".join(positional)
    if name in {"start and end dates", "start and end dates and age", "start-and-end-dates"}:
        # {{Start and end dates|Y1|M1|D1|Y2|M2|D2}} -- reigns short enough to fit in
        # one calendar year (e.g. Edward VIII, 1936) commonly use this instead of a
        # plain "reign" prose string with a dash template in it.
        start = _render_date(positional[:3])
        end = _render_date(positional[3:6])
        if start and end:
            return f"{start}–{end}"
        return start or " ".join(positional)

    # Unknown template: best-effort fall back to its first positional argument, since
    # name/link-formatting templates (e.g. {{HMS|Bronington|M1115}}) conventionally
    # put the primary display text there.
    return positional[0] if positional else ""


def _render_marriage(positional: list[str], named: dict[str, str]) -> str:
    who = positional[0] if positional else ""
    start = positional[1] if len(positional) > 1 else ""
    end = positional[2] if len(positional) > 2 else ""
    reason = named.get("reason", "")
    date_range = ""
    if start and end:
        date_range = f"{start}–{end}"
    elif start:
        date_range = f"{start}–present"
    extra = f", {reason}" if reason else ""
    if date_range:
        return f"{who} ({date_range}{extra})"
    return who


def _render_date(parts: list[str]) -> str | None:
    if len(parts) < 3:
        return None
    year, month, day = parts[0], parts[1], parts[2]
    try:
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    except ValueError:
        return None
