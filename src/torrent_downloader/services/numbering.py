"""Episode numbering: map TMDB default (canonical) numbering to the
release-season and absolute numbers release names use, from a TMDB episode
group of type TV. Pure; the TMDB reads live in ``services/tmdb.py``. Spec:
``docs/specs/anime-numbering.md`` in the workspace."""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from medialab_contracts import Episode, EpisodeNumber, ShowNumbering

SPECIALS_GROUP_ORDER = 0
"""An episode group's ``order`` 0 holds specials."""
SPECIALS_SEASON = 0
MIN_RELEASE_SEASONS = 2
"""A group must split the show into at least this many release seasons."""

FIELD_GROUPS = "groups"
FIELD_ORDER = "order"
FIELD_EPISODES = "episodes"
FIELD_SEASON_NUMBER = "season_number"
FIELD_EPISODE_NUMBER = "episode_number"

MAX_ABSOLUTE_DIGITS = 4
# Fansub absolute form: "Title - 58 (1080p)", "Title - 1100v2 [1080p]". PTN
# misreads these (it takes digits out of the trailing CRC), so they are read here.
_ABSOLUTE_EPISODE = re.compile(
    rf"\s-\s(?P<absolute>\d{{1,{MAX_ABSOLUTE_DIGITS}}})(?:v\d+)?(?=[\s\[(.]|$)"
)

CanonicalKey = tuple[int, int]


@dataclass
class GroupSeason:
    """One group of an episode group: its ``order`` is the release season."""

    order: int
    episodes: list[CanonicalKey]


def parse_absolute_episode(name: str) -> int | None:
    """The absolute episode number of a fansub-style name, or None."""
    match = _ABSOLUTE_EPISODE.search(name)
    return int(match.group("absolute")) if match else None


def parse_group_seasons(raw: dict[str, Any]) -> list[GroupSeason]:
    """TMDB ``/tv/episode_group/{id}`` -> groups by order, episodes by order."""
    seasons: list[GroupSeason] = []
    for group in raw.get(FIELD_GROUPS, []):
        ordered = sorted(group.get(FIELD_EPISODES, []), key=lambda e: e.get(FIELD_ORDER, 0))
        seasons.append(
            GroupSeason(
                order=int(group.get(FIELD_ORDER, 0)),
                episodes=[(e[FIELD_SEASON_NUMBER], e[FIELD_EPISODE_NUMBER]) for e in ordered],
            )
        )
    return sorted(seasons, key=lambda s: s.order)


def identity_numbering(tmdb_id: int, canonical: Sequence[Episode]) -> ShowNumbering:
    """TMDB numbering: release numbers equal canonical, absolute counts across seasons."""
    return ShowNumbering(
        tmdb_id=tmdb_id,
        episodes=[
            EpisodeNumber(
                season=e.season,
                episode=e.episode,
                release_season=e.season,
                release_episode=e.episode,
                absolute=index,
            )
            for index, e in enumerate(_regular(canonical), start=1)
        ],
    )


def build_numbering(
    tmdb_id: int,
    canonical: Sequence[Episode],
    groups: Sequence[GroupSeason],
    *,
    today: date,
    group_id: str,
    group_name: str = "",
) -> ShowNumbering | None:
    """The map one group gives, or None when it does not qualify.

    The regular groups must hold canonical regular episodes only, each once,
    in at least ``MIN_RELEASE_SEASONS`` release seasons, and cover every
    canonical episode that has aired. Canonical episodes after the group's
    last one (announced, not yet grouped) continue its last release season.
    """
    regular_groups = [g for g in groups if g.order != SPECIALS_GROUP_ORDER and g.episodes]
    if len(regular_groups) < MIN_RELEASE_SEASONS:
        return None
    ordered = _regular(canonical)
    canonical_keys = [(e.season, e.episode) for e in ordered]
    known = set(canonical_keys)
    mapped: dict[CanonicalKey, tuple[int, int]] = {}
    for group in regular_groups:
        for position, key in enumerate(group.episodes, start=1):
            if key not in known or key in mapped:
                return None
            mapped[key] = (group.order, position)
    if any(_aired(e, today) and (e.season, e.episode) not in mapped for e in ordered):
        return None

    last_season, last_position = max(mapped.values())
    episodes: list[EpisodeNumber] = []
    for absolute, key in enumerate(_group_order(canonical_keys, mapped), start=1):
        if key in mapped:
            release_season, release_episode = mapped[key]
        else:
            last_position += 1
            release_season, release_episode = last_season, last_position
        episodes.append(
            EpisodeNumber(
                season=key[0],
                episode=key[1],
                release_season=release_season,
                release_episode=release_episode,
                absolute=absolute,
            )
        )
    return ShowNumbering(
        tmdb_id=tmdb_id, group_id=group_id, group_name=group_name, episodes=episodes
    )


def select_auto(
    tmdb_id: int,
    canonical: Sequence[Episode],
    candidates: Iterable[tuple[str, str, Sequence[GroupSeason]]],
    *,
    today: date,
) -> ShowNumbering:
    """The first candidate ``(group_id, name, groups)`` that qualifies and
    differs from TMDB numbering, else the identity map. ``candidates`` may be
    lazy: iteration stops at the first match."""
    for group_id, name, groups in candidates:
        numbering = build_numbering(
            tmdb_id, canonical, groups, today=today, group_id=group_id, group_name=name
        )
        if numbering is not None and _differs(numbering):
            return numbering
    return identity_numbering(tmdb_id, canonical)


def _regular(canonical: Sequence[Episode]) -> list[Episode]:
    return sorted(
        (e for e in canonical if e.season != SPECIALS_SEASON), key=lambda e: (e.season, e.episode)
    )


def _aired(episode: Episode, today: date) -> bool:
    return episode.air_date is not None and episode.air_date <= today


def _group_order(
    canonical_keys: list[CanonicalKey], mapped: dict[CanonicalKey, tuple[int, int]]
) -> list[CanonicalKey]:
    """Grouped episodes in release order, then the ungrouped tail in canonical order."""
    grouped = sorted(mapped, key=lambda key: mapped[key])
    return grouped + [key for key in canonical_keys if key not in mapped]


def _differs(numbering: ShowNumbering) -> bool:
    return any(
        (e.release_season, e.release_episode) != (e.season, e.episode) for e in numbering.episodes
    )
