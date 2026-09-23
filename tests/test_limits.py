import pytest

from book_audio_production.errors import AudioError
from book_audio_production.limits import validate_batch_capacity, validate_limits
from book_audio_production.models import AudioLimits


@pytest.mark.parametrize(
    "limits",
    [
        AudioLimits(max_tracks=0),
        AudioLimits(max_tracks=21),
        AudioLimits(max_source_bytes=2 * 1024**3 + 1),
        AudioLimits(max_track_seconds=7201),
        AudioLimits(max_batch_seconds=28801),
        AudioLimits(max_output_bytes_per_track=8 * 1024**3 + 1),
        AudioLimits(max_output_bytes_per_batch=40 * 1024**3 + 1),
        AudioLimits(track_deadline_seconds=21601),
        AudioLimits(batch_deadline_seconds=86401),
        AudioLimits(process_output_limit_bytes=1024 * 1024 + 1),
    ],
)
def test_rejects_invalid_or_over_cap_limits(limits: AudioLimits) -> None:
    with pytest.raises(AudioError) as error:
        validate_limits(limits)

    assert error.value.code == "INVALID_LIMITS"


def test_accepts_default_and_reduced_limits() -> None:
    validate_limits(AudioLimits())
    validate_limits(AudioLimits(max_tracks=2, max_source_bytes=1024, track_deadline_seconds=30))


@pytest.mark.parametrize("duration", [float("nan"), float("inf"), -1, 28801])
def test_rejects_invalid_or_over_cap_batch_duration(duration: float) -> None:
    with pytest.raises(AudioError) as error:
        validate_batch_capacity(1, duration, AudioLimits())

    assert error.value.code == "RESOURCE_LIMIT_EXCEEDED"


def test_batch_capacity_obeys_reduced_track_count_and_duration() -> None:
    limits = AudioLimits(max_tracks=1, max_batch_seconds=20)

    with pytest.raises(AudioError):
        validate_batch_capacity(2, 10, limits)
    with pytest.raises(AudioError):
        validate_batch_capacity(1, 21, limits)
