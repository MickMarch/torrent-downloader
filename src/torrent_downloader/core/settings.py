"""Runtime settings: the declared tunables, their JSON override store, and the
live application onto ``config``.

Only keys in ``SETTINGS`` are visible to the API. Overrides persist on the
cache volume and are applied at import, so a restart keeps them; code that
reads ``config.<key>`` per request sees a change on the next request.
"""

import json
from enum import Enum
from pathlib import Path
from typing import Any

from medialab_contracts import (
    SettingSource,
    SettingSpec,
    SettingType,
    SettingValue,
    SettingView,
)

from torrent_downloader.core.config import AppConfig, config
from torrent_downloader.core.logger import app_logger
from torrent_downloader.services.language import LanguageFilter

_APPLIES_NEXT_SEARCH = "next search"

SETTINGS: tuple[SettingSpec, ...] = (
    SettingSpec(
        key="target_language",
        type=SettingType.STR,
        description="ISO 639-1 code TMDB metadata and the audio filter target.",
        applies=_APPLIES_NEXT_SEARCH,
    ),
    SettingSpec(
        key="audio_language_filter",
        type=SettingType.CHOICE,
        choices=[f.value for f in LanguageFilter],
        description=(
            "lenient drops foreign-tagged releases; strict also drops untagged; "
            "off only shows tags."
        ),
        applies=_APPLIES_NEXT_SEARCH,
    ),
    SettingSpec(
        key="minimum_seeders",
        type=SettingType.INT,
        min=0,
        max=1000,
        description="Releases with fewer seeders are dropped.",
        applies=_APPLIES_NEXT_SEARCH,
    ),
    SettingSpec(
        key="search_timeout_seconds",
        type=SettingType.INT,
        min=5,
        max=120,
        description="How long one plugin search may run before it is stopped.",
        applies=_APPLIES_NEXT_SEARCH,
    ),
    SettingSpec(
        key="search_concurrency",
        type=SettingType.INT,
        min=1,
        max=8,
        description="Pattern searches run in parallel up to this many at once.",
        applies=_APPLIES_NEXT_SEARCH,
    ),
    SettingSpec(
        key="cache_expiration_seconds",
        type=SettingType.INT,
        min=0,
        max=86400,
        description="How long search results stay cached.",
        applies="next cache write",
    ),
)

_SPECS: dict[str, SettingSpec] = {spec.key: spec for spec in SETTINGS}


class UnknownSettingError(KeyError):
    """The key is not a declared setting."""


def _wire(value: Any) -> SettingValue:
    """Enum members go over the wire as their value."""
    return value.value if isinstance(value, Enum) else value


def _typed(key: str, value: SettingValue) -> Any:
    """The value as the config field expects it: enum fields get the member."""
    annotation = AppConfig.model_fields[key].annotation
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return annotation(value)
    return value


class SettingsStore:
    """Overrides as one JSON document. Missing or unreadable means no overrides."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> dict[str, SettingValue]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as error:
            app_logger.warning(f"Settings store unreadable, ignoring it: {error}")
            return {}
        return data if isinstance(data, dict) else {}

    def save(self, overrides: dict[str, SettingValue]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(overrides, indent=2, sort_keys=True), encoding="utf-8")


class RuntimeSettings:
    """The declared settings applied onto a live ``AppConfig``."""

    def __init__(self, cfg: AppConfig, store: SettingsStore) -> None:
        self._config = cfg
        self._store = store
        # The value each key had before any override: the .env layer.
        self._env_values: dict[str, SettingValue] = {
            key: _wire(getattr(cfg, key)) for key in _SPECS
        }
        self._overrides: dict[str, SettingValue] = {}
        for key, raw in store.load().items():
            spec = _SPECS.get(key)
            if spec is None:
                continue
            try:
                self._overrides[key] = spec.coerce(raw)
            except ValueError as error:
                app_logger.warning(f"Stored setting ignored: {error}")
        for key, value in self._overrides.items():
            setattr(cfg, key, _typed(key, value))

    def spec(self, key: str) -> SettingSpec:
        try:
            return _SPECS[key]
        except KeyError as error:
            raise UnknownSettingError(key) from error

    def view(self, key: str) -> SettingView:
        spec = self.spec(key)
        default = _wire(AppConfig.model_fields[key].default)
        if key in self._overrides:
            source = SettingSource.OVERRIDE
        elif self._env_values[key] != default:
            source = SettingSource.ENV
        else:
            source = SettingSource.DEFAULT
        return SettingView(
            key=key,
            value=_wire(getattr(self._config, key)),
            default=default,
            source=source,
            type=spec.type,
            description=spec.description,
            applies=spec.applies,
            choices=spec.choices,
            min=spec.min,
            max=spec.max,
        )

    def views(self) -> list[SettingView]:
        return [self.view(spec.key) for spec in SETTINGS]

    def set(self, key: str, raw: Any) -> SettingView:
        """Validate, persist, apply. ``ValueError`` carries the reason."""
        value = self.spec(key).coerce(raw)
        self._overrides[key] = value
        self._store.save(self._overrides)
        setattr(self._config, key, _typed(key, value))
        app_logger.info(f"Setting {key} set to {value!r}.")
        return self.view(key)

    def reset(self, key: str) -> SettingView:
        """Drop the override; the .env value (or default) applies again."""
        self.spec(key)
        if self._overrides.pop(key, None) is not None:
            self._store.save(self._overrides)
        setattr(self._config, key, _typed(key, self._env_values[key]))
        app_logger.info(f"Setting {key} reset.")
        return self.view(key)


runtime_settings = RuntimeSettings(config, SettingsStore(Path(config.settings_path)))
