import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from book_audio_production.errors import AudioError
from book_audio_production.models import (
    AudioBatchResult,
    AudioMeasurement,
    LoudnessTargets,
    QAResult,
    TrackResult,
)
from book_audio_production.report import serialize_result

SCHEMA_PATH = Path(__file__).parents[1] / "schemas" / "audio-batch-result.v1.schema.json"


def sample_result(source: str = "tone.wav") -> AudioBatchResult:
    track = TrackResult(
        track_id="tone",
        status="accepted",
        source_relative=source,
        source_sha256="a" * 64,
        trim=None,
        requested_targets=LoudnessTargets(-16, -1, None),
        pre_measurement=AudioMeasurement(-21, 0, -18, -18, 1),
        post_measurement=AudioMeasurement(-16, 0, -13, -12, 1),
        output_format="flac",
        output_relative_path="artifacts/tone-aaaaaaaaaaaa.flac",
        output_sha256="b" * 64,
        output_bytes=1024,
        normalization_type="linear",
        qa=QAResult(True, (), {"loudness": True}),
        wall_seconds=0.5,
        cpu_seconds=0.1,
        measurement_status="measured",
        warnings=(),
        error=None,
    )
    return AudioBatchResult(
        schema_version="audio-batch-result.v1",
        batch_id="pilot-1",
        status="accepted",
        recipe_version="audio-v1a.1",
        fingerprint="c" * 64,
        ffmpeg_version="ffmpeg 9.0.1",
        ffprobe_version="ffprobe 9.0.1",
        model_calls=0,
        accepted_tracks=1,
        rejected_tracks=0,
        wall_seconds=0.5,
        cpu_seconds=0.1,
        measurement_status="measured",
        bytes_written=1024,
        monetary_cost=None,
        cost_status="unknown",
        replay=False,
        tracks=(track,),
    )


def test_serialize_result_matches_versioned_schema_and_contains_no_command_data() -> None:
    payload = serialize_result(sample_result())
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert list(Draft202012Validator(schema).iter_errors(payload)) == []
    assert payload["model_calls"] == 0
    assert "argv" not in json.dumps(payload)


@pytest.mark.parametrize("source", ["C:/private/tone.wav", "../outside.wav", "https://example.test/audio.wav"])
def test_serialize_result_rejects_non_relative_source_reference(source: str) -> None:
    with pytest.raises(AudioError) as error:
        serialize_result(sample_result(source))

    assert error.value.code == "UNSAFE_REPORT"
