"""Small deterministic quality checks applied to measured audio output."""

from __future__ import annotations

import math

from .errors import AudioError

_NEAR_FULL_SCALE_DBFS = -0.1


def warnings_for_sample_peak(peak_dbfs: float) -> tuple[str, ...]:
    """Warn when a measured sample peak is within 0.1 dB of full scale."""
    if isinstance(peak_dbfs, bool) or not isinstance(peak_dbfs, (int, float)) or not math.isfinite(peak_dbfs):
        raise AudioError("MEASUREMENT_UNAVAILABLE", "Sample peak measurement is unavailable")
    return ("near_full_scale_peak",) if peak_dbfs >= _NEAR_FULL_SCALE_DBFS else ()
