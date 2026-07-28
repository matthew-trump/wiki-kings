from pathlib import Path

from wiki_kings.naming import document_path, image_path_stem, regnal_slug


def test_regnal_slug():
    assert regnal_slug("Charles III") == "CHARLES_III"


def test_document_path_matches_project_spec_example():
    path = document_path(Path("output"), "kings_of_the_united_kingdom", "2022-09-08", "Charles III")
    assert path == Path("output/kings_of_the_united_kingdom/documents/2022-09-08-CHARLES_III-INFOBOX.md")


def test_image_path_stem_matches_project_spec_example():
    stem = image_path_stem(Path("output"), "kings_of_the_united_kingdom", "2022-09-08", "Charles III")
    assert stem == Path("output/kings_of_the_united_kingdom/images/2022-09-08-CHARLES_III")
