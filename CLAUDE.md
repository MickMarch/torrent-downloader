# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
uv sync --dev

# Run API (production)
uv run torrent-downloader

# Run API (dev, hot-reload)
uv run torrent-downloader-dev

# Run all tests
uv run pytest

# Run single test
uv run pytest tests/test_middleware.py::TestRequestIdHeader::test_response_includes_request_id
```

## Environment Setup

Copy `.env.example` to `.env` and populate. All config loads via `pydantic-settings` from `.env`.

All fields are optional at import time (for CI compatibility), but the service will not function correctly without real values at runtime.

- `QB_API_KEY` — qBittorrent Web UI API key
- `TMDB_API_KEY` — TMDB v3 API key
- `API_KEY` — static key required in `X-API-Key` header on all protected endpoints

Required (v1.1+):
- `MOVIES_PATH` — container-side save path (e.g. `/media/movies`); passed to qBittorrent as save_path
- `TV_PATH` — container-side save path (e.g. `/media/tv`); passed to qBittorrent as save_path
- `MOVIES_HOST_PATH` — host-side path for the same directory (e.g. `F:\Media\Movies`); returned to orchestrator for Jellyfin library registration
- `TV_HOST_PATH` — host-side path for the same directory (e.g. `F:\Media\TV`); returned to orchestrator for Jellyfin library registration

Optional (defaults shown):
- `QB_HOST=127.0.0.1`, `QB_PORT=8080`
- `API_HOST=0.0.0.0`, `API_PORT=8000`
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

**Auth:** All endpoints except `/api/v1/health` require `X-API-Key: <API_KEY>`. Implemented in `core/auth.py` via FastAPI `Security(APIKeyHeader)`. Missing key → 403 with `UNAUTHORIZED` code. Wrong key → 403 with `UNAUTHORIZED` code. Applied via `dependencies=[Depends(verify_api_key)]` on `include_router` calls in `main.py`; system routes apply it per-route so `/health` stays public.

**Rate limiting:** `slowapi` limiter in `core/limiter.py`. General endpoints: `RATE_LIMIT_DEFAULT` (60/min). Search endpoints: `RATE_LIMIT_SEARCH` (20/min). `/health` exempt via `@limiter.exempt`. Applied via `@limiter.limit(RATE_LIMIT_*)` decorator on each route handler. Breach returns 429 with `Retry-After` header and `RATE_LIMITED` error code. Limiter storage must be reset between tests - see `reset_rate_limiter` fixture in `conftest.py`.

**Request logging:** `core/middleware.py` - `RequestLoggingMiddleware` logs method, path+query, status, duration on every request. Injects `X-Request-ID` UUID response header per request for cross-service correlation.

**Error handling:** `core/errors.py` defines `ErrorCode` enum and `AppException`. All structured errors use shape `{"status": "error", "code": "<ErrorCode>", "detail": "..."}`. Exception handlers registered in `main.py` for `AppException`, `RequestValidationError`, and `RateLimitExceeded`. `schemas/errors.py` holds `ErrorResponse` Pydantic model used in `responses=` on route decorators for OpenAPI documentation.

**VPN enforcement:** Every download request verifies qBittorrent is bound to `NordLynx` interface via `is_vpn_bound()`. Health check also exposes this status. Blocks if wrong interface.

**Caching:** `diskcache.Cache` (`app_cache`) used in two places — TMDB results via `@app_cache.memoize()` decorator, torrent search results via explicit `app_cache.get/set`. Both respect `CACHE_EXPIRATION_SECONDS`.

**Module layout:**
- `core/config.py` — single `AppConfig` pydantic-settings instance (`config`) imported everywhere
- `core/auth.py` — `verify_api_key` FastAPI dependency; patch `torrent_downloader.core.auth.config` in tests
- `core/limiter.py` — `limiter` slowapi instance, `RATE_LIMIT_DEFAULT`, `RATE_LIMIT_SEARCH` constants
- `core/middleware.py` — `RequestLoggingMiddleware` (BaseHTTPMiddleware)
- `core/cache.py` — single `app_cache` diskcache instance
- `core/logger.py` — `app_logger` singleton; stdout only (no file handler - correct for containers)
- `core/errors.py` — `ErrorCode` enum, `AppException`
- `services/qbittorrent.py` — all qBittorrent logic: client init, search (with timeout polling), filter/sort/group, transfers, VPN check
- `services/tmdb.py` — TMDB search + field extractors
- `schemas/` — Pydantic models for request/response validation; `errors.py` holds shared `ErrorResponse`
- `routers/` — APIRouter modules grouped by domain (`system`, `search`, `transfers`); registered in `main.py` via `include_router` with `prefix="/api/v1"`
- `main.py` — FastAPI app instantiation, middleware stack, exception handlers, router registration, custom OpenAPI schema, uvicorn entrypoints

**Search result pipeline:** `execute_plugin_search` (raw qBittorrent plugin results) → `filter_and_sort_results` (drop below min seeders, require magnet URIs, sort desc by seeders) → `group_by_resolution` (PTN parse filename → bucket into 4K/1080p/720p).

**Torrent search uses qBittorrent's built-in search plugin system** (not a direct tracker API). Search is async-polled with a configurable timeout; hanging plugins are stopped explicitly.

**OpenAPI:** Custom `openapi()` override in `main.py` sets `/health` security to `[]` (no auth required). All other routes inherit `APIKeyHeader` security scheme auto-generated from the `Security(APIKeyHeader)` dependency. Error response shapes declared via `responses=` on each route using `ErrorResponse` schema.

## v1.1 spec (feat/v1.1-media-type-paths - in progress)

### Goal

Remove `save_path` from the download request. Caller passes `media_type` instead;
torrent-downloader resolves the container-side save path from config and stores
`hash -> (media_type, host_path)` in diskcache so the orchestrator can retrieve
it at torrent completion time.

### Changes

**`core/config.py`** — add four new required fields:
- `movies_path: str` — container-side path, no default (must be set)
- `tv_path: str` — container-side path, no default (must be set)
- `movies_host_path: str` — host-side path, no default (must be set)
- `tv_host_path: str` — host-side path, no default (must be set)

**`schemas/downloads.py`** — replace `save_path: str` with `media_type: MediaType`
(`MediaType` is `Literal["movie", "show"]` or a `str` enum). Remove `save_path`.
`dry_run` stays.

**`routers/transfers.py` (`POST /download`)** — resolve save_path internally:
```python
save_path = config.movies_path if payload.media_type == "movie" else config.tv_path
```
After successful `torrents_add`, store in diskcache:
```python
app_cache.set(f"media_type:{torrent_hash}", {"media_type": payload.media_type, "host_path": host_path})
```
`torrent_hash` comes from qBittorrent's response or is derived from the magnet URI.

**New endpoint: `GET /api/v1/transfers/{hash}/info`** — orchestrator calls this
after receiving the qBittorrent completion webhook. Returns:
```json
{ "media_type": "movie", "host_path": "F:\\Media\\Movies", "save_path": "/media/movies" }
```
Reads from diskcache. Returns 404 with `TRANSFER_NOT_FOUND` error code if hash
unknown (e.g. download predates v1.1 or cache evicted).

**`core/errors.py`** — add `TRANSFER_NOT_FOUND`.

**`.env.example`** — add the four new path vars with host vs container notes.

### Hash extraction from magnet URI

qBittorrent's `torrents_add()` does not return the hash directly. Extract from
magnet URI via regex on `xt=urn:btih:([a-fA-F0-9]{40}|[a-zA-Z2-7]{32})`.
Normalise to lowercase. Store immediately after `torrents_add` succeeds.

### Path returned to orchestrator

`host_path` in the response is the media type's root dir (e.g. `F:\Media\Movies`),
not the individual torrent's subfolder. The orchestrator appends the torrent name
(`%N` from qBittorrent's completion script) to build the full item path for
`POST /library/paths`.

## Versioning

Version is derived from git tags via `hatch-vcs` - do not hardcode it anywhere. `src/torrent_downloader/_version.py` is generated at build time and is gitignored. To release a new version: merge to main, tag (`git tag -a vX.Y.Z -m "vX.Y.Z"`), push the tag (`git push origin vX.Y.Z`), create a GitHub Release from the tag, update `CHANGELOG.md` before tagging.

## Testing patterns

- Always use `uv run pytest`, never `python -m pytest`
- Always pytest style, never unittest
- `conftest.py` has two `autouse=True` fixtures: `patch_api_key` (mocks auth config) and `reset_rate_limiter` (clears limiter storage between tests)
- `client` fixture sends `X-API-Key` header by default; use `unauthed_client` fixture for auth rejection tests
- Mock `torrent_downloader.core.auth.config` (not `core.config`) when patching auth
- Mock `torrent_downloader.core.middleware.app_logger` when asserting on log output
