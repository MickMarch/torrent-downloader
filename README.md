# torrent-downloader

FastAPI microservice wrapping qBittorrent and TMDB for the
[medialab](https://github.com/MickMarch/medialab) suite. It searches metadata
and torrents, submits downloads (VPN-enforced), and reports transfers and disk
usage. It is a downstream worker: only the medialab-orchestrator calls it.

## Prerequisites

### qBittorrent

In the compose stack qBittorrent runs as a container inside the gluetun VPN
namespace, and so does this service: qBittorrent is on `127.0.0.1:8080`, the
tunnel interface is `tun0`, and the workspace provision script seeds the API
key, interface binding and search plugins. Nothing to click. See the
[workspace README](../README.md).

For a host install instead:

1. Install [qBittorrent](https://www.qbittorrent.org/download) (5.2 or newer)
   and launch it.
2. **Tools > Preferences > Web UI**: enable the Web UI, note host and port
   (default `8080`), and generate an API key for `QB_API_KEY`.
3. **Tools > Preferences > Advanced > Network interface**: bind qBittorrent to
   your VPN adapter, then list that adapter name in `VPN_INTERFACES`. Any
   provider works; comma-separate several if you switch. Downloads are rejected
   unless the bound interface matches an entry; an empty list rejects all.
4. Enable the search plugin system and install at least one plugin
   (**View > Search Engine > Search plugins**).
5. If this service runs in a container against host qBittorrent, bind the Web
   UI to `0.0.0.0` and set `QB_HOST=host.docker.internal`. `MEDIA_MOUNT_PATH`
   must then be a path qBittorrent can write, in qBittorrent's own view of the
   filesystem.

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
the [workspace README](../README.md) for the compose flow. `MEDIA_MOUNT_PATH`
is the in-container path of the media root, the same bind mount qBittorrent
and the orchestrator see, so the save paths this service hands to qBittorrent
are plain POSIX paths under it.

## API

All paths under `/api/v1`. Every endpoint except `/health` requires
`X-API-Key: <API_KEY>`; a missing or wrong key returns `403` with
`"code": "UNAUTHORIZED"`.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Public. Uptime, VPN-binding status (bool only) and `credentials`: per-key health (`ok`, `invalid`, `unreachable`, `unknown`) for the TMDB key and the qBittorrent WebUI key. A refusal on any live call marks a key `invalid` at once; a probe every `CREDENTIAL_CHECK_INTERVAL_SECONDS` covers keys that expire while idle. |
| `GET` | `/search/tmdb?query=` | TMDB multi-search (movies + shows). |
| `GET` | `/search/tmdb/movie/{tmdb_id}` | TMDB movie detail. |
| `GET` | `/search/tmdb/show/{tmdb_id}` | TMDB show detail, including the season list. |
| `GET` | `/search/tmdb/show/{tmdb_id}/episodes` | Every season and episode of a show (specials excluded) as `SeriesEpisodesResponse`, with the next episode to air and the show status. Cached for `DISCOVER_CACHE_SECONDS`. `503 TMDB_UNAVAILABLE` if TMDB is unconfigured or failing. |
| `GET` | `/search/tmdb/{media_type}/{tmdb_id}/videos?[season=]` | YouTube trailers and teasers of a title (`media_type` is `movie` or `show`) as `VideosResponse`: official first, then trailers before teasers, then newest first. `season` narrows a show to one season; on a movie it is `422 INVALID_INPUT`. English videos are included alongside `TARGET_LANGUAGE`. Cached for `DISCOVER_CACHE_SECONDS`. `503 TMDB_UNAVAILABLE` if TMDB is unconfigured or failing. |
| `GET` | `/search/torrents?query=&media_type=[&season=&episode=&alt_query=]` | qBittorrent plugin search grouped by resolution. `media_type` required; shows accept `season`/`episode`, which refine the pattern and filter results to that scope; `alt_query` is a second spelling of the title whose hits are unioned in. Each result carries `languages` and `multiAudio` parsed from its name; `AUDIO_LANGUAGE_FILTER` drops foreign-tagged releases (see `.env.example`). |
| `GET` | `/search/torrents/progress?query=&media_type=[&season=&episode=&alt_query=]` | Where the search `/search/torrents` would run with the same parameters stands, as `TorrentSearchProgress`: `state` (`idle`, `running`, `done`), patterns done out of total, results so far, elapsed and timeout. Read from an in-process registry and the pattern cache; qBittorrent is not called, so it is cheap to poll once a second. |
| `GET` | `/search/torrents/pick?query=&season=&resolution=[&episode=&min_seeders=&alt_query=&timeout_seconds=]` | The show search reduced to the single `TorrentResult` the pick rule chooses. With `episode`: exact-episode releases only (no packs). Without it: exact single-season packs only (no episodes, no multi-season or complete-series packs). Then at least `min_seeders` seeders (default `MINIMUM_SEEDERS`), the requested resolution bucket or the next lower one (`4K` -> `1080p` -> `720p`, never `Other`), most seeders then largest file. `timeout_seconds` (bounded like the `search_timeout_seconds` setting) makes this one search wait longer and skip the result cache. `404 NO_CANDIDATE` when nothing qualifies; `422 INVALID_INPUT` for a resolution outside those buckets. |
| `GET` | `/discover/{media_type}?[genre=&page=]` | One TMDB page as `DiscoverResponse` (`media_type` is `movie` or `show`): trending this week, or with `genre` the most popular titles in it with a minimum vote count. Cached for `DISCOVER_CACHE_SECONDS`. `503 TMDB_UNAVAILABLE` if TMDB is unconfigured or failing. |
| `GET` | `/discover/{media_type}/genres` | TMDB genre list as `GenresResponse`, cached like discover. |
| `POST` | `/download` | Body `{source_url, media_type, tmdb_id, dry_run?}`. `source_url` is a magnet, a `.torrent` URL, or an HTML details page. Resolves the save path as `MEDIA_MOUNT_PATH/_incoming/<Movies|Shows>` (staging; the orchestrator places into the library), enforces VPN binding, returns `torrent_hash`. `503 SOURCE_UNREACHABLE` when a details page cannot be fetched (retryable); `422 INVALID_INPUT` when it was fetched but carries no magnet. |
| `GET` | `/transfers` | Active transfers with state. |
| `GET` | `/transfers/{torrent_hash}/info` | Cached `{media_type, host_path, tmdb_id}` for a hash (used by the orchestrator at completion); `host_path` is the contracts field name and carries the save path above. 404 `TRANSFER_NOT_FOUND` if unknown. |
| `POST` | `/transfers/{torrent_hash}/resume` | Resume one torrent; no-op if already running. `404 TRANSFER_NOT_FOUND` if unknown. |
| `DELETE` | `/transfers/{torrent_hash}[?delete_files=true]` | Remove one torrent from qBittorrent, keeping its files unless `delete_files=true`. `404` if unknown. |
| `POST` | `/transfers/stop-seeding` | Pause every completed (seeding) torrent. Never touches in-progress downloads. |
| `GET` | `/storage` | Disk usage of the media path. |
| `GET` | `/settings` | Every runtime setting (search and cache behaviour) with its effective value and source (`default`, `env`, `override`). |
| `PUT` | `/settings/{key}` | Override one setting (`{"value": ...}`); validated against its bounds, persisted to `SETTINGS_PATH`, applied on the next search. |
| `DELETE` | `/settings/{key}` | Drop the override. |
| `DELETE` | `/cache` | Evict all cached data. |

Errors: `{"status": "error", "code": "<ErrorCode>", "detail": "..."}`.
Rate limits per IP: 60/min general, 20/min on `/search/*` and `/discover/*`; `429` carries
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
