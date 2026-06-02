# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
