"""execute_plugin_search reports to the progress registry while it polls, and
the progress route aggregates without touching qBittorrent."""

from fastapi.testclient import TestClient
from medialab_contracts import SearchProgressState
from pytest_mock import MockerFixture

from torrent_downloader.services import qbittorrent as qb
from torrent_downloader.services.search_progress import search_progress

PROGRESS_URL = "/api/v1/search/torrents/progress"


class TestExecutePluginSearchHooks:
    def test_registry_follows_the_search_lifecycle(self, mocker: MockerFixture) -> None:
        mocker.patch.object(qb.time, "sleep")
        client = mocker.MagicMock()
        client.search_start.return_value = {"id": 7}
        client.search_status.side_effect = [
            [{"status": "Running", "total": 3}],
            [{"status": "Running", "total": 9}],
            [{"status": "Stopped", "total": 12}],
        ]
        client.search_results.return_value = {"results": [{"fileUrl": "a"}] * 12}
        counts: list[int] = []
        original_update = search_progress.update

        def spy(pattern, category, *, results):
            counts.append(results)
            original_update(pattern, category, results=results)

        mocker.patch.object(search_progress, "update", side_effect=spy)

        results = qb.execute_plugin_search(client, "Show S01", "tv", timeout_seconds=30)

        # Each poll's running count, then the fetched total.
        assert counts == [3, 9, 12, 12]

        assert len(results) == 12
        entry = search_progress.get("Show S01", "tv")
        assert entry is not None
        assert entry.finished_at is not None
        assert entry.results == 12

    def test_timeout_still_finishes_the_entry(self, mocker: MockerFixture) -> None:
        mocker.patch.object(qb.time, "sleep")
        times = iter([0.0, 0.0, 100.0, 100.0, 100.0])
        mocker.patch.object(qb.time, "time", side_effect=lambda: next(times))
        client = mocker.MagicMock()
        client.search_start.return_value = {"id": 1}
        client.search_status.return_value = [{"status": "Running", "total": 1}]
        client.search_results.return_value = {"results": []}

        qb.execute_plugin_search(client, "Slow", "movies", timeout_seconds=5)

        entry = search_progress.get("Slow", "movies")
        assert entry is not None and entry.finished_at is not None
        client.search_stop.assert_called_once()

    def test_a_qbittorrent_failure_still_finishes_the_entry(self, mocker: MockerFixture) -> None:
        import pytest

        client = mocker.MagicMock()
        client.search_start.return_value = {"id": 1}
        client.search_status.side_effect = RuntimeError("qB gone")

        with pytest.raises(RuntimeError):
            qb.execute_plugin_search(client, "Broken", "tv", timeout_seconds=5)

        entry = search_progress.get("Broken", "tv")
        assert entry is not None and entry.finished_at is not None


class TestProgressRoute:
    def test_aggregates_the_requests_patterns_without_qbittorrent(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        get_client = mocker.patch("torrent_downloader.routers.search.get_torrent_client")
        mocker.patch.object(qb.app_cache, "get", return_value=None)
        search_progress.start("The Wire S02", "tv")
        search_progress.update("The Wire S02", "tv", results=4)

        body = client.get(
            PROGRESS_URL, params={"query": "The Wire", "media_type": "show", "season": 2}
        ).json()

        get_client.assert_not_called()
        assert body["state"] == SearchProgressState.RUNNING.value
        # Season scope: "The Wire S02", "The Wire Season 2", "The Wire".
        assert body["patterns_total"] == 3
        assert body["patterns_done"] == 0
        assert body["results_so_far"] == 4
        search_progress.finish("The Wire S02", "tv")

    def test_alt_query_and_movie_bare_title_patterns_are_counted(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mocker.patch.object(qb.app_cache, "get", return_value=None)
        body = client.get(
            PROGRESS_URL,
            params={"query": "Dune 2021", "media_type": "movie", "alt_query": "dune part one 2021"},
        ).json()
        # "Dune 2021", "Dune", "dune part one 2021", "dune part one".
        assert body["patterns_total"] == 4
        assert body["state"] == SearchProgressState.IDLE.value

    def test_invalid_scope_is_422(self, client: TestClient) -> None:
        response = client.get(
            PROGRESS_URL, params={"query": "x", "media_type": "movie", "season": 1}
        )
        assert response.status_code == 422

    def test_cached_patterns_read_as_done(self, client: TestClient, mocker: MockerFixture) -> None:
        mocker.patch.object(qb.app_cache, "get", return_value=[{"fileUrl": "a"}, {"fileUrl": "b"}])
        body = client.get(PROGRESS_URL, params={"query": "Dune", "media_type": "movie"}).json()
        assert body["state"] == SearchProgressState.DONE.value
        assert body["patterns_done"] == body["patterns_total"] == 1
        assert body["results_so_far"] == 2
