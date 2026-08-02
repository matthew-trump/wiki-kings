from datetime import date

from wiki_kings.dates import find_start_date, parse_wiki_date


def test_parse_wiki_date_day_month_year():
    assert parse_wiki_date("8 September 2022") == date(2022, 9, 8)


def test_parse_wiki_date_month_day_year():
    assert parse_wiki_date("September 8, 2022") == date(2022, 9, 8)


def test_parse_wiki_date_returns_none_for_garbage():
    assert parse_wiki_date("present") is None


def test_parse_wiki_date_iso():
    assert parse_wiki_date("1936-01-20") == date(1936, 1, 20)


def test_parse_wiki_date_old_style_new_style_dual_date():
    # Pre-1752 reigns (before Britain's Julian -> Gregorian switch) are often
    # written as "Old/New Style day, Month Year", e.g. George II's "11/22 June 1727".
    assert parse_wiki_date("11/22 June 1727") == date(1727, 6, 11)


def test_find_start_date_prefers_reign_field():
    fields = {"reign": "8 September 2022–present", "term_start": "1 January 2000"}
    assert find_start_date(fields) == date(2022, 9, 8)


def test_find_start_date_falls_back_to_term_start():
    fields = {"term_start": "20 January 2021"}
    assert find_start_date(fields) == date(2021, 1, 20)


def test_find_start_date_none_when_unparseable():
    assert find_start_date({"reign": "unknown"}) is None


def test_find_start_date_prefers_coronation_over_year_only_reign():
    fields = {"reign": "1216 – 1272", "coronation": "28 October 1216"}
    assert find_start_date(fields) == date(1216, 10, 28)


def test_find_start_date_falls_back_to_year_only():
    fields = {"reign": "1216 – 1272"}
    assert find_start_date(fields) == date(1216, 1, 1)


def test_parse_wiki_date_month_year_no_day():
    # Mary I: "sources differ on whether her regnal years were dated from 24 July
    # or 6 July" -- the infobox itself only commits to the month.
    assert parse_wiki_date("July 1553") == date(1553, 7, 1)


def test_find_start_date_month_year_reign_beats_full_precision_wrong_field():
    # Mary I's actual bug: 'reign' (the right title, Queen of England) only has
    # month precision; 'reign1' (Queen consort of Spain -- a different, lesser
    # title) has full day precision. The correct field must win even though it's
    # less precise, since it's checked first and now parses on its own.
    fields = {
        "reign": "July 1553 – 17 November 1558",
        "reign1": "16 January 1556 – 17 November 1558",
    }
    assert find_start_date(fields) == date(1553, 7, 1)


def test_find_start_date_year_only_reign_still_prefers_coronation():
    # Regression guard: month-year support must not steal priority from the
    # existing coronation fallback for reigns with only YEAR precision (no month
    # at all) -- "1216" has no leading month name, so month-year parsing correctly
    # doesn't match it, and the day-precise coronation field wins as before.
    fields = {"reign": "1216 – 1272", "reign1": "1 January 1200 – 1 January 1210", "coronation": "28 October 1216"}
    assert find_start_date(fields) == date(1216, 10, 28)


def test_parse_wiki_date_three_digit_year():
    # Alfred the Great's reign started in 871 CE -- a plain 3-digit year in
    # wikitext (Python's date.isoformat() zero-pads it to "0871" in our own
    # filenames, but the source infobox text itself doesn't).
    assert parse_wiki_date("23 April 871") == date(871, 4, 23)


def test_find_start_date_three_digit_year_only_fallback():
    assert find_start_date({"reign": "871 – 899"}) == date(871, 1, 1)
