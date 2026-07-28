"""Best-effort parsing of the human-written dates found in infobox prose."""

from __future__ import annotations

import re
from datetime import date

_MONTHS = {
    name.lower(): i
    for i, name in enumerate(
        [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ],
        start=1,
    )
}

_ISO_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
# The optional "/22" handles Old Style/New Style dual dates used for reigns that
# started before Great Britain's 1752 Julian-to-Gregorian switch, e.g. George II's
# "11/22 June 1727" -- the Old Style (Julian) day is used, ignoring the New Style one.
_DAY_MONTH_YEAR = re.compile(r"(\d{1,2})(?:/\d{1,2})?\s+([A-Za-z]+)\s+(\d{4})")
_MONTH_DAY_YEAR = re.compile(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})")


def parse_wiki_date(text: str) -> date | None:
    """Parse a leading '8 September 2022', 'September 8, 2022', or '2022-09-08'.

    The ISO form shows up because infobox.py itself renders templates like
    {{start and end dates}} down to ISO dates -- this needs to round-trip back.
    """
    text = text.strip()
    iso_match = _ISO_DATE.match(text)
    if iso_match:
        try:
            return date(*(int(part) for part in iso_match.groups()))
        except ValueError:
            pass
    for pattern, order in ((_DAY_MONTH_YEAR, "dmy"), (_MONTH_DAY_YEAR, "mdy")):
        match = pattern.match(text)
        if not match:
            continue
        groups = match.groups()
        day, month_name, year = groups if order == "dmy" else (groups[1], groups[0], groups[2])
        month = _MONTHS.get(month_name.lower())
        if month is None:
            continue
        try:
            return date(int(year), month, int(day))
        except ValueError:
            continue
    return None


# Infobox fields commonly used to mark when someone took office, roughly in order
# of how likely they are to appear and to represent the *start* of a reign/term.
# 'coronation' is a fallback proxy for medieval reigns whose 'reign' field is only
# recorded to year precision (see below) but whose coronation date is exact.
REIGN_START_FIELDS = ("reign", "term_start", "reign1", "coronation", "coronation1")

_LEADING_YEAR = re.compile(r"\d{4}")


def find_start_date(fields: dict[str, str]) -> date | None:
    for name in REIGN_START_FIELDS:
        value = fields.get(name)
        if not value:
            continue
        parsed = parse_wiki_date(value)
        if parsed:
            return parsed

    # Some medieval reigns are recorded to year precision only, e.g. Henry III's
    # `reign = 1216 - 1272` (no month/day anywhere in the infobox). Falling back to
    # 1 January of that year is an approximation, but keeps a predecessor chain
    # running this far back rather than failing outright.
    for name in REIGN_START_FIELDS:
        value = fields.get(name)
        if not value:
            continue
        match = _LEADING_YEAR.search(value)
        if match:
            return date(int(match.group()), 1, 1)
    return None
