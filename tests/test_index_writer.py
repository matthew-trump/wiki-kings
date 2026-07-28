from pathlib import Path

from wiki_kings.index_writer import build_index


def _write_doc(output_root: Path, slug: str, filename: str, heading: str) -> None:
    documents_dir = output_root / slug / "documents"
    documents_dir.mkdir(parents=True, exist_ok=True)
    (documents_dir / filename).write_text(f"# {heading}\n\nsome content\n", encoding="utf-8")


def test_build_index_orders_chronologically_and_links_documents(tmp_path):
    slug = "kings_of_the_united_kingdom"
    _write_doc(tmp_path, slug, "2022-09-08-CHARLES_III-INFOBOX.md", "Charles III")
    _write_doc(tmp_path, slug, "1066-12-25-WILLIAM_THE_CONQUEROR-INFOBOX.md", "William the Conqueror")
    _write_doc(tmp_path, slug, "1952-02-06-ELIZABETH_II-INFOBOX.md", "Elizabeth II")

    index_path = build_index(tmp_path, slug, "Kings and Queens of the United Kingdom")

    assert index_path == tmp_path / slug / "INDEX.md"
    content = index_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    assert lines[0] == "# Kings and Queens of the United Kingdom"
    body = [line for line in lines if line and not line.startswith("#")]
    assert body == [
        "1. [William the Conqueror](documents/1066-12-25-WILLIAM_THE_CONQUEROR-INFOBOX.md)"
        " — reign began 1066-12-25",
        "2. [Elizabeth II](documents/1952-02-06-ELIZABETH_II-INFOBOX.md) — reign began 1952-02-06",
        "3. [Charles III](documents/2022-09-08-CHARLES_III-INFOBOX.md) — reign began 2022-09-08",
    ]


def test_build_index_empty_documents_dir(tmp_path):
    slug = "empty_slug"
    (tmp_path / slug / "documents").mkdir(parents=True)
    index_path = build_index(tmp_path, slug, "Empty")
    assert index_path.read_text(encoding="utf-8").strip() == "# Empty"
