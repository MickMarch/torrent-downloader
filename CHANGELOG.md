# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.6.0] - 2026-09-01

### Added

- `VPN_INTERFACES` config: a comma-separated allowlist of network interface
  names qBittorrent may be bound to, so any VPN provider can be used instead of
  only NordLynx. Defaults to `NordLynx`, so existing deployments need no `.env`
  change. The check stays fail-closed: an empty or unset allowlist rejects every
  download rather than allowing any interface.
- Unit tests for `is_vpn_bound`, which previously had no direct coverage (every
  existing test stubbed it at the router boundary).

### Changed

- The VPN binding check now logs the interface actually in use on every check
  (INFO on match, CRITICAL on mismatch).
- The `VPN_NOT_BOUND` 403 detail now names the accepted interfaces. The bound
  interface is deliberately kept out of the response and logged instead, since
  on VPN drop it is often the host's real LAN adapter name.

## [1.5.0] - 2026-07-20

### Added

- HTML details-page sources are now downloadable. When `source_url` is a tracker
  details page (not a magnet or `.torrent` file), `POST /download` fetches the
  page and scrapes the embedded `magnet:?xt=urn:btih:...`, then adds that magnet
  (`services/source.py`). This is where the seeded results for many shows live
  (e.g. limetorrents), so shows that returned only page URLs are now downloadable.
  An unscrapeable page returns 422. `services/source.py` also centralises source
  classification (magnet / `.torrent` file / HTML page).

### Changed

- Torrent search filtering now keeps any magnet or http source URL (magnet,
  `.torrent` file, or HTML details page) - all three are addable now that pages
  are scraped. Only non-http, non-magnet URLs are dropped.

## [1.4.0] - 2026-07-20

### Changed

- `POST /download` now accepts `source_url` (renamed from `magnet_uri`), which
  may be a magnet URI OR an http `.torrent` file URL. qBittorrent adds either
  directly. This recovers results from plugins that return a `.torrent` link
  instead of a magnet (e.g. torlock), which were previously dropped entirely -
  the reason some TV searches returned no downloadable options.
- Torrent search filtering (`filter_and_sort_results`) now keeps results whose
  `fileUrl` is a magnet OR a `.torrent` file URL. HTML details-page URLs are
  still dropped (magnet-from-page scraping is a later tier).

### Added

- `POST /download` response now includes `torrent_hash`, the resolved BTIH
  info-hash. For a magnet it is parsed from the URI; for a `.torrent` URL it is
  read back from qBittorrent by diffing the tracked-torrent set before and after
  the add (deterministic, equals qBittorrent's own hash, matches the completion
  webhook `%I`). `None` if it could not be resolved; the completion webhook
  backfills it.

## [1.3.3] - 2026-07-17

### Fixed

- Torrent results with no parseable or unrecognised resolution (common for
  older/SD TV rips like HDTV and DVDRip) are now bucketed under `Other` in
  `GET /api/v1/search/torrents` instead of being silently dropped. Previously
  `group_by_resolution` kept only 4K/1080p/720p, so a show search that returned
  only untagged releases came back empty even when viable, well-seeded torrents
  existed (e.g. "The Simpsons Season 23").

## [1.3.2] - 2026-07-17

### Fixed

- Season-scope search pattern changed from an `S0N` tag to `Season N`
  ("The Wire Season 2"), matching how season packs are actually named on
  trackers. The `S0N` form mostly matched single-episode releases, so
  season-scoped searches returned few or no pack hits. Episode scope keeps
  the `S0NE0M` tag.

## [1.3.1] - 2026-07-17

### Fixed

- TV detail route renamed from `GET /api/v1/search/tmdb/tv/{series_id}` to
  `GET /api/v1/search/tmdb/show/{series_id}`, matching the documented API
  surface and the shared `MediaType` vocabulary (`movie`/`show`). The
  orchestrator builds this path from `MediaType.SHOW.value`, so the old `tv`
  segment returned 404 through the gateway - which silently disabled the bot's
  TV season/episode scope picker and degraded show title resolution.

## [1.3.0] - 2026-07-02

### Added

- TV season/episode targeting on `GET /api/v1/search/torrents`. `media_type` is
  now a required query param; shows accept optional `season` and `episode`
  params. The search pattern is refined with an `S0N`/`S0NE0M` tag and results
  are strictly filtered to the requested season - non-matching seasons are
  dropped, while multi-season range packs and complete-series packs are kept as
  ranked-below fallbacks so the set is never empty. Fixes older seasons being
  buried by the latest season's higher-seeded packs. Consumes the
  `TorrentSearchScope` model from medialab-contracts v0.3.0.

