import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).parents[1] / "schemas" / "audio-batch-result.v1.schema.json"


def result_payload() -> dict[str, object]:
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
        "wall_seconds": 1.25,
        "cpu_seconds": None,
        "measurement_status": "unavailable",
        "bytes_written": 512,
        "monetary_cost": None,
        "cost_status": "unknown",
        "replay": False,
        "tracks": [
            {
                "track_id": "intro",
                "status": "accepted",
                "source_relative": "intro.wav",
                "source_sha256": "b" * 64,
                "trim": None,
                "requested_targets": {
                    "integrated_lufs": -16,
                    "true_peak_dbtp": -1,
                    "lra_lu": None,
                },
                "pre_measurement": None,
                "post_measurement": None,
                "output_format": "flac",
                "output_relative_path": "pilot-1/intro-abc.flac",
                "output_sha256": "c" * 64,
                "output_bytes": 512,
                "normalization_type": "dynamic",
                "qa": {"passed": True, "failures": [], "checks": {"format": True}},
                "wall_seconds": 1.25,
                "cpu_seconds": None,
                "measurement_status": "unavailable",
                "warnings": [],
                "error": None,
            }
        ],
    }


def validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def test_result_schema_accepts_valid_manifest() -> None:
    assert list(validator().iter_errors(result_payload())) == []


@pytest.mark.parametrize(
    ("field", "value"),
    [("status", "mystery"), ("model_calls", 1)],
)
def test_result_schema_rejects_unknown_status_and_model_calls(field: str, value: object) -> None:
    payload = result_payload()
    payload[field] = value

    assert list(validator().iter_errors(payload))
