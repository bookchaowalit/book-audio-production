from pathlib import Path
import time

import pytest

from book_audio_production.engine import milliseconds_to_samples, render_track
from book_audio_production.errors import AudioError
from book_audio_production.models import AudioLimits, LoudnessTargets, TrackRequest, TrimRange
from book_audio_production.runner import run_process
from book_audio_production.validation import validate_track
from tests.audio_fixtures import create_synthetic_audio


def test_millisecond_trim_uses_sample_rounding() -> None:
    assert milliseconds_to_samples(11, 44100) == 485
    assert milliseconds_to_samples(1000, 44100) == 44100


@pytest.mark.parametrize("milliseconds,sample_rate", [(-1, 44100), (1, 0), (True, 44100)])
def test_millisecond_trim_rejects_invalid_values(milliseconds, sample_rate) -> None:
    with pytest.raises(AudioError) as error:
        milliseconds_to_samples(milliseconds, sample_rate)

    assert error.value.code == "INVALID_TRIM"


def test_render_flac_is_lossless_24_bit_and_meets_loudness_targets(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    input_root.mkdir()
    source = create_synthetic_audio(input_root / "tone.wav")
    source_hash_before = source.read_bytes()
    request = TrackRequest("tone", "tone.wav", None, LoudnessTargets(-16, -1, None), "flac")
    validated = validate_track(request, input_root, AudioLimits(), run_process)

    result = render_track(validated, tmp_path / "staging" / "tone.flac", run_process)

    assert result.status == "accepted"
    assert result.qa.passed is True
    assert result.pre_measurement is not None and result.post_measurement is not None
    assert abs(result.post_measurement.integrated_lufs - (-16)) <= 0.5
    assert result.post_measurement.true_peak_dbtp <= -0.9
    assert result.normalization_type in {"linear", "dynamic"}
    assert result.output_bytes > 0
    assert result.output_sha256 is not None and len(result.output_sha256) == 64
    assert result.output_relative_path is None
    assert result.source_sha256 == validated.source_sha256
    assert source.read_bytes() == source_hash_before


def test_render_trimmed_stereo_pcm24_preserves_channel_count_and_duration(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    input_root.mkdir()
    source = create_synthetic_audio(input_root / "stereo.wav", channels=2)
    request = TrackRequest("stereo", "stereo.wav", TrimRange(200, 800), LoudnessTargets(-18, -1, None), "wav_pcm24")
    validated = validate_track(request, input_root, AudioLimits(), run_process)

    result = render_track(validated, tmp_path / "staging" / "stereo.wav", run_process)

    assert result.status == "accepted"
    assert result.post_measurement is not None
    assert abs(result.post_measurement.duration_seconds - 0.6) <= 1 / 44100 + 0.002
    assert result.qa.checks["channels_preserved"] is True
    assert result.qa.checks["lossless_24_bit_format"] is True


def test_render_refuses_to_overwrite_an_existing_output(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    input_root.mkdir()
    create_synthetic_audio(input_root / "tone.wav")
    validated = validate_track(
        TrackRequest("tone", "tone.wav", None, LoudnessTargets(-16, -1, None), "flac"),
        input_root,
        AudioLimits(),
        run_process,
    )
    output = tmp_path / "tone.flac"
    output.write_bytes(b"keep-existing")

    with pytest.raises(AudioError) as error:
        render_track(validated, output, run_process)

    assert error.value.code == "OUTPUT_EXISTS"
    assert output.read_bytes() == b"keep-existing"


def test_render_rejects_source_changed_after_validation_before_running_ffmpeg(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    input_root.mkdir()
    source = create_synthetic_audio(input_root / "tone.wav")
    validated = validate_track(
        TrackRequest("tone", "tone.wav", None, LoudnessTargets(-16, -1, None), "flac"),
        input_root,
        AudioLimits(),
        run_process,
    )
    source.write_bytes(b"changed")

    with pytest.raises(AudioError) as error:
        render_track(validated, tmp_path / "tone.flac", run_process)

    assert error.value.code == "SOURCE_CHANGED"


def test_render_deadline_includes_source_hashing_before_running_ffmpeg(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    input_root.mkdir()
    create_synthetic_audio(input_root / "tone.wav")
    validated = validate_track(
        TrackRequest("tone", "tone.wav", None, LoudnessTargets(-16, -1, None), "flac"),
        input_root,
        AudioLimits(),
        run_process,
    )

    def unreachable_runner(*_args):
        raise AssertionError("expired deadline must stop before invoking FFmpeg")

    with pytest.raises(AudioError) as error:
        render_track(validated, tmp_path / "tone.flac", unreachable_runner, deadline=time.monotonic() - 1)

    assert error.value.code == "PROCESS_TIMEOUT"


def test_render_preserves_a_file_created_at_the_target_after_initial_check(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    input_root.mkdir()
    create_synthetic_audio(input_root / "tone.wav")
    validated = validate_track(
        TrackRequest("tone", "tone.wav", None, LoudnessTargets(-16, -1, None), "flac"),
        input_root,
        AudioLimits(),
        run_process,
    )
    output = tmp_path / "tone.flac"

    def racing_runner(argv, timeout_seconds, output_limit_bytes):
        if "-bits_per_raw_sample" in argv:
            output.write_bytes(b"written-by-another-job")
        return run_process(argv, timeout_seconds, output_limit_bytes)

    with pytest.raises(AudioError) as error:
        render_track(validated, output, racing_runner)

    assert error.value.code == "OUTPUT_EXISTS"
    assert output.read_bytes() == b"written-by-another-job"


def test_render_rejects_predicted_output_over_cap_before_invoking_ffmpeg(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    input_root.mkdir()
    create_synthetic_audio(input_root / "tone.wav")
    validated = validate_track(
        TrackRequest("tone", "tone.wav", None, LoudnessTargets(-16, -1, None), "wav_pcm24"),
        input_root,
        AudioLimits(max_output_bytes_per_track=1),
        run_process,
    )

    def unreachable_runner(*_args):
        raise AssertionError("output cap must be checked before rendering")

    with pytest.raises(AudioError) as error:
        render_track(validated, tmp_path / "tone.wav", unreachable_runner)

    assert error.value.code == "RESOURCE_LIMIT_EXCEEDED"
