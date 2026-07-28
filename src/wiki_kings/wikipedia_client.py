"""Thin client over the MediaWiki API for fetching article wikitext and file info."""

from __future__ import annotations

from urllib.parse import unquote

import requests

API_URL = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "wiki-kings/0.1 (https://github.com/; data-extraction script)"


class WikipediaError(RuntimeError):
    pass


def _get(params: dict) -> dict:
    params = {**params, "format": "json", "formatversion": "2"}
    resp = requests.get(API_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise WikipediaError(data["error"].get("info", str(data["error"])))
    return data


def fetch_wikitext(page_title: str) -> str:
    """Return the raw wikitext for the current revision of a page."""
    data = _get({"action": "parse", "page": page_title, "prop": "wikitext", "redirects": 1})
    try:
        return data["parse"]["wikitext"]
    except KeyError as exc:
        raise WikipediaError(f"No wikitext returned for page {page_title!r}") from exc


def fetch_thumbnail_url(file_name: str, width: int = 400) -> str:
    """Resolve a File: name (e.g. 'King Charles III (July 2023).jpg') to a thumbnail URL.

    Falls back to the original full-resolution URL for formats MediaWiki won't
    thumbnail (e.g. SVG signatures, since `iiurlwidth` is ignored for those).
    """
    # Some infoboxes have a URL-encoded filename pasted in by mistake (e.g. "Mary
    # Queen of Scots" -> "Mary%2C Queen of Scots"). MediaWiki titles can never
    # legitimately contain a raw "%XX" sequence, so unquoting is always correct here
    # -- and a no-op for filenames that don't have one.
    file_name = unquote(file_name)
    title = file_name if file_name.lower().startswith("file:") else f"File:{file_name}"
    data = _get({
        "action": "query", "titles": title,
        "prop": "imageinfo", "iiprop": "url", "iiurlwidth": width,
    })
    pages = data.get("query", {}).get("pages", [])
    if not pages or "imageinfo" not in pages[0]:
        raise WikipediaError(f"No image info found for {title!r}")
    info = pages[0]["imageinfo"][0]
    return info.get("thumburl") or info["url"]


def download_file(url: str) -> bytes:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
    resp.raise_for_status()
    return resp.content
