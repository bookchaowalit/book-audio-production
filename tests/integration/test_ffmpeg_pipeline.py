from pathlib import Path

from tests.audio_fixtures import create_synthetic_audio
from tests.toolchain import requires_pinned_toolchain

from book_audio_production.engine import render_track
from book_audio_production.models import (
    AudioLimits,
    LoudnessTargets,
    TrackRequest,
    TrimRange,
)
from book_audio_production.runner import run_process
from book_audio_production.validation import validate_track

pytestmark = requires_pinned_toolchain


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


def test_render_explicitly_drops_global_and_stream_metadata(tmp_path: Path) -> None:
    from book_audio_production.probe import verified_toolchain

    input_root = tmp_path / "input"
    input_root.mkdir()
    source = input_root / "tagged.mka"
    toolchain = verified_toolchain()
    created = run_process(
        [
            toolchain.ffmpeg_path,
            "-nostdin",
            "-hide_banner",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100:duration=1",
            "-c:a",
            "flac",
            "-metadata",
            "title=GLOBAL_PRIVATE_TAG",
            "-metadata:s:a:0",
            "comment=STREAM_PRIVATE_TAG",
            "-y",
            str(source),
        ],
        10,
        64 * 1024,
    )
    assert created.returncode == 0
    metadata_command = [
        toolchain.ffprobe_path,
        "-v",
        "error",
        "-show_entries",
        "format_tags:stream_tags",
        "-of",
        "json",
        str(source),
    ]
    source_metadata = run_process(metadata_command, 10, 64 * 1024)
    assert source_metadata.returncode == 0
    source_text = source_metadata.stdout.decode("utf-8")
    assert "GLOBAL_PRIVATE_TAG" in source_text and "STREAM_PRIVATE_TAG" in source_text

    render_commands = []

    def capture_render(argv, timeout_seconds, output_limit_bytes):
        if argv[0] == toolchain.ffmpeg_path and "-af" in argv:
            render_commands.append(list(argv))
        return run_process(argv, timeout_seconds, output_limit_bytes)

    request = TrackRequest("tagged", source.name, None, LoudnessTargets(-18, -1, None), "flac")
    validated = validate_track(request, input_root, AudioLimits(), capture_render)
    output = tmp_path / "staging" / "tagged.flac"
    result = render_track(validated, output, capture_render)

    assert result.qa.passed is True
    encode_command = next(argv for argv in render_commands if "-map_metadata" in argv)
    assert "-map_metadata:s" in encode_command
    stream_mapping = encode_command.index("-map_metadata:s")
    assert encode_command[stream_mapping + 1] == "-1"
    output_metadata = run_process(
        [toolchain.ffprobe_path, "-v", "error", "-show_entries", "format_tags:stream_tags", "-of", "json", str(output)],
        10,
        64 * 1024,
    )
    assert output_metadata.returncode == 0
    assert "GLOBAL_PRIVATE_TAG" not in output_metadata.stdout.decode("utf-8")
    assert "STREAM_PRIVATE_TAG" not in output_metadata.stdout.decode("utf-8")
