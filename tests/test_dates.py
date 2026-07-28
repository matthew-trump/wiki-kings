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
