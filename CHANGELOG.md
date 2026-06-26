# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
