"""Audio language of a release, parsed from its name, and the filter policy.

Release names carry the language when it is not the original (``FRENCH``,
``ITA.ENG``, ``HINDI``); English releases almost never carry a tag. PTN
parses the tagged ones. ``MULTi`` / ``DUAL`` mean more than one audio track,
usually including the original, so they are kept but shown.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

import PTN

from torrent_downloader.core.logger import app_logger

LANGUAGES_KEY = "languages"
MULTI_AUDIO_KEY = "multiAudio"

# ISO 639-1 code (TARGET_LANGUAGE) -> the name PTN emits.
LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "ru": "Russian",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
    "hi": "Hindi",
    "sv": "Swedish",
    "pl": "Polish",
    "tr": "Turkish",
}

_MULTI_AUDIO_PATTERN = re.compile(r"(?<![a-z0-9])(multi|dual[\s._-]?audio|dual)(?![a-z0-9])", re.I)


class LanguageFilter(str, Enum):
    LENIENT = "lenient"
    STRICT = "strict"
    OFF = "off"


def parse_languages(file_name: str) -> tuple[list[str], bool]:
    """``(audio languages, multi_audio)`` parsed from a release name.

    Languages are PTN's names, in the order tagged; empty when the name is
    untagged. Subtitle tags (``VOSTFR``, ``ENG.SUBS``) are not audio and are
    ignored here.
    """
    parsed: dict[str, Any] = PTN.parse(file_name)
    language = parsed.get("language")
    if isinstance(language, list):
        languages = [str(lang) for lang in language]
    elif isinstance(language, str):
        languages = [language]
    else:
        languages = []
    return languages, bool(_MULTI_AUDIO_PATTERN.search(file_name))


def is_allowed(
    languages: list[str], multi_audio: bool, target_name: str, policy: LanguageFilter
) -> bool:
    """Whether a result passes the audio-language policy.

    ``lenient`` drops only an explicitly foreign, single-language release.
    ``strict`` also drops untagged releases. ``off`` drops nothing.
    """
    if policy is LanguageFilter.OFF:
        return True
    if not languages:
        return policy is LanguageFilter.LENIENT
    if multi_audio:
        return True
    return target_name.lower() in {lang.lower() for lang in languages}


def annotate_and_filter(
    results: list[dict[str, Any]], *, target_code: str, policy: LanguageFilter
) -> list[dict[str, Any]]:
    """Stamp ``languages`` and ``multiAudio`` on each result, then apply the policy.

    An unknown ``target_code`` cannot be matched against PTN's names, so the
    filter behaves as ``off`` and says so once per call.
    """
    target_name = LANGUAGE_NAMES.get(target_code.lower())
    effective = policy
    if target_name is None and policy is not LanguageFilter.OFF:
        app_logger.warning(
            f"TARGET_LANGUAGE {target_code!r} has no language-name mapping; "
            "audio language filter is off for this search."
        )
        effective = LanguageFilter.OFF

    kept: list[dict[str, Any]] = []
    dropped = 0
    for result in results:
        languages, multi_audio = parse_languages(str(result.get("fileName", "")))
        result[LANGUAGES_KEY] = languages
        result[MULTI_AUDIO_KEY] = multi_audio
        if is_allowed(languages, multi_audio, target_name or "", effective):
            kept.append(result)
        else:
            dropped += 1
    if dropped:
        app_logger.info(
            f"Audio language filter ({effective.value}, target {target_name}): "
            f"dropped {dropped} of {len(results)} results."
        )
    return kept
