"""Download and save an infobox's profile thumbnail, keeping its native format."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from . import wikipedia_client as wc


def save_thumbnail(file_name: str, dest_stem: Path, *, thumb_width: int = 400) -> Path:
    """Download the thumbnail for `file_name` and save it next to `dest_stem`.

    `dest_stem` has no extension; the real one (matching whatever format
    Wikipedia serves) is appended based on the resolved URL.
    """
    url = wc.fetch_thumbnail_url(file_name, thumb_width)
    ext = Path(urlparse(url).path).suffix or ".jpg"
    dest = dest_stem.with_name(dest_stem.name + ext)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(wc.download_file(url))
    return dest
