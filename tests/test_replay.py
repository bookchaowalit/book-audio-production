from pathlib import Path

import pytest

from book_audio_production.engine import process_batch
from book_audio_production.errors import AudioError
from book_audio_production.models import AudioBatch, AudioLimits, LoudnessTargets, TrackRequest
from tests.audio_fixtures import create_synthetic_audio


def make_args(tmp_path: Path):
    input_root = tmp_path / "input"
    output_root = tmp_path / "output"
    input_root.mkdir()
    create_synthetic_audio(input_root / "tone.wav", duration=0.8)
    batch = AudioBatch(
        "replay-1",
        (TrackRequest("tone", "tone.wav", None, LoudnessTargets(-18, -1, None), "flac"),),
    )
    return batch, input_root, output_root, AudioLimits()


def test_exact_replay_returns_saved_result_without_media_process(tmp_path: Path, monkeypatch) -> None:
    arguments = make_args(tmp_path)
    first = process_batch(*arguments)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("exact replay must not launch FFmpeg or FFprobe")

    monkeypatch.setattr("book_audio_production.batch.run_process", fail_if_called)
    replay = process_batch(*arguments)

    assert first.replay is False
    assert replay.replay is True
    assert replay.fingerprint == first.fingerprint
    assert replay.tracks[0].output_sha256 == first.tracks[0].output_sha256


def test_changed_request_with_existing_batch_id_conflicts(tmp_path: Path) -> None:
    batch, input_root, output_root, limits = make_args(tmp_path)
    process_batch(batch, input_root, output_root, limits)
    changed = AudioBatch(
        batch.batch_id,
        (TrackRequest("tone", "tone.wav", None, LoudnessTargets(-20, -1, None), "flac"),),
    )

    with pytest.raises(AudioError) as error:
        process_batch(changed, input_root, output_root, limits)

    assert error.value.code == "REPLAY_CONFLICT"


def test_changed_source_with_existing_batch_id_conflicts(tmp_path: Path) -> None:
    arguments = make_args(tmp_path)
    process_batch(*arguments)
    (arguments[1] / "tone.wav").write_bytes(b"changed source bytes")

    with pytest.raises(AudioError) as error:
        process_batch(*arguments)

    assert error.value.code == "REPLAY_CONFLICT"


def test_tampered_output_is_rejected_during_replay(tmp_path: Path) -> None:
    arguments = make_args(tmp_path)
    result = process_batch(*arguments)
    artifact = arguments[2] / result.batch_id / result.tracks[0].output_relative_path
    artifact.write_bytes(artifact.read_bytes() + b"tampered")

    with pytest.raises(AudioError) as error:
        process_batch(*arguments)

    assert error.value.code == "REPLAY_INTEGRITY_ERROR"
