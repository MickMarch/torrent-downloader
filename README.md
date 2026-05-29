# Torrent Downloader

A FastAPI microservice that wraps qBittorrent and TMDB. Exposes a REST API for searching media metadata, finding torrents, submitting downloads, and reporting disk usage — intended to be called by an external orchestrator (e.g. a Discord bot or media library service) that handles save path logic and workflow coordination.

---

## Prerequisites

### qBittorrent

1. Install [qBittorrent](https://www.qbittorrent.org/download) and launch it.
2. Open **Tools → Preferences → Web UI** and enable the Web UI.
3. Set a port (default: `8080`) and note the host (`127.0.0.1` for local).
4. Under **Web UI → Authentication**, generate or set an API key and copy it.
5. Under **Tools → Preferences → Advanced → Network interface**, bind qBittorrent to your VPN interface (e.g. `NordLynx`). The API will reject downloads if this binding is absent.
6. Ensure the qBittorrent search plugin system is enabled and at least one search plugin is installed (**View → Search Engine → Search plugins**).

### TMDB

1. Create a free account at [themoviedb.org](https://www.themoviedb.org/).
2. Go to **Settings → API** and request an API key (v3 auth).
3. Copy the API key.

### Python

Requires Python 3.12+. Install [uv](https://github.com/astral-sh/uv) (recommended) or use pip.

---

## Setup

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd torrent_downloader
uv sync --dev
# or: pip install -e ".[dev]"
```

### 2. Configure environment variables

Copy the example env file and populate it:

```bash
cp .env.example .env
```

Edit `.env`:

```env
# qBittorrent
QB_HOST=127.0.0.1
QB_PORT=8080
QB_API_KEY=your_qbittorrent_api_key

# TMDB
TMDB_API_KEY=your_tmdb_api_key

# Optional — defaults shown
TARGET_LANGUAGE=en
MINIMUM_SEEDERS=10
SEARCH_TIMEOUT_SECONDS=15
CACHE_DIRECTORY=.cache
CACHE_EXPIRATION_SECONDS=3600
API_HOST=127.0.0.1
API_PORT=8000
```

### 3. Run

```bash
# Development (hot-reload)
uv run torrent-downloader-dev

# Production
uv run torrent-downloader
```

API available at `http://127.0.0.1:8000`. Interactive docs at `http://127.0.0.1:8000/docs`.

---

## API Overview

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/health` | Liveness check + VPN binding status |
| `GET` | `/api/v1/storage?path=` | Disk usage (GB + %) for a given save path |
| `DELETE` | `/api/v1/cache` | Evict all cached data |
| `GET` | `/api/v1/search/tmdb?query=` | TMDB multi-search (movies + TV) |
| `GET` | `/api/v1/search/tmdb/movie/{movie_id}` | Full TMDB movie details by ID |
| `GET` | `/api/v1/search/tmdb/tv/{series_id}` | Full TMDB TV series details by ID |
| `GET` | `/api/v1/search/torrents?query=` | Torrent search grouped by resolution |
| `POST` | `/api/v1/download` | Submit magnet URI to qBittorrent |
| `GET` | `/api/v1/transfers` | List all active transfers |
| `POST` | `/api/v1/transfers/stop-seeding` | Pause all seeding torrents |

The `/api/v1/download` endpoint requires the caller to provide the full `save_path`. Save path construction is the responsibility of the orchestrating application.

### Inter-service communication

This service is stateless and cache-only — it holds no persistent records. Orchestrators should:

- Call `/api/v1/storage` before dispatching a download to verify sufficient disk space
- Poll `/api/v1/transfers` to detect when a download completes, then notify downstream services (e.g. a media library cataloguer)
- Treat all responses as ephemeral; do not use this service as a source of truth for library state

---

## Development

```bash
# Run all tests
uv run pytest

# Run a single test
uv run pytest tests/test_search.py::test_filter_and_sort_results
```

---

## Roadmap

- [ ] Structured error responses — consistent `{"status": "error", "detail": "..."}` shape across all endpoints
- [ ] CI/CD — GitHub Actions pipeline to run tests on push and block merges on failure
- [ ] Dockerfile — containerize service for isolated deployment; docker-compose lives in the infra repo
- [ ] API authentication — protect endpoints with an API key or JWT for orchestrator-only access
- [ ] Request logging middleware — trace inbound calls for cross-service debugging
- [ ] Health check expansion — expose service version and qBittorrent reachability status
- [ ] Rate limiting — protect against runaway orchestrator loops hammering TMDB/qBittorrent
- [ ] Webhook/event emission — notify downstream services when a transfer completes
- [ ] API versioning strategy — document `/api/v1/` contract and breaking-change policy
