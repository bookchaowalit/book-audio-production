import json
from pathlib import Path

from jsonschema import Draft202012Validator

from book_audio_production.artifacts import verify_manifest
from book_audio_production.engine import process_batch
from book_audio_production.models import AudioBatch, AudioLimits, LoudnessTargets, TrackRequest
from book_audio_production.report import serialize_result
from tests.audio_fixtures import create_synthetic_audio


def test_process_batch_publishes_manifest_and_keeps_per_track_failure_local(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    output_root = tmp_path / "output"
    input_root.mkdir()
    create_synthetic_audio(input_root / "tone.wav", duration=0.8)
    batch = AudioBatch(
        "batch-1",
        (
            TrackRequest("tone", "tone.wav", None, LoudnessTargets(-18, -1, None), "flac"),
            TrackRequest("missing", "missing.wav", None, LoudnessTargets(-18, -1, None), "flac"),
        ),
    )

    result = process_batch(batch, input_root, output_root, AudioLimits())
    manifest_path = output_root / "batch-1" / "result.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    schema = json.loads((Path(__file__).parents[1] / "schemas" / "audio-batch-result.v1.schema.json").read_text())

    assert result.status == "completed_with_errors"
    assert result.accepted_tracks == result.rejected_tracks == 1
    assert result.model_calls == 0 and result.monetary_cost is None
    assert result.tracks[0].output_relative_path is not None
    assert result.tracks[1].error is not None and result.tracks[1].error.code == "SOURCE_NOT_FOUND"
    assert list(Draft202012Validator(schema).iter_errors(payload)) == []
    assert verify_manifest(manifest_path).passed is True
    assert "output" not in serialize_result(result)["tracks"][0]["output_relative_path"]


def test_process_batch_publishes_sanitized_rejection_without_audio_outputs(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    output_root = tmp_path / "output"
    input_root.mkdir()
    batch = AudioBatch(
        "rejected-1",
        (TrackRequest("unsafe", "../private.wav", None, LoudnessTargets(-18, -1, None), "flac"),),
    )

    result = process_batch(batch, input_root, output_root, AudioLimits())
    manifest_path = output_root / "rejected-1" / "result.json"
    payload_text = manifest_path.read_text(encoding="utf-8")
    payload = json.loads(payload_text)

    assert result.status == "rejected"
    assert result.tracks[0].error is not None and result.tracks[0].error.code == "UNSAFE_PATH"
    assert payload["tracks"][0]["source_relative"] is None
    assert "private" not in payload_text and payload["tracks"][0]["output_relative_path"] is None
    assert verify_manifest(manifest_path).passed is True
