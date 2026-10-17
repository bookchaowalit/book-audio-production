"""Load the pinned FFmpeg/FFprobe versions shipped with the package."""

from __future__ import annotations

import json

# importlib.resources.files() needs 3.9+; the package requires Python >= 3.12.
# nosemgrep: python.lang.compatibility.python37.python37-compatibility-importlib2
from importlib import resources

from .errors import AudioError

LOCK_SCHEMA_VERSION = "audio-toolchain.v1"
LOCK_RESOURCE = "toolchain.lock.json"


def pinned_versions() -> tuple[str, str]:
    """Return ``(ffmpeg_version, ffprobe_version)`` from the packaged lock file.

    The lock is package data, so this works the same from a source checkout,
    an editable install, and an installed wheel.
    """
    try:
        text = resources.files(__package__).joinpath(LOCK_RESOURCE).read_text(encoding="utf-8")
        payload = json.loads(text)
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise AudioError("TOOLCHAIN_LOCK_INVALID", "Pinned media tool versions cannot be read") from None
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != LOCK_SCHEMA_VERSION
        or not isinstance(payload.get("ffmpeg_version"), str)
        or not isinstance(payload.get("ffprobe_version"), str)
    ):
        raise AudioError("TOOLCHAIN_LOCK_INVALID", "Pinned media tool versions are invalid")
    return payload["ffmpeg_version"], payload["ffprobe_version"]
