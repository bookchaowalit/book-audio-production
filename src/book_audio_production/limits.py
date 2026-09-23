"""Validation for pilot resource caps."""

from __future__ import annotations

from dataclasses import fields

from .errors import AudioError
from .models import AudioLimits

HARD_CAPS = {
    "max_tracks": 20,
    "max_source_bytes": 2 * 1024**3,
    "max_track_seconds": 7200,
    "max_batch_seconds": 28800,
    "max_output_bytes_per_track": 8 * 1024**3,
    "max_output_bytes_per_batch": 40 * 1024**3,
    "track_deadline_seconds": 21600,
    "batch_deadline_seconds": 86400,
    "process_output_limit_bytes": 1024 * 1024,
}


def validate_limits(limits: AudioLimits) -> None:
    """Reject zero, non-integer, or over-cap resource settings."""
    for field in fields(AudioLimits):
        value = getattr(limits, field.name)
        maximum = HARD_CAPS[field.name]
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
            raise AudioError("INVALID_LIMITS", "Configured resource limits must be positive and within pilot caps")


def validate_batch_capacity(track_count: int, source_seconds: float, limits: AudioLimits) -> None:
    """Apply track-count and cumulative source-duration caps to a batch."""
    validate_limits(limits)
    if track_count < 1 or track_count > limits.max_tracks:
        raise AudioError("RESOURCE_LIMIT_EXCEEDED", "Batch exceeds the configured track limit")
    if source_seconds < 0 or source_seconds > limits.max_batch_seconds:
        raise AudioError("RESOURCE_LIMIT_EXCEEDED", "Batch exceeds the configured duration limit")
