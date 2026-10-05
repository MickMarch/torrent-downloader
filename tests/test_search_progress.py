"""The in-process registry of searches in flight, and its aggregation into
the wire model."""

from medialab_contracts import SearchProgressState

from torrent_downloader.services.search_progress import SearchProgressRegistry

TV = "tv"
TIMEOUT = 15


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def _registry() -> tuple[SearchProgressRegistry, FakeClock]:
    clock = FakeClock()
    return SearchProgressRegistry(clock=clock, retention_seconds=TIMEOUT), clock


class TestRegistry:
    def test_start_update_finish(self) -> None:
        registry, clock = _registry()
        registry.start("Show S01", TV)
        clock.now += 2.0
        registry.update("Show S01", TV, results=7)
        entry = registry.get("Show S01", TV)
        assert entry is not None
        assert entry.results == 7 and entry.finished_at is None
        assert entry.elapsed(clock.now) == 2.0
        registry.finish("Show S01", TV)
        entry = registry.get("Show S01", TV)
        assert entry is not None and entry.finished_at == clock.now

    def test_finished_entries_expire_after_retention(self) -> None:
        registry, clock = _registry()
        registry.start("Show", TV)
        registry.finish("Show", TV)
        clock.now += TIMEOUT + 1
        assert registry.get("Show", TV) is None

    def test_running_entries_never_expire(self) -> None:
        registry, clock = _registry()
        registry.start("Show", TV)
        clock.now += TIMEOUT * 10
        assert registry.get("Show", TV) is not None

    def test_restart_resets_the_entry(self) -> None:
        registry, clock = _registry()
        registry.start("Show", TV)
        registry.update("Show", TV, results=5)
        registry.finish("Show", TV)
        clock.now += 1.0
        registry.start("Show", TV)
        entry = registry.get("Show", TV)
        assert entry is not None and entry.results == 0 and entry.finished_at is None

    def test_update_of_an_unknown_pattern_is_ignored(self) -> None:
        registry, _ = _registry()
        registry.update("nope", TV, results=3)
        registry.finish("nope", TV)
        assert registry.get("nope", TV) is None


class TestAggregate:
    def test_idle_when_nothing_started_and_nothing_cached(self) -> None:
        registry, _ = _registry()
        progress = registry.aggregate(
            ["Show S01", "Show"], TV, timeout_seconds=TIMEOUT, cached_results=lambda _p: None
        )
        assert progress.state is SearchProgressState.IDLE
        assert progress.patterns_total == 2 and progress.patterns_done == 0
        assert progress.results_so_far == 0 and progress.elapsed_seconds == 0.0
        assert progress.timeout_seconds == TIMEOUT

    def test_running_counts_done_and_cached_and_the_longest_elapsed(self) -> None:
        registry, clock = _registry()
        registry.start("Show S01", TV)
        clock.now += 4.0
        registry.update("Show S01", TV, results=3)
        registry.start("Show Season 1", TV)
        clock.now += 1.0
        registry.update("Show Season 1", TV, results=2)
        cached = {"Show": [{"fileUrl": "a"}, {"fileUrl": "b"}]}
        progress = registry.aggregate(
            ["Show S01", "Show Season 1", "Show"],
            TV,
            timeout_seconds=TIMEOUT,
            cached_results=cached.get,
        )
        assert progress.state is SearchProgressState.RUNNING
        assert progress.patterns_total == 3 and progress.patterns_done == 1
        assert progress.results_so_far == 3 + 2 + 2
        assert progress.elapsed_seconds == 5.0

    def test_done_when_every_pattern_is_finished_or_cached(self) -> None:
        registry, _ = _registry()
        registry.start("Show S01", TV)
        registry.update("Show S01", TV, results=4)
        registry.finish("Show S01", TV)
        progress = registry.aggregate(
            ["Show S01", "Show"],
            TV,
            timeout_seconds=TIMEOUT,
            cached_results=lambda p: [{"fileUrl": "x"}] if p == "Show" else None,
        )
        assert progress.state is SearchProgressState.DONE
        assert progress.patterns_done == 2 and progress.results_so_far == 5
        assert progress.elapsed_seconds == 0.0

    def test_a_pattern_is_counted_once(self) -> None:
        registry, _ = _registry()
        progress = registry.aggregate(
            ["Show", "Show"], TV, timeout_seconds=TIMEOUT, cached_results=lambda _p: None
        )
        assert progress.patterns_total == 1

    def test_a_running_entry_beats_a_stale_cache_hit(self) -> None:
        # A forced re-search (timeout override skips the cache) is in flight
        # while the old cached results still exist: report the live search.
        registry, clock = _registry()
        registry.start("Show", TV)
        clock.now += 2.0
        progress = registry.aggregate(
            ["Show"], TV, timeout_seconds=TIMEOUT, cached_results=lambda _p: [{"fileUrl": "a"}]
        )
        assert progress.state is SearchProgressState.RUNNING
        assert progress.patterns_done == 0 and progress.elapsed_seconds == 2.0
