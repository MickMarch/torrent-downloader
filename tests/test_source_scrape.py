"""Tests for scraping a magnet URI out of an HTML details page."""

from pytest_mock import MockerFixture

from torrent_downloader.services.source import (
    SourceKind,
    classify_source,
    scrape_magnet_from_page,
)

_MAGNET = "magnet:?xt=urn:btih:612C3D851D51D36830BF6D439E63E66967508044&dn=Foo"
_PAGE = "https://www.limetorrents.lol/Foo-torrent-123.html"


class TestClassifySource:
    def test_magnet(self) -> None:
        assert classify_source("magnet:?xt=urn:btih:abc") is SourceKind.MAGNET

    def test_torrent_file(self) -> None:
        assert classify_source("https://x.com/y.torrent") is SourceKind.TORRENT_FILE

    def test_html_page(self) -> None:
        assert classify_source(_PAGE) is SourceKind.HTML_PAGE

    def test_http_torrent_takes_priority_over_page(self) -> None:
        # A .torrent URL is served directly even though it is http.
        assert classify_source("http://x.com/a.torrent") is SourceKind.TORRENT_FILE


class TestScrapeMagnet:
    def test_returns_first_magnet_on_page(self, mocker: MockerFixture) -> None:
        html = f'<a href="{_MAGNET}">download</a>'
        mock_resp = mocker.MagicMock(status_code=200, text=html)
        mocker.patch("torrent_downloader.services.source.requests.get", return_value=mock_resp)

        assert scrape_magnet_from_page(_PAGE) == _MAGNET

    def test_returns_none_when_no_magnet(self, mocker: MockerFixture) -> None:
        mock_resp = mocker.MagicMock(status_code=200, text="<html>no magnet here</html>")
        mocker.patch("torrent_downloader.services.source.requests.get", return_value=mock_resp)

        assert scrape_magnet_from_page(_PAGE) is None

    def test_returns_none_on_http_error(self, mocker: MockerFixture) -> None:
        mock_resp = mocker.MagicMock(status_code=404, text="")
        mocker.patch("torrent_downloader.services.source.requests.get", return_value=mock_resp)

        assert scrape_magnet_from_page(_PAGE) is None

    def test_returns_none_on_request_exception(self, mocker: MockerFixture) -> None:
        import requests

        mocker.patch(
            "torrent_downloader.services.source.requests.get",
            side_effect=requests.RequestException("boom"),
        )

        assert scrape_magnet_from_page(_PAGE) is None
