# CLAUDE.md - torrent-downloader

Workspace rules, conventions, standards and workflow live in the root
[`medialab/CLAUDE.md`](../CLAUDE.md); it is the authority when anything here
disagrees. This file holds only what is specific to this code.

## Commands

```bash
uv sync --dev
uv run torrent-downloader        # production
uv run torrent-downloader-dev    # dev, hot-reload
uv run pytest
uv run pytest tests/test_middleware.py::TestRequestIdHeader::test_response_includes_request_id
```

## Config

`.env.example` is the authoritative variable list; `core/config.py` holds the
defaults. Every field is optional at import time (CI has no `.env`) and
required at runtime. Two fields need context:

- `MEDIA_HOST_PATH` is a **host** path even when this service runs in a
  container: `save_path` is sent to host-installed qBittorrent's API, never
  used locally. The app appends the media-type subdir (`Movies` / `Shows`).
- `VPN_INTERFACES` is a fail-closed allowlist. Empty rejects every download and
  never means "allow any". `is_vpn_bound(client, [])` denies rather than falling
  back to config (the fallback checks `is not None`, not truthiness).

## Architecture

FastAPI REST API wrapping qBittorrent (torrent client) and TMDB (metadata).
Endpoint table: [README](README.md).

**Download flow:** `GET /search/tmdb` (TMDB) -> `GET /search/torrents`
(qBittorrent plugin search, category from `media_type`, grouped by
resolution; shows accept `season`/`episode`) -> `POST /download` with a
`source_url`. `services/source.py` classifies the source: magnet (hash from
the URI), `.torrent` file URL (hash read back by snapshot diff of
`torrents_info()` before/after add), or HTML details page (magnet scraped
from the page; 422 if none). VPN binding is enforced before every add. The
resolved info-hash is returned as `torrent_hash` and `{media_type, host_path,
tmdb_id}` is cached against it for the orchestrator's
`GET /transfers/{hash}/info` at completion time.

**Search pipeline:** `search_torrents` (scope-aware pattern + cache key,
category from `media_type`) -> `execute_plugin_search` -> `filter_and_sort_results`
(drop below min seeders, keep any addable source, sort by seeders) ->
`filter_by_scope` (season/episode scopes only: PTN parse, keep matches, keep
range/complete packs as ranked-below fallbacks) -> `group_by_resolution`
(4K/1080p/720p/Other). Search uses qBittorrent's built-in plugin system,
async-polled with a timeout; hanging plugins are stopped explicitly.

**Cross-cutting:** `X-API-Key` via `Security(APIKeyHeader)` in `core/auth.py`,
applied on `include_router` (system routes per-route so `/health` stays
public). `slowapi` limits in `core/limiter.py` (`RATE_LIMIT_DEFAULT`,
`RATE_LIMIT_SEARCH`), `/health` exempt. `RequestLoggingMiddleware` adds
`X-Request-ID`. Errors are `AppException` + `ErrorCode` (extends the contracts
`CommonErrorCode`). `diskcache` for TMDB (`@app_cache.memoize`) and search
results (explicit get/set). The bound VPN interface name is logged but kept out
of the 403 body and `/health` (public; on VPN drop it is often the LAN adapter).

## Module layout

```
src/torrent_downloader/
├── core/        config, auth, limiter, middleware, cache, logger, errors, constants,
│                settings_manager (runtime env updates, no route yet)
├── services/    qbittorrent (client, search, filter/sort/group, transfers, VPN check),
│                tmdb, source (source-URL classification + magnet scraping), storage
├── schemas/     request/response models; errors re-exports contracts ErrorResponse
├── routers/     system, search, transfers (registered in main.py under /api/v1)
└── main.py      app, middleware, exception handlers, custom OpenAPI (/health unauthenticated)
```

## Testing patterns

- `conftest.py` autouse fixtures: `patch_api_key` (mocks auth config) and
  `reset_rate_limiter` (clears limiter storage between tests).
- `client` fixture sends `X-API-Key`; `unauthed_client` for rejection tests.
- Patch `torrent_downloader.core.auth.config` (not `core.config`) for auth;
  patch `torrent_downloader.core.middleware.app_logger` for log assertions.
- qBittorrent and TMDB are mocked at the service boundary. Nothing live.
