from contextlib import contextmanager
from pathlib import Path

import pytest

from book_audio_production.engine import process_batch
from book_audio_production.errors import AudioError
from book_audio_production.models import (
    AudioBatch,
    AudioLimits,
    LoudnessTargets,
    TrackRequest,
)
from tests.audio_fixtures import create_synthetic_audio
from tests.toolchain import requires_pinned_toolchain


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


@requires_pinned_toolchain
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


@requires_pinned_toolchain
def test_exact_replay_canonicalizes_safe_dot_relative_source(tmp_path: Path, monkeypatch) -> None:
    batch, input_root, output_root, limits = make_args(tmp_path)
    request = batch.tracks[0]
    normalized = AudioBatch(
        batch.batch_id,
        (TrackRequest(request.track_id, f"./{request.source}", request.trim, request.targets, request.output_format),),
    )
    first = process_batch(normalized, input_root, output_root, limits)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("exact replay must not launch FFmpeg or FFprobe")

    monkeypatch.setattr("book_audio_production.batch.run_process", fail_if_called)
    replay = process_batch(normalized, input_root, output_root, limits)

    assert replay.replay is True
    assert replay.fingerprint == first.fingerprint


@requires_pinned_toolchain
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


@requires_pinned_toolchain
def test_changed_source_with_existing_batch_id_conflicts(tmp_path: Path) -> None:
    arguments = make_args(tmp_path)
    process_batch(*arguments)
    (arguments[1] / "tone.wav").write_bytes(b"changed source bytes")

    with pytest.raises(AudioError) as error:
        process_batch(*arguments)

    assert error.value.code == "REPLAY_CONFLICT"


@requires_pinned_toolchain
def test_tampered_output_is_rejected_during_replay(tmp_path: Path) -> None:
    arguments = make_args(tmp_path)
    result = process_batch(*arguments)
    artifact = arguments[2] / result.batch_id / result.tracks[0].output_relative_path
    artifact.write_bytes(artifact.read_bytes() + b"tampered")

    with pytest.raises(AudioError) as error:
        process_batch(*arguments)

    assert error.value.code == "REPLAY_INTEGRITY_ERROR"


@pytest.mark.parametrize("component", ["batch", "artifacts", "locks", "staging"])
@requires_pinned_toolchain
def test_batch_rejects_symlinked_output_directories(tmp_path: Path, monkeypatch, component: str) -> None:
    batch, input_root, output_root, limits = make_args(tmp_path)
    output_root.mkdir()
    target = {
        "batch": output_root / batch.batch_id,
        "artifacts": output_root / batch.batch_id / "artifacts",
        "locks": output_root / ".locks",
        "staging": output_root / ".staging",
    }[component]
    original_is_symlink = Path.is_symlink

    def report_selected_component_as_symlink(path: Path) -> bool:
        return path == target or original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", report_selected_component_as_symlink)

    with pytest.raises(AudioError) as error:
        process_batch(batch, input_root, output_root, limits)

    assert error.value.code == "UNSAFE_PATH"


class _StopAfterLock(Exception):
    pass


@requires_pinned_toolchain
def test_batch_deadline_is_passed_to_source_fingerprinting(tmp_path: Path, monkeypatch) -> None:
    batch, input_root, output_root, limits = make_args(tmp_path)
    deadlines = []

    def record_fingerprint(_batch, _root, _limits, *, deadline=None):
        deadlines.append(deadline)
        return {"tone": "a" * 64}

    @contextmanager
    def no_wait_lock(_path, *, wait_seconds=30):
        yield

    def stop_after_lock(*_args, **_kwargs):
        raise _StopAfterLock

    monkeypatch.setattr("book_audio_production.replay.fingerprint_sources", record_fingerprint)
    monkeypatch.setattr("book_audio_production.replay._load_exact_replay", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("book_audio_production.replay.exclusive_lock", no_wait_lock)
    monkeypatch.setattr("book_audio_production.replay.process_batch_once", stop_after_lock)

    with pytest.raises(_StopAfterLock):
        process_batch(batch, input_root, output_root, limits)

    assert len(deadlines) == 1
    assert isinstance(deadlines[0], float)


@requires_pinned_toolchain
def test_batch_lock_wait_is_bounded_by_remaining_deadline(tmp_path: Path, monkeypatch) -> None:
    batch, input_root, output_root, _limits = make_args(tmp_path)
    limits = AudioLimits(batch_deadline_seconds=2)
    waits = []

    def no_hash_deadline(_batch, _root, _limits, *, deadline=None):
        return {"tone": "a" * 64}

    @contextmanager
    def capture_lock(_path, *, wait_seconds=30):
        waits.append(wait_seconds)
        yield

    def stop_after_lock(*_args, **_kwargs):
        raise _StopAfterLock

    monkeypatch.setattr("book_audio_production.replay.fingerprint_sources", no_hash_deadline)
    monkeypatch.setattr("book_audio_production.replay._load_exact_replay", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("book_audio_production.replay.exclusive_lock", capture_lock)
    monkeypatch.setattr("book_audio_production.replay.process_batch_once", stop_after_lock)

    with pytest.raises(_StopAfterLock):
        process_batch(batch, input_root, output_root, limits)

    assert len(waits) == 1
    assert 0 < waits[0] <= 2


@requires_pinned_toolchain
def test_retry_discards_incomplete_staging_attempt_before_same_batch_id(tmp_path: Path) -> None:
    batch, input_root, output_root, limits = make_args(tmp_path)
    stale_stage = output_root / ".staging" / batch.batch_id / "interrupted-attempt"
    (stale_stage / "artifacts").mkdir(parents=True)
    (stale_stage / "artifacts" / "orphan.flac").write_bytes(b"partial output")
    (stale_stage / "result.json.sha256").write_text("orphan sidecar", encoding="ascii")

    result = process_batch(batch, input_root, output_root, limits)

    assert result.status == "accepted"
    assert not stale_stage.parent.exists()
    assert (output_root / batch.batch_id / "result.json").is_file()
