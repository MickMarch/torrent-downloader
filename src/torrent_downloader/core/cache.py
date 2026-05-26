"""Shared diskcache instance used for memoizing TMDB and torrent search results."""

import diskcache

from torrent_downloader.core.config import config

app_cache: diskcache.Cache = diskcache.Cache(config.cache_directory)
