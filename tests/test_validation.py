from pathlib import Path

import pytest

from book_audio_production.errors import AudioError
from book_audio_production.models import AudioLimits, LoudnessTargets, TrackRequest, TrimRange
from book_audio_production.validation import validate_roots, validate_track


def request(source: str, trim: TrimRange | None = None) -> TrackRequest:
    return TrackRequest("sample", source, trim, LoudnessTargets(-16, -1, None), "flac")


def unreachable_runner(argv, timeout_seconds, output_limit_bytes):
    raise AssertionError("unsafe inputs must be rejected before ffprobe")


@pytest.mark.parametrize("source", ["../outside.wav", "C:/private.wav", "https://example.test/a.wav", "\\\\server\\share\\a.wav"])
def test_rejects_unsafe_source_references(tmp_path: Path, source: str) -> None:
    root = tmp_path / "input"
    root.mkdir()

    with pytest.raises(AudioError) as error:
        validate_track(request(source), root, AudioLimits(), unreachable_runner)

    assert error.value.code == "UNSAFE_PATH"


def test_rejects_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.wav"
    outside.write_bytes(b"audio")
    root = tmp_path / "input"
    root.mkdir()
    try:
        (root / "escape.wav").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable on this host")

    with pytest.raises(AudioError) as error:
        validate_track(request("escape.wav"), root, AudioLimits(), unreachable_runner)

    assert error.value.code == "UNSAFE_PATH"


def test_rejects_missing_source_before_probe(tmp_path: Path) -> None:
    root = tmp_path / "input"
    root.mkdir()

    with pytest.raises(AudioError) as error:
        validate_track(request("missing.wav"), root, AudioLimits(), unreachable_runner)

    assert error.value.code == "SOURCE_NOT_FOUND"


def test_rejects_source_over_file_size_cap_before_probe(tmp_path: Path) -> None:
    root = tmp_path / "input"
    root.mkdir()
    (root / "large.wav").write_bytes(b"0123456789")
    limits = AudioLimits(max_source_bytes=8)

    with pytest.raises(AudioError) as error:
        validate_track(request("large.wav"), root, limits, unreachable_runner)

    assert error.value.code == "RESOURCE_LIMIT_EXCEEDED"


@pytest.mark.parametrize("trim", [TrimRange(-1, 10), TrimRange(100, 100), TrimRange(200, 100)])
def test_rejects_invalid_trim_before_probe(tmp_path: Path, trim: TrimRange) -> None:
    root = tmp_path / "input"
    root.mkdir()
    (root / "sample.wav").write_bytes(b"audio")

    with pytest.raises(AudioError) as error:
        validate_track(request("sample.wav", trim), root, AudioLimits(), unreachable_runner)

    assert error.value.code == "INVALID_TRIM"


@pytest.mark.parametrize(
    "targets",
    [
        LoudnessTargets(-71, -1, None),
        LoudnessTargets(-16, 0.1, None),
        LoudnessTargets(-16, -1, 51),
        LoudnessTargets(True, -1, None),
        LoudnessTargets("-16", -1, None),
    ],
)
def test_rejects_targets_outside_filter_range_before_probe(tmp_path: Path, targets: LoudnessTargets) -> None:
    root = tmp_path / "input"
    root.mkdir()
    (root / "sample.wav").write_bytes(b"audio")
    invalid = TrackRequest("sample", "sample.wav", None, targets, "flac")

    with pytest.raises(AudioError) as error:
        validate_track(invalid, root, AudioLimits(), unreachable_runner)

    assert error.value.code == "INVALID_TARGET"


def test_rejects_overlapping_input_and_output_roots(tmp_path: Path) -> None:
    root = tmp_path / "audio"
    root.mkdir()

    with pytest.raises(AudioError) as error:
        validate_roots(root, root / "output")

    assert error.value.code == "UNSAFE_PATH"
