"""The slow credential probe: one cheap read-only call per owned credential, on an interval.

Refusals on live calls already flip a credential to invalid the moment they
happen; the probe exists for keys that expire while nobody is searching.
"""

import asyncio
from collections.abc import Awaitable, Callable

from torrent_downloader.core.config import config
from torrent_downloader.core.logger import app_logger
from torrent_downloader.services.qbittorrent import get_torrent_client
from torrent_downloader.services.tmdb import probe_tmdb

STARTUP_DELAY_SECONDS = 15.0


def probe_all() -> None:
    """Exercise each owned credential once; each call classifies itself into the tracker."""
    probe_tmdb()
    get_torrent_client()


async def run_probe_loop(
    stop: asyncio.Event,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    startup_delay: float = STARTUP_DELAY_SECONDS,
) -> None:
    """Probe after a short startup delay, then every `credential_check_interval_seconds`.

    The interval is read each round so a runtime setting change applies to the
    next wait without a restart.
    """
    await sleep(startup_delay)
    while not stop.is_set():
        try:
            await asyncio.to_thread(probe_all)
        except Exception:  # noqa: BLE001 - the loop must survive any single probe failure
            app_logger.exception("Credential probe failed")
        await sleep(float(config.credential_check_interval_seconds))
