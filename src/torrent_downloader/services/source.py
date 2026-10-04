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


class ScrapeFailure(Enum):
    """Why no magnet came back from a details page.

    ``UNREACHABLE`` is a transport failure or a non-200 answer: the page was
    never read, so the request was fine and a retry may succeed. ``NO_MAGNET``
    is a page that was read and carries no magnet; retrying cannot help.
    """

    UNREACHABLE = "unreachable"
    NO_MAGNET = "no_magnet"


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


def scrape_magnet_from_page(page_url: str) -> str | ScrapeFailure:
    """Fetch an HTML details page and return the first magnet URI on it.

    A failure comes back as a ``ScrapeFailure`` naming its kind, so the caller
    can tell a retryable fetch problem from a page that has no magnet. The
    request runs inside the container, which is bound to the VPN interface.
    """
    try:
        response = requests.get(
            page_url,
            headers={"User-Agent": _USER_AGENT},
            timeout=_PAGE_FETCH_TIMEOUT_SECONDS,
        )
    except requests.RequestException as error:
        app_logger.warning("Failed to fetch details page %s: %s", page_url, error)
        return ScrapeFailure.UNREACHABLE

    if response.status_code != _HTTP_OK:
        app_logger.warning("Details page %s returned status %s", page_url, response.status_code)
        return ScrapeFailure.UNREACHABLE

    match = _MAGNET_PATTERN.search(response.text)
    if match is None:
        app_logger.warning("No magnet found on details page %s", page_url)
        return ScrapeFailure.NO_MAGNET
    return match.group(0)
