"""Local TOML configuration for reducible pilot resource limits."""

from __future__ import annotations

import tomllib
from pathlib import Path

from .errors import AudioError
from .limits import validate_limits
from .models import AudioLimits

_LIMIT_FIELDS = frozenset(AudioLimits.__dataclass_fields__)


def load_limits(path: Path | None) -> AudioLimits:
    """Load optional per-machine limits, which may only lower hard caps."""
    limits = AudioLimits()
    if path is None:
        return limits
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        raise AudioError("INVALID_CONFIG", "Local audio configuration cannot be read") from None

    if set(payload).difference({"limits"}):
        raise AudioError("INVALID_CONFIG", "Local audio configuration has unknown sections")
    raw_limits = payload.get("limits", {})
    if not isinstance(raw_limits, dict) or set(raw_limits).difference(_LIMIT_FIELDS):
        raise AudioError("INVALID_CONFIG", "Local audio configuration has unknown limit names")

    values = {field: getattr(limits, field) for field in _LIMIT_FIELDS}
    for field, value in raw_limits.items():
        if isinstance(value, bool) or not isinstance(value, int):
            raise AudioError("INVALID_CONFIG", "Configured resource limits must be integers")
        values[field] = value
    configured = AudioLimits(**values)
    try:
        validate_limits(configured)
    except AudioError:
        raise AudioError("INVALID_CONFIG", "Configured resource limits exceed the allowed pilot caps") from None
    return configured
