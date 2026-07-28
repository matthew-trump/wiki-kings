"""Normalizing the free-text infobox 'House' field into one label per dynasty, and
assigning each dynasty a fixed, validated categorical color.

Shared by houses_writer.py (HOUSES.md, the normative list of houses/sovereigns/
colors -- see its module docstring) and scripts/build_keynote_deck.py (which reads
HOUSES.md rather than re-deriving any of this independently).
"""

from __future__ import annotations

_HOUSE_ALIASES = {
    "Plantagenet-Angevin": "Plantagenet",
    "Plantagenet–Angevin": "Plantagenet",  # en-dash variant
}


def normalize_house(raw: str) -> str:
    """Collapse Wikipedia's inconsistent House field into one name per dynasty.

    Two real cases in the UK data: (1) the same continuous House of Plantagenet is
    labeled "Plantagenet" for later monarchs and "Plantagenet-Angevin" (or an
    en-dash variant) for earlier ones -- no actual dynasty change, so it should be
    one label, not two. (2) Monarchs whose reign straddled the 1917 rename from
    Saxe-Coburg and Gotha to Windsor (WWI anti-German sentiment) have a compound
    field describing both eras (e.g. "Saxe-Coburg and Gotha (by birth); Windsor
    (founder)") -- shown under the name the dynasty is actually known by today.
    """
    raw = raw.strip()
    if raw in _HOUSE_ALIASES:
        return _HOUSE_ALIASES[raw]
    lower = raw.lower()
    if "windsor" in lower and "saxe-coburg" in lower:
        return "Windsor"
    return raw


# Dark-mode categorical hues, in fixed order, from the dataviz skill's reference
# palette (references/palette.md) -- not hand-picked; the ordering is itself
# validated (via that skill's scripts/validate_palette.js) to clear the CVD/normal-
# vision separation floor between every *adjacent* slot.
_SLOT_BLUE = "#3987e5"
_SLOT_ORANGE = "#d95926"
_SLOT_AQUA = "#199e70"
_SLOT_YELLOW = "#c98500"
_SLOT_MAGENTA = "#d55181"
_SLOT_GREEN = "#008300"
_SLOT_VIOLET = "#9085e9"
_SLOT_RED = "#e66767"
CATEGORICAL_PALETTE_DARK = [
    _SLOT_BLUE, _SLOT_ORANGE, _SLOT_AQUA, _SLOT_YELLOW,
    _SLOT_MAGENTA, _SLOT_GREEN, _SLOT_VIOLET, _SLOT_RED,
]

# House -> color for the UK line. The 42 monarchs pass through 12 distinct houses
# (after normalize_house() collapses near-duplicate labels), more than the
# palette's 8 fixed hues, so 4 houses reuse an earlier slot. Each reuse was picked,
# not blindly cycled: every *actual* chronological transition in the sequence
# (Blois->Plantagenet, ..., Stuart->Orange-Nassau->Stuart->Hanover->Saxe-Coburg and
# Gotha->Windsor) was checked with
#   node <dataviz skill>/scripts/validate_palette.js "<hexA,hexB>" --mode dark --surface "#000000"
# and only assignments that cleared the validator's normal-vision floor (>=15
# OKLab dE) against BOTH real neighbors were kept -- e.g. Hanover reuses Grey's
# violet rather than the "next" slot (orange) because Stuart->orange fails that
# floor at dE 7.1, while Stuart->violet passes at dE 22.5. Full derivation in
# PROGRESS.md. If you extend this table for a new house, re-run the validator
# against its real neighbors rather than picking the next unused slot.
HOUSE_COLORS = {
    "Normandy": _SLOT_BLUE,
    "Blois": _SLOT_ORANGE,
    "Plantagenet": _SLOT_AQUA,
    "Lancaster": _SLOT_YELLOW,
    "York": _SLOT_MAGENTA,
    "Tudor": _SLOT_GREEN,
    "Grey": _SLOT_VIOLET,
    "Stuart": _SLOT_RED,
    "Orange-Nassau": _SLOT_BLUE,
    "Hanover": _SLOT_VIOLET,
    "Saxe-Coburg and Gotha": _SLOT_AQUA,
    "Windsor": _SLOT_YELLOW,
}


def assign_house_colors(house_sequence: list[str]) -> dict[str, str]:
    """Map each distinct house (in first-appearance order) to a hex color.

    Houses in HOUSE_COLORS use their validated assignment. Anything else (a
    different slug/dataset) falls back to cycling the same 8 hues in fixed order --
    NOT re-validated for adjacency. Re-run the dataviz skill's validator per the
    method documented above/in PROGRESS.md before trusting that fallback for a
    dataset with more than a handful of distinct categories.
    """
    assigned: dict[str, str] = {}
    next_slot = 0
    for house in house_sequence:
        if not house or house in assigned:
            continue
        if house in HOUSE_COLORS:
            assigned[house] = HOUSE_COLORS[house]
        else:
            assigned[house] = CATEGORICAL_PALETTE_DARK[next_slot % 8]
            next_slot += 1
    return assigned
