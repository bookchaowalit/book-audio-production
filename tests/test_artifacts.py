import hashlib
import json
from pathlib import Path

import pytest

from book_audio_production.artifacts import publish_artifact, verify_manifest, write_manifest_atomic
from book_audio_production.errors import AudioError


def accepted_payload(output_path: str, content: bytes) -> dict[str, object]:
    return {
        "schema_version": "audio-batch-result.v1",
        "batch_id": "pilot-1",
        "status": "accepted",
        "recipe_version": "audio-v1a.1",
        "fingerprint": "a" * 64,
        "ffmpeg_version": "ffmpeg 9.0.1",
        "ffprobe_version": "ffprobe 9.0.1",
        "model_calls": 0,
        "accepted_tracks": 1,
        "rejected_tracks": 0,
        "wall_seconds": 1,
        "cpu_seconds": None,
        "measurement_status": "unavailable",
        "bytes_written": len(content),
        "monetary_cost": None,
        "cost_status": "unknown",
        "replay": False,
        "tracks": [
            {
                "track_id": "tone",
                "status": "accepted",
                "source_relative": "tone.wav",
                "source_sha256": "b" * 64,
                "trim": None,
                "requested_targets": {"integrated_lufs": -16, "true_peak_dbtp": -1, "lra_lu": None},
                "pre_measurement": None,
                "post_measurement": None,
                "output_format": "flac",
                "output_relative_path": output_path,
                "output_sha256": hashlib.sha256(content).hexdigest(),
                "output_bytes": len(content),
                "normalization_type": "linear",
                "qa": {"passed": True, "failures": [], "checks": {"render": True}},
                "wall_seconds": 1,
                "cpu_seconds": None,
                "measurement_status": "unavailable",
                "warnings": [],
                "error": None,
            }
        ],
    }


def test_publish_artifact_never_overwrites_existing_file(tmp_path: Path) -> None:
    staged = tmp_path / "staged.flac"
    final = tmp_path / "final.flac"
    staged.write_bytes(b"new")
    final.write_bytes(b"existing")

    with pytest.raises(AudioError) as error:
        publish_artifact(staged, final)

    assert error.value.code == "OUTPUT_EXISTS"
    assert final.read_bytes() == b"existing"
    assert staged.read_bytes() == b"new"


def test_atomic_manifest_verifies_output_hash_and_size(tmp_path: Path) -> None:
    batch_dir = tmp_path / "pilot-1"
    artifact = batch_dir / "artifacts" / "tone.flac"
    artifact.parent.mkdir(parents=True)
    content = b"lossless-output"
    artifact.write_bytes(content)
    manifest = batch_dir / "result.json"

    write_manifest_atomic(manifest, accepted_payload("artifacts/tone.flac", content))
    verification = verify_manifest(manifest)

    assert verification.passed is True
    assert verification.artifacts_checked == 1
    assert verification.bytes_checked == len(content)


def test_verifier_rejects_tampered_artifact_and_path_escape(tmp_path: Path) -> None:
    batch_dir = tmp_path / "pilot-1"
    batch_dir.mkdir()
    artifact = batch_dir / "tone.flac"
    artifact.write_bytes(b"original")
    manifest = batch_dir / "result.json"
    write_manifest_atomic(manifest, accepted_payload("tone.flac", b"original"))
    artifact.write_bytes(b"modified")

    assert verify_manifest(manifest).error_code == "REPLAY_INTEGRITY_ERROR"

    unsafe = accepted_payload("../outside.flac", b"original")
    unsafe_manifest = batch_dir / "unsafe.json"
    write_manifest_atomic(unsafe_manifest, unsafe)
    assert verify_manifest(unsafe_manifest).error_code == "UNSAFE_PATH"


def test_orphan_artifact_without_manifest_is_not_accepted(tmp_path: Path) -> None:
    batch_dir = tmp_path / "pilot-1"
    (batch_dir / "artifacts").mkdir(parents=True)
    (batch_dir / "artifacts" / "orphan.flac").write_bytes(b"orphan")

    verification = verify_manifest(batch_dir / "result.json")

    assert verification.passed is False
    assert verification.error_code == "MANIFEST_NOT_FOUND"


def test_atomic_manifest_does_not_replace_existing_manifest(tmp_path: Path) -> None:
    manifest = tmp_path / "result.json"
    manifest.write_text('{"existing":true}', encoding="utf-8")

    with pytest.raises(AudioError) as error:
        write_manifest_atomic(manifest, {"schema_version": "audio-batch-result.v1"})

    assert error.value.code == "OUTPUT_EXISTS"
    assert json.loads(manifest.read_text(encoding="utf-8")) == {"existing": True}


def test_verifier_rejects_tampered_manifest_even_when_artifact_is_unchanged(tmp_path: Path) -> None:
    batch_dir = tmp_path / "pilot-1"
    artifact = batch_dir / "tone.flac"
    batch_dir.mkdir()
    content = b"lossless-output"
    artifact.write_bytes(content)
    manifest = batch_dir / "result.json"
    write_manifest_atomic(manifest, accepted_payload("tone.flac", content))
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["wall_seconds"] = 99
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    verification = verify_manifest(manifest)

    assert verification.passed is False
    assert verification.error_code == "REPLAY_INTEGRITY_ERROR"
