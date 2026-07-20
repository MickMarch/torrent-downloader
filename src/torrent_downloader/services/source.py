"""Classifying a torrent source URL and scraping a magnet from an HTML page.

qBittorrent search plugins return three ``fileUrl`` shapes: a magnet, a
``.torrent`` file URL (added directly), or an HTML details page. For the last
kind the magnet lives inside the page, so it must be fetched and scraped before
the torrent can be added.
"""

from __future__ import annotations

import re
from enum import Enum

import requests

from torrent_downloader.core.logger import app_logger

_MAGNET_PREFIX = "magnet:?"
_TORRENT_SUFFIX = ".torrent"
_HTTP_PREFIX = "http"

# First magnet link on the page; trackers embed a full magnet:?xt=urn:btih:... .
_MAGNET_PATTERN = re.compile(r"magnet:\?xt=urn:btih:[^\"'\s<>]+")

_PAGE_FETCH_TIMEOUT_SECONDS = 15
_HTTP_OK = 200
# A browser-like UA; some trackers reject default library agents.
_USER_AGENT = "Mozilla/5.0 (compatible; medialab-downloader)"


class SourceKind(Enum):
    """The shape of a torrent source URL."""

    MAGNET = "magnet"
    TORRENT_FILE = "torrent_file"
    HTML_PAGE = "html_page"
    UNKNOWN = "unknown"


def classify_source(source_url: str) -> SourceKind:
    """Classify a source URL by how the torrent must be obtained from it."""
    if source_url.startswith(_MAGNET_PREFIX):
        return SourceKind.MAGNET
    if source_url.endswith(_TORRENT_SUFFIX):
        return SourceKind.TORRENT_FILE
    if source_url.startswith(_HTTP_PREFIX):
        return SourceKind.HTML_PAGE
    return SourceKind.UNKNOWN


def scrape_magnet_from_page(page_url: str) -> str | None:
    """Fetch an HTML details page and return the first magnet URI on it.

    Returns ``None`` on any failure (network error, non-200, or no magnet
    present) so the caller can degrade to a clear error rather than crashing.
    The request runs inside the container, which is bound to the VPN interface.
    """
    try:
        response = requests.get(
            page_url,
            headers={"User-Agent": _USER_AGENT},
            timeout=_PAGE_FETCH_TIMEOUT_SECONDS,
        )
    except requests.RequestException as error:
        app_logger.warning("Failed to fetch details page %s: %s", page_url, error)
        return None

    if response.status_code != _HTTP_OK:
        app_logger.warning("Details page %s returned status %s", page_url, response.status_code)
        return None

    match = _MAGNET_PATTERN.search(response.text)
    if match is None:
        app_logger.warning("No magnet found on details page %s", page_url)
        return None
    return match.group(0)
