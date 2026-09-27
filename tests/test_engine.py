import subprocess
import time
from array import array
from pathlib import Path

import pytest

from book_audio_production.engine import (
    _GAIN_LIMITER_NORMALIZATION_TYPE,
    _trim_filter,
    milliseconds_to_samples,
    render_track,
)
from book_audio_production.errors import AudioError
from book_audio_production.models import (
    AudioLimits,
    LoudnessTargets,
    ProbeInfo,
    TrackRequest,
    TrimRange,
    ValidatedTrack,
)
from book_audio_production.probe import verified_toolchain
from book_audio_production.runner import run_process
from book_audio_production.validation import validate_track
from tests.audio_fixtures import (
    create_extreme_crest_audio,
    create_quiet_bursty_audio,
    create_synthetic_audio,
)


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


def test_render_quiet_bursty_source_recovers_through_recorrection(tmp_path: Path) -> None:
    """Real meeting-speech profile: quiet integrated loudness with ~20 dB crest.

    Two-pass linear loudnorm cannot bridge the required gain inside the true-peak
    headroom, so the engine must recover by re-running dynamic loudnorm on its own
    output until the integrated loudness lands on target, while the same QA
    tolerances stay enforced.
    """
    input_root = tmp_path / "input"
    input_root.mkdir()
    source = create_quiet_bursty_audio(input_root / "bursty.wav")
    source_bytes_before = source.read_bytes()
    request = TrackRequest("bursty", "bursty.wav", None, LoudnessTargets(-16, -1, None), "flac")
    validated = validate_track(request, input_root, AudioLimits(), run_process)

    result = render_track(validated, tmp_path / "staging" / "bursty.flac", run_process)

    assert result.status == "accepted"
    assert result.qa.passed is True
    assert result.qa.failures == ()
    assert result.normalization_type == _GAIN_LIMITER_NORMALIZATION_TYPE
    assert result.pre_measurement is not None and result.post_measurement is not None
    assert result.pre_measurement.integrated_lufs < -20
    assert abs(result.post_measurement.integrated_lufs - (-16)) <= 0.5
    assert result.post_measurement.true_peak_dbtp <= -0.9
    assert result.output_bytes > 0
    assert source.read_bytes() == source_bytes_before


def _decode_mono(path: Path) -> array:
    toolchain = verified_toolchain()
    completed = subprocess.run(
        [toolchain.ffmpeg_path, "-nostdin", "-v", "error", "-i", str(path), "-ac", "1", "-f", "f32le", "-acodec", "pcm_f32le", "-"],
        capture_output=True,
        check=True,
        timeout=60,
    )
    samples = array("f")
    samples.frombytes(completed.stdout)
    return samples


def _first_index_above(samples: array, threshold: float, start: int) -> int:
    for index in range(start, len(samples)):
        if abs(samples[index]) > threshold:
            return index
    raise AssertionError("no sample above threshold")


def test_limiter_recovery_keeps_output_time_aligned_with_source(tmp_path: Path) -> None:
    """The gain+limiter path must not shift audio by the limiter lookahead (A/V sync)."""
    input_root = tmp_path / "input"
    input_root.mkdir()
    source = create_quiet_bursty_audio(input_root / "bursty.wav")
    request = TrackRequest("bursty", "bursty.wav", None, LoudnessTargets(-16, -1, None), "flac")
    validated = validate_track(request, input_root, AudioLimits(), run_process)
    output = tmp_path / "staging" / "bursty.flac"

    result = render_track(validated, output, run_process)

    assert result.normalization_type == _GAIN_LIMITER_NORMALIZATION_TYPE
    source_samples, output_samples = _decode_mono(source), _decode_mono(output)
    assert len(output_samples) == len(source_samples)
    # The burst starting at t=3.0 s must land on the same sample in both files.
    search_from = int(2.9 * 44100)
    source_onset = _first_index_above(source_samples, 0.1, search_from)
    output_peak = max(abs(value) for value in output_samples[search_from : search_from + 44100])
    output_onset = _first_index_above(output_samples, 0.25 * output_peak, search_from)
    assert abs(output_onset - source_onset) <= 20


def test_render_fades_only_the_edges_cut_by_trim(tmp_path: Path) -> None:
    """Trim points inside a waveform get a short fade so the cut does not click."""
    input_root = tmp_path / "input"
    input_root.mkdir()
    create_synthetic_audio(input_root / "tone.wav")
    # 203 ms / 801 ms fall mid-cycle of the 440 Hz tone, so an unfaded cut starts and ends loud.
    request = TrackRequest("tone", "tone.wav", TrimRange(203, 801), LoudnessTargets(-18, -1, None), "wav_pcm24")
    validated = validate_track(request, input_root, AudioLimits(), run_process)
    output = tmp_path / "staging" / "tone.wav"

    result = render_track(validated, output, run_process)

    assert result.status == "accepted"
    samples = _decode_mono(output)
    peak = max(abs(value) for value in samples)
    assert max(abs(value) for value in samples[:22]) < 0.15 * peak
    assert max(abs(value) for value in samples[-22:]) < 0.15 * peak
    # The body stays untouched past the fade window.
    assert max(abs(value) for value in samples[400:500]) > 0.9 * peak


def test_trim_filter_leaves_uncut_edges_unfaded() -> None:
    probe = ProbeInfo(codec_name="pcm_s16le", channels=1, sample_rate=44100, duration_seconds=1.0, file_bytes=88244)

    def filter_for(trim: TrimRange | None) -> str:
        start = 0 if trim is None or trim.start_ms is None else milliseconds_to_samples(trim.start_ms, 44100)
        end = None if trim is None or trim.end_ms is None else milliseconds_to_samples(trim.end_ms, 44100)
        request = TrackRequest("tone", "tone.wav", trim, LoudnessTargets(-16, -1, None), "flac")
        track = ValidatedTrack(request, Path("tone.wav"), "0" * 64, start, end, probe)
        return _trim_filter(track)

    assert "afade" not in filter_for(None)
    assert "afade" not in filter_for(TrimRange(0, 1000))
    head_only = filter_for(TrimRange(100, None))
    assert "afade=t=in" in head_only and "afade=t=out" not in head_only
    tail_only = filter_for(TrimRange(0, 900))
    assert "afade=t=out" in tail_only and "afade=t=in" not in tail_only


def test_render_extreme_crest_source_fails_closed_when_target_is_unreachable(tmp_path: Path) -> None:
    """A source silent 99.5% of the time cannot hold -16 LUFS under -1 dBTP.

    The recorrection loop must give up after its bounded passes and fail closed
    instead of publishing an artifact that misses its targets.
    """
    input_root = tmp_path / "input"
    input_root.mkdir()
    create_extreme_crest_audio(input_root / "extreme.wav")
    validated = validate_track(
        TrackRequest("extreme", "extreme.wav", None, LoudnessTargets(-16, -1, None), "flac"),
        input_root,
        AudioLimits(),
        run_process,
    )

    with pytest.raises(AudioError) as error:
        render_track(validated, tmp_path / "staging" / "extreme.flac", run_process)

    assert error.value.code == "QA_FAILED"


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
