from collections import OrderedDict

from wiki_kings.markdown_writer import humanize_field, render_markdown


def test_humanize_field():
    assert humanize_field("birth_date") == "Birth Date"


def test_render_markdown_includes_image_link_and_fields():
    fields = OrderedDict([("title", "King"), ("birth_date", "1948-11-14")])
    content = render_markdown(regnal_name="Charles III", fields=fields, image_relpath="../images/foo.jpg")
    assert content.startswith("# Charles III\n")
    assert "![Charles III](../images/foo.jpg)" in content
    assert "- **Title**: King" in content
    assert "- **Birth Date**: 1948-11-14" in content


def test_render_markdown_without_image():
    content = render_markdown(regnal_name="Charles III", fields={}, image_relpath=None)
    assert "![" not in content
