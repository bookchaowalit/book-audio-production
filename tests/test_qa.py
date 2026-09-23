import math

import pytest

from book_audio_production.errors import AudioError
from book_audio_production.qa import warnings_for_sample_peak


@pytest.mark.parametrize(
    ("peak", "expected"),
    [(-0.09, True), (-0.1, True), (-0.11, False), (-1.0, False)],
)
def test_sample_peak_warning_threshold(peak: float, expected: bool) -> None:
    warnings = warnings_for_sample_peak(peak)

    assert ("near_full_scale_peak" in warnings) is expected


def test_sample_peak_warning_rejects_non_finite_measurement() -> None:
    with pytest.raises(AudioError) as error:
        warnings_for_sample_peak(math.nan)

    assert error.value.code == "MEASUREMENT_UNAVAILABLE"
