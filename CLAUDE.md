# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies (uses uv or pip with hatchling build backend)
pip install -e ".[dev]"

# Run API (production)
torrent-downloader

# Run API (dev, hot-reload)
torrent-downloader-dev

# Run all tests
pytest

# Run single test
pytest tests/test_search.py::test_filter_and_sort_results
```

## Environment Setup

Copy `.env` and populate required fields. All config loads via `pydantic-settings` from `.env`.

Required env vars:
- `QB_API_KEY` — qBittorrent Web UI API key
- `TMDB_API_KEY` — TMDB v3 API key

Optional (defaults shown):
- `QB_HOST=127.0.0.1`, `QB_PORT=8080`
- `API_HOST=127.0.0.1`, `API_PORT=8000`
- `MINIMUM_SEEDERS=10`
- `SEARCH_TIMEOUT_SECONDS=15`
- `CACHE_DIRECTORY=.cache`, `CACHE_EXPIRATION_SECONDS=3600`
- `TARGET_LANGUAGE=en`

## Architecture

FastAPI REST API wrapping two external integrations: qBittorrent (torrent client) and TMDB (metadata).

**Request flow for a download:**
1. Client calls `GET /api/v1/search/tmdb?query=...` → TMDB lookup returns movie/show metadata
2. Client calls `GET /api/v1/search/torrents?query=...` → qBittorrent plugin search, results grouped by resolution (4K/1080p/720p)
3. Client calls `POST /api/v1/download` with selected magnet URI → VPN binding enforced before add

**VPN enforcement:** Every download request verifies qBittorrent is bound to `NordLynx` interface via `is_vpn_bound()`. Health check also exposes this status. Blocks if wrong interface.

**Caching:** `diskcache.Cache` (`app_cache`) used in two places — TMDB results via `@app_cache.memoize()` decorator, torrent search results via explicit `app_cache.get/set`. Both respect `CACHE_EXPIRATION_SECONDS`.

**Module layout:**
- `core/config.py` — single `AppConfig` pydantic-settings instance (`config`) imported everywhere
- `core/cache.py` — single `app_cache` diskcache instance
- `core/logger.py` — `app_logger` singleton
- `core/settings_manager.py` — writes config changes back to `.env` at runtime
- `services/qbittorrent.py` — all qBittorrent logic: client init, search (with timeout polling), filter/sort/group, transfers, VPN check
- `services/tmdb.py` — TMDB search + field extractors
- `schemas/` — Pydantic models for request/response validation
- `routers/` — APIRouter modules grouped by domain (`system`, `search`, `transfers`); registered in `main.py` via `include_router` with `prefix="/api/v1"`
- `main.py` — FastAPI app instantiation, CORS middleware, router registration, uvicorn entrypoints

**Search result pipeline:** `execute_plugin_search` (raw qBittorrent plugin results) → `filter_and_sort_results` (drop below min seeders, require magnet URIs, sort desc by seeders) → `group_by_resolution` (PTN parse filename → bucket into 4K/1080p/720p).

**Torrent search uses qBittorrent's built-in search plugin system** (not a direct tracker API). Search is async-polled with a configurable timeout; hanging plugins are stopped explicitly.
