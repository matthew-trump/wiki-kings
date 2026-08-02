from collections import OrderedDict

from wiki_kings.infobox import (
    clean_value,
    find_predecessor_target,
    first_wikilink_target,
    parse_infobox,
    parse_infobox_raw,
)


def test_clean_value_strips_refs_comments_and_footnotes():
    text = "Protestant<!--do not change-->{{efn|see discussion}}<ref>cite</ref>"
    assert clean_value(text) == "Protestant"


def test_clean_value_resolves_wikilinks():
    assert clean_value("[[King of the United Kingdom]]") == "King of the United Kingdom"
    assert clean_value("[[Elizabeth II|the Queen]]") == "the Queen"


def test_clean_value_renders_circa_instead_of_dropping_it():
    # {{circa|886}} previously sat in _DROP_TEMPLATES alongside citation/footnote
    # templates and vanished entirely -- silently deleting Alfred the Great's reign
    # end date ("23 April 871 -- {{circa|886}}" rendered as "23 April 871 --", the
    # approximate end year just gone). "c. 886" matches Wikipedia's own rendering.
    assert clean_value("23 April 871 – {{circa|886}}") == "23 April 871 – c. 886"


def test_clean_value_renders_dash_template():
    # {{dash}} (a generic "–") is a different template from {{sndash}}/{{ndash}}
    # and wasn't in _DASH_TEMPLATES -- Edmund I's "27 October 939{{dash}} 26 May
    # 946" rendered as "27 October 939 26 May 946", the separator just gone.
    assert clean_value("27 October 939{{dash}} 26 May 946") == "27 October 939– 26 May 946"


def test_clean_value_strips_bold_and_italics():
    assert clean_value("'''Charles III'''") == "Charles III"
    assert clean_value("''Regina''") == "Regina"


def test_clean_value_renders_sndash_without_eating_neighbouring_text():
    assert clean_value("8 September 2022{{sndash}}present") == "8 September 2022–present"


def test_clean_value_renders_nowrap():
    assert clean_value("{{nowrap|[[Heir apparent]]}}") == "Heir apparent"


def test_clean_value_renders_birth_date_and_age():
    assert clean_value("{{birth date and age|1948|11|14|df=yes}}") == "1948-11-14"


def test_clean_value_renders_marriage():
    text = "{{marriage|[[Diana Spencer]]|29 July 1981|28 August 1996|reason=divorced}}"
    assert clean_value(text) == "Diana Spencer (29 July 1981–28 August 1996, divorced)"


def test_clean_value_splits_plainlist_bullets():
    text = "{{plainlist|\n* [[Royal Navy]]\n* [[Royal Air Force]]}}"
    assert clean_value(text) == "Royal Navy; Royal Air Force"


def test_parse_infobox_flattens_nested_modules():
    wikitext = """
Intro text before the infobox.

{{Infobox royalty
| title = King
| reign = 8 September 2022{{sndash}}present
| module = {{Infobox person
| embed = yes
| education = [[Trinity College, Cambridge]]
| module = {{Infobox officeholder
| embed = yes
| office = Member of the [[House of Lords]]
}}
}}
}}

Article body after the infobox.
"""
    fields = parse_infobox(wikitext)
    assert fields["title"] == "King"
    assert fields["reign"] == "8 September 2022–present"
    assert fields["education"] == "Trinity College, Cambridge"
    assert fields["office"] == "Member of the House of Lords"
    assert "module" not in fields
    assert "embed" not in fields


def test_parse_infobox_raises_when_absent():
    import pytest

    with pytest.raises(ValueError):
        parse_infobox("no infobox here")


def test_first_wikilink_target_normalizes_nbsp_to_plain_space():
    # html.unescape('&nbsp;') yields U+00A0, not ASCII " " -- must be normalized so it
    # doesn't survive into page titles / regnal-name filenames as an invisible NBSP.
    assert first_wikilink_target(" [[George&nbsp;VI]]\n") == "George VI"


def test_first_wikilink_target_none_when_no_link():
    assert first_wikilink_target("none") is None


def test_parse_infobox_raw_preserves_link_markup():
    wikitext = "{{Infobox royalty\n| predecessor = [[George&nbsp;VI]]\n}}"
    raw = parse_infobox_raw(wikitext)
    assert "[[George" in raw["predecessor"]
    assert first_wikilink_target(raw["predecessor"]) == "George VI"


def test_find_predecessor_target_prefers_plain_field():
    fields = OrderedDict([("predecessor", "[[Elizabeth II]]"), ("predecessor1", "[[Someone Else]]")])
    assert find_predecessor_target(fields) == "Elizabeth II"


def test_find_predecessor_target_prefers_realm_at_a_personal_union_fork():
    # James VI and I: unnumbered box is Scotland (predecessor -> Mary, Queen of
    # Scots), numbered box is England (predecessor1 -> Elizabeth I). Naively
    # preferring the unnumbered field walks into Scottish history and never
    # reaches an English king like William the Conqueror.
    fields = OrderedDict([
        ("succession1", "[[King of England]] and [[Monarchy of Ireland|Ireland]]"),
        ("predecessor1", "[[Elizabeth I]]"),
        ("succession", "[[King of Scotland]]"),
        ("predecessor", "[[Mary, Queen of Scots|Mary]]"),
    ])
    assert find_predecessor_target(fields) == "Elizabeth I"
    assert find_predecessor_target(fields, prefer_realm=None) == "Mary, Queen of Scots"


def test_find_predecessor_target_falls_back_to_numbered_field():
    # George V's infobox has two succession boxes (UK, Emperor of India) and only
    # numbered predecessor1/successor1 fields -- no plain "predecessor" at all.
    fields = OrderedDict([("successor1", "[[Edward VIII]]"), ("predecessor1", "[[Edward VII]]")])
    assert find_predecessor_target(fields) == "Edward VII"


def test_find_predecessor_target_none_when_no_link_anywhere():
    fields = OrderedDict([("predecessor", "none")])
    assert find_predecessor_target(fields) is None
