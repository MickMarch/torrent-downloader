"""Where every torrent search in flight stands, for the progress endpoint.

``execute_plugin_search`` runs one qBittorrent job per pattern and polls it;
each poll carries the running result count. This registry keeps that state
per ``(pattern, category)``, the identity the result cache already uses, so
the web can ask how the search it just started is doing by the same
parameters it searched with. One uvicorn worker owns the search threads, so a
dict behind a lock is the whole store; finished entries expire so it never
grows.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from medialab_contracts import SearchProgressState, TorrentSearchProgress

Clock = Callable[[], float]
CachedResults = Callable[[str], Sequence[object] | None]

DEFAULT_RETENTION_SECONDS = 60
"""How long a finished pattern stays readable after it finishes: long enough
for the web's last poll, short enough that the registry stays small."""


@dataclass
class PatternProgress:
    started_at: float
    finished_at: float | None = None
    results: int = 0

    def elapsed(self, now: float) -> float:
        return max(
            0.0, (self.finished_at if self.finished_at is not None else now) - self.started_at
        )


@dataclass
class _PatternState:
    done: bool
    results: int
    elapsed: float


@dataclass
class SearchProgressRegistry:
    clock: Clock = time.monotonic
    retention_seconds: float = DEFAULT_RETENTION_SECONDS
    _entries: dict[tuple[str, str], PatternProgress] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @staticmethod
    def _key(pattern: str, category: str) -> tuple[str, str]:
        return (pattern.casefold(), category)

    def start(self, pattern: str, category: str) -> None:
        with self._lock:
            self._entries[self._key(pattern, category)] = PatternProgress(started_at=self.clock())

    def update(self, pattern: str, category: str, *, results: int) -> None:
        with self._lock:
            entry = self._entries.get(self._key(pattern, category))
            if entry is not None:
                entry.results = results

    def finish(self, pattern: str, category: str) -> None:
        with self._lock:
            entry = self._entries.get(self._key(pattern, category))
            if entry is not None and entry.finished_at is None:
                entry.finished_at = self.clock()

    def get(self, pattern: str, category: str) -> PatternProgress | None:
        """The live entry, dropping it when it finished longer than the
        retention ago. A running entry is never dropped."""
        key = self._key(pattern, category)
        now = self.clock()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.finished_at is not None and now - entry.finished_at > self.retention_seconds:
                del self._entries[key]
                return None
            return entry

    def _state_of(
        self, pattern: str, category: str, cached_results: CachedResults
    ) -> _PatternState | None:
        """Done with its count when finished or cached, running with its
        elapsed time when in flight, ``None`` when nothing has started. A live
        entry wins over a cache hit: a forced re-search skips the cache."""
        now = self.clock()
        entry = self.get(pattern, category)
        if entry is not None:
            if entry.finished_at is None:
                return _PatternState(done=False, results=entry.results, elapsed=entry.elapsed(now))
            return _PatternState(done=True, results=entry.results, elapsed=0.0)
        cached = cached_results(pattern)
        if cached is not None:
            return _PatternState(done=True, results=len(cached), elapsed=0.0)
        return None

    def aggregate(
        self,
        patterns: Sequence[str],
        category: str,
        *,
        timeout_seconds: int,
        cached_results: CachedResults,
    ) -> TorrentSearchProgress:
        """One ``TorrentSearchProgress`` for the patterns a search needs."""
        unique = list({p.casefold(): p for p in patterns}.values())
        states = [self._state_of(p, category, cached_results) for p in unique]
        started = [s for s in states if s is not None]
        done = [s for s in started if s.done]
        running = [s for s in started if not s.done]
        if running:
            state = SearchProgressState.RUNNING
        elif unique and len(done) == len(unique):
            state = SearchProgressState.DONE
        else:
            state = SearchProgressState.IDLE
        return TorrentSearchProgress(
            state=state,
            patterns_total=len(unique),
            patterns_done=len(done),
            results_so_far=sum(s.results for s in started),
            elapsed_seconds=max((s.elapsed for s in running), default=0.0),
            timeout_seconds=timeout_seconds,
        )


search_progress = SearchProgressRegistry()
