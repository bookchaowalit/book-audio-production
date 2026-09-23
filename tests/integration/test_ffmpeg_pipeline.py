from pathlib import Path

from book_audio_production.models import AudioLimits, LoudnessTargets, TrackRequest, TrimRange
from book_audio_production.runner import run_process
from book_audio_production.validation import validate_track
from book_audio_production.engine import render_track
from tests.audio_fixtures import create_synthetic_audio


def test_sine_and_noise_round_trip_through_normalization(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    input_root.mkdir()

    for kind in ("tone", "noise"):
        source = create_synthetic_audio(input_root / f"{kind}.wav", duration=0.8, kind=kind)
        request = TrackRequest(kind, source.name, TrimRange(100, 700), LoudnessTargets(-18, -1, None), "flac")
        validated = validate_track(request, input_root, AudioLimits(), run_process)

        result = render_track(validated, tmp_path / "staging" / f"{kind}.flac", run_process)

        assert result.qa.passed is True
        assert result.pre_measurement is not None and result.post_measurement is not None
        assert abs(result.post_measurement.duration_seconds - 0.6) <= 1 / 44100 + 0.002
        assert abs(result.post_measurement.integrated_lufs - (-18)) <= 0.5
        assert result.post_measurement.true_peak_dbtp <= -0.9
