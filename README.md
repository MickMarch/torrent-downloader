# torrent-downloader

FastAPI microservice wrapping qBittorrent and TMDB for the
[medialab](https://github.com/MickMarch/medialab) suite. It searches metadata
and torrents, submits downloads (VPN-enforced), and reports transfers and disk
usage. It is a downstream worker: only the medialab-orchestrator calls it.

## Prerequisites

### qBittorrent

1. Install [qBittorrent](https://www.qbittorrent.org/download) and launch it.
2. **Tools > Preferences > Web UI**: enable the Web UI, note host and port
   (default `8080`), and set the credential the API will use.
3. **Tools > Preferences > Advanced > Network interface**: bind qBittorrent to
   your VPN interface, then list that interface name in `VPN_INTERFACES`. Any
   provider works; comma-separate several if you switch. Downloads are rejected
   unless the bound interface matches an entry; an empty list rejects all.
4. Enable the search plugin system and install at least one plugin
   (**View > Search Engine > Search plugins**).
5. For containerized deployment, bind the Web UI to `0.0.0.0` so the container
   can reach it, and set `QB_HOST=host.docker.internal`.

### TMDB

Create a free account at [themoviedb.org](https://www.themoviedb.org/),
**Settings > API**, request a v3 key.

## Setup

```bash
uv sync --dev
cp .env.example .env     # then fill in the values
uv run torrent-downloader-dev   # dev, hot-reload
uv run torrent-downloader       # production
```

`.env.example` documents every variable. Interactive docs at `/docs`.

The service runs as a container from the workspace `docker-compose.yml`; see
the [workspace README](../README.md) for the compose flow. It mounts no media
directories itself: `MEDIA_HOST_PATH` is the host path handed to
host-installed qBittorrent.

## API

All paths under `/api/v1`. Every endpoint except `/health` requires
`X-API-Key: <API_KEY>`; a missing or wrong key returns `403` with
`"code": "UNAUTHORIZED"`.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Public. Uptime and VPN-binding status (bool only). |
| `GET` | `/search/tmdb?query=` | TMDB multi-search (movies + shows). |
| `GET` | `/search/tmdb/movie/{tmdb_id}` | TMDB movie detail. |
| `GET` | `/search/tmdb/show/{tmdb_id}` | TMDB show detail, including the season list. |
| `GET` | `/search/torrents?query=&media_type=[&season=&episode=]` | qBittorrent plugin search grouped by resolution. `media_type` required; shows accept `season`/`episode`, which refine the pattern and filter results to that scope. Each result carries `languages` and `multiAudio` parsed from its name; `AUDIO_LANGUAGE_FILTER` drops foreign-tagged releases (see `.env.example`). |
| `POST` | `/download` | Body `{source_url, media_type, tmdb_id, dry_run?}`. `source_url` is a magnet, a `.torrent` URL, or an HTML details page. Resolves the host save path from `MEDIA_HOST_PATH` + media type, enforces VPN binding, returns `torrent_hash`. |
| `GET` | `/transfers` | Active transfers with state. |
| `GET` | `/transfers/{torrent_hash}/info` | Cached `{media_type, host_path, tmdb_id}` for a hash (used by the orchestrator at completion). 404 `TRANSFER_NOT_FOUND` if unknown. |
| `POST` | `/transfers/{torrent_hash}/resume` | Resume one torrent; no-op if already running. `404 TRANSFER_NOT_FOUND` if unknown. |
| `DELETE` | `/transfers/{torrent_hash}[?delete_files=true]` | Remove one torrent from qBittorrent, keeping its files unless `delete_files=true`. `404` if unknown. |
| `POST` | `/transfers/stop-seeding` | Pause every completed (seeding) torrent. Never touches in-progress downloads. |
| `GET` | `/storage` | Disk usage of the media path. |
| `DELETE` | `/cache` | Evict all cached data. |

Errors: `{"status": "error", "code": "<ErrorCode>", "detail": "..."}`.
Rate limits per IP: 60/min general, 20/min on `/search/*`; `429` carries
`Retry-After`. Every response includes an `X-Request-ID` UUID.

This service is stateless apart from its cache. Completion is signalled by
qBittorrent's run-on-completion hook into the orchestrator, not by polling
this API.

## Development

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy src
```

Standards, workflow and release process: [workspace CLAUDE.md](../CLAUDE.md).
Code-local notes: [CLAUDE.md](CLAUDE.md).
