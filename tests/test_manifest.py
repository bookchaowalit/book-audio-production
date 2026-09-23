import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from book_audio_production.errors import AudioError
from book_audio_production.manifest import parse_manifest


def manifest(tracks: str | None = None) -> bytes:
    entries = tracks or (
        '{"track_id":"intro","source":"intro.wav",'
        '"targets":{"integrated_lufs":-16,"true_peak_dbtp":-1},'
        '"output_format":"flac"}'
    )
    return (
        '{"schema_version":"audio-batch.v1","batch_id":"pilot-1",'
        f'"tracks":[{entries}]}}'
    ).encode()


def test_parse_audio_batch_v1() -> None:
    batch = parse_manifest(manifest())

    assert batch.batch_id == "pilot-1"
    assert batch.tracks[0].track_id == "intro"
    assert batch.tracks[0].targets.lra_lu is None
    assert batch.tracks[0].trim is None


def test_rejects_oversized_manifest_payload() -> None:
    with pytest.raises(AudioError) as error:
        parse_manifest(b" " * (1024 * 1024 + 1))

    assert error.value.code == "RESOURCE_LIMIT_EXCEEDED"


def test_parse_optional_trim_and_lra() -> None:
    payload = manifest(
        '{"track_id":"intro","source":"intro.wav",'
        '"trim":{"start_ms":100,"end_ms":900},'
        '"targets":{"integrated_lufs":-16,"true_peak_dbtp":-1,"lra_lu":8},'
        '"output_format":"wav_pcm24"}'
    )

    track = parse_manifest(payload).tracks[0]

    assert track.trim is not None
    assert (track.trim.start_ms, track.trim.end_ms) == (100, 900)
    assert track.targets.lra_lu == 8
    assert track.output_format == "wav_pcm24"


def test_manifest_schema_accepts_valid_input_and_rejects_invalid_input() -> None:
    schema_path = Path(__file__).parents[1] / "schemas" / "audio-batch.v1.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    valid = json.loads(manifest())
    invalid = {**valid, "schema_version": "audio-batch.v2"}

    assert list(validator.iter_errors(valid)) == []
    assert list(validator.iter_errors(invalid))


@pytest.mark.parametrize(
    "payload",
    [b"{", b"\xff", b'{"schema_version":"audio-batch.v1","schema_version":"audio-batch.v1"}'],
)
def test_rejects_malformed_json(payload: bytes) -> None:
    with pytest.raises(AudioError) as error:
        parse_manifest(payload)

    assert error.value.code == "INVALID_MANIFEST"


def test_rejects_unknown_schema_version() -> None:
    with pytest.raises(AudioError) as error:
        parse_manifest(b'{"schema_version":"audio-batch.v2","batch_id":"x","tracks":[]}')

    assert error.value.code == "UNSUPPORTED_SCHEMA"


def test_rejects_duplicate_track_ids() -> None:
    track = (
        '{"track_id":"same","source":"a.wav","targets":{"integrated_lufs":-16,'
        '"true_peak_dbtp":-1},"output_format":"flac"}'
    )
    payload = manifest(f"{track},{track}")

    with pytest.raises(AudioError) as error:
        parse_manifest(payload)

    assert error.value.code == "DUPLICATE_TRACK_ID"


@pytest.mark.parametrize(
    ("fragment", "expected_code"),
    [
        (
            '{"track_id":"a","source":"a.wav","targets":{"integrated_lufs":NaN,'
            '"true_peak_dbtp":-1},"output_format":"flac"}',
            "INVALID_MANIFEST",
        ),
        (
            '{"track_id":"a","source":"a.wav","targets":{"integrated_lufs":-16,'
            '"true_peak_dbtp":-1},"output_format":"mp3"}',
            "INVALID_OUTPUT_FORMAT",
        ),
        (
            '{"track_id":"a","source":"a.wav","targets":{"integrated_lufs":-16,'
            '"true_peak_dbtp":-1},"output_format":[]}',
            "INVALID_OUTPUT_FORMAT",
        ),
        (
            '{"track_id":"a","source":"a.wav","targets":{"integrated_lufs":-16,'
            '"true_peak_dbtp":-1},"output_format":"flac","unexpected":true}',
            "INVALID_MANIFEST",
        ),
    ],
)
def test_rejects_invalid_track_fields(fragment: str, expected_code: str) -> None:
    with pytest.raises(AudioError) as error:
        parse_manifest(manifest(fragment))

    assert error.value.code == expected_code


def test_rejects_numbers_that_overflow_finite_float_range() -> None:
    huge_number = "9" * 4000
    payload = manifest(
        '{"track_id":"a","source":"a.wav","targets":{"integrated_lufs":'
        f'{huge_number},"true_peak_dbtp":-1}},"output_format":"flac"'
    )

    with pytest.raises(AudioError) as error:
        parse_manifest(payload)

    assert error.value.code == "INVALID_MANIFEST"