### Changed

- `medialab-contracts` pin bumped to v0.3.0.
- Torrent search plugin category is now chosen from `media_type` (`movies` vs
  `tv`) instead of always `movies`.
- The torrent search cache key now varies by `media_type`/`season`/`episode`, so
  a season-specific search no longer returns a cached whole-series result set.

## [1.2.1] - 2026-06-29

### Fixed

- Install `git` in the Docker build stage so `uv sync` can clone the
  `medialab-contracts` git-ref dependency (the v1.2 migration made it a git
  dependency, but the Dockerfile lacked git, failing the build with "Git
  executable not found"). Surfaced by the first whole-project
  `docker compose build`.

## [1.2.0] - 2026-06-26

### Added

- `tmdb_id` (required) on `POST /download`, cached against the torrent hash and
  returned by `GET /transfers/{hash}/info`, so the orchestrator can resolve
  canonical TMDB metadata at completion time.
- Ruff lint + format configuration (`pyproject.toml`), enforcing the workspace
  rule set (`E,F,I,UP,B,SIM,PLR2004`) including the magic-value ban (`PLR2004`).
- Mypy static type checking with the pydantic plugin.
- Pre-commit hooks (ruff, whitespace, eof, yaml/toml checks).
- Dependabot config for `uv` and GitHub Actions updates.
- CI now runs lint, format check, mypy, tests, and a dependency audit
  (previously tests only).
- `integration` pytest marker for tests that need real secrets or a live
  service (skipped in CI).

### Changed

- Consume shared models from `medialab-contracts` v0.2.0: `MediaType` (now the
  shared enum, replacing the local `Literal`), `ErrorResponse`, `TransferInfo`,
  and `TransferHashInfo`. `ErrorCode` now sources its shared members from
  `CommonErrorCode`, keeping only the service-specific codes local.
- Bumped `starlette` (>=1.3.1), `pydantic-settings` (>=2.14.2), and `idna`
  (>=3.15) to resolve known CVEs surfaced by the new dependency audit.
  `starlette` 1.3 deprecates using `httpx` with its `TestClient`; migrating
  the test client to `httpx2` is tracked as a follow-up.

### Fixed

- `_resolve_host_path` now raises a clear configuration error when
  `MEDIA_HOST_PATH` is unset, instead of an opaque `AttributeError`.
- Disk-usage error handlers chain the original exception (`raise ... from err`).

## [1.0.2] - 2026-06-05

### Changed

- Standardized system endpoint response schemas: `CacheClearResponse` and `DiskUsageResponse` now include a `status` field matching `HealthResponse`. Removed `message` field from `CacheClearResponse`.

## [1.0.1] - 2026-06-03

### Fixed

- Docker build failure caused by `hatch-vcs` being unable to resolve the package version without git history in the build context. Adds `APP_VERSION` build arg passed as `SETUPTOOLS_SCM_PRETEND_VERSION` at build time.

### Documentation

- Clarified `QB_HOST` in `.env.example`: use `127.0.0.1` for host deployments, `host.docker.internal` for Docker.

## [1.0.0] - 2026-06-02

### Added

- FastAPI REST API wrapping qBittorrent and TMDB
- TMDB multi-search and detail endpoints for movies and TV series
- qBittorrent torrent search via built-in plugin system, results grouped by resolution (4K/1080p/720p)
- Download submission with VPN binding enforcement (NordLynx interface required)
- Transfer listing and stop-seeding control
- Disk usage reporting for mounted save paths
- Application cache with configurable TTL; `DELETE /cache` endpoint for manual eviction
- Static API key authentication via `X-API-Key` header on all endpoints except `/health`
- Per-IP rate limiting: 60 req/min general, 20 req/min on search endpoints; `429` with `Retry-After` header
- Request logging middleware with `X-Request-ID` UUID header for cross-service call correlation
- Structured error responses with typed `ErrorCode` enum across all endpoints
- OpenAPI documentation with auth scheme, error response shapes, and app metadata at `/docs`
- Dockerfile with non-root user and two-stage uv install for minimal image size
- GitHub Actions CI running pytest on push to main and PRs targeting main
- VCS-based versioning via `hatch-vcs` - version derived from git tags
