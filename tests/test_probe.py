import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from book_audio_production.errors import AudioError
from book_audio_production.models import ProcessResult
from book_audio_production.probe import probe_audio


def process_result(payload: bytes, returncode: int = 0) -> ProcessResult:
    return ProcessResult(returncode, payload, b"", 0.01, None, "unavailable", False)


def test_probe_uses_safe_local_argv_and_reads_audio_stream(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "sample.wav"
    source.write_bytes(b"audio-data")
    response = {
        "streams": [{"codec_type": "audio", "codec_name": "pcm_s16le", "channels": 2, "sample_rate": "48000", "duration": "1.25"}],
        "format": {"duration": "1.25"},
    }
    monkeypatch.setattr("book_audio_production.probe.verified_toolchain", lambda: SimpleNamespace(ffprobe_path="ffprobe"))

    def runner(argv, timeout_seconds, output_limit_bytes):
        assert isinstance(argv, list)
        assert "-protocol_whitelist" in argv
        assert "file,pipe" in argv
        assert argv[argv.index("-f") + 1] == "wav"
        assert argv.index("-f") < argv.index("-i")
        assert "-of" in argv
        assert "json" in argv
        assert argv[-1] == str(source)
        return process_result(json.dumps(response).encode())

    info = probe_audio(source, runner)

    assert (info.codec_name, info.channels, info.sample_rate) == ("pcm_s16le", 2, 48000)
    assert info.duration_seconds == 1.25
    assert info.file_bytes == len(b"audio-data")


_AUDIO_STREAM = {"codec_type": "audio", "codec_name": "pcm", "channels": 1, "sample_rate": "44100", "duration": "1"}


@pytest.mark.parametrize(
    "response",
    [
        {"streams": [], "format": {"duration": "1"}},
        {"streams": [_AUDIO_STREAM, _AUDIO_STREAM], "format": {"duration": "1"}},
        {
            "streams": [{"codec_type": "video", "codec_name": "mjpeg", "channels": 0, "sample_rate": "0", "duration": "1"}],
            "format": {"duration": "1"},
        },
    ],
)
def test_probe_rejects_missing_or_ambiguous_audio_streams(tmp_path: Path, monkeypatch, response) -> None:
    source = tmp_path / "sample.wav"
    source.write_bytes(b"audio")
    monkeypatch.setattr("book_audio_production.probe.verified_toolchain", lambda: SimpleNamespace(ffprobe_path="ffprobe"))

    with pytest.raises(AudioError) as error:
        probe_audio(source, lambda *_: process_result(json.dumps(response).encode()))

    assert error.value.code == "UNSUPPORTED_STREAM"


def test_probe_sanitizes_failed_process_and_invalid_json(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "sample.wav"
    source.write_bytes(b"audio")
    monkeypatch.setattr("book_audio_production.probe.verified_toolchain", lambda: SimpleNamespace(ffprobe_path="ffprobe"))

    with pytest.raises(AudioError) as failed:
        probe_audio(source, lambda *_: process_result(b"private path", returncode=1))
    assert failed.value.code == "PROCESS_FAILED"
    assert "private" not in str(failed.value)

    with pytest.raises(AudioError) as malformed:
        probe_audio(source, lambda *_: process_result(b"not json"))
    assert malformed.value.code == "UNSUPPORTED_STREAM"


def test_probe_rejects_incomplete_container_metadata(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "sample.wav"
    source.write_bytes(b"audio")
    monkeypatch.setattr("book_audio_production.probe.verified_toolchain", lambda: SimpleNamespace(ffprobe_path="ffprobe"))

    with pytest.raises(AudioError) as error:
        probe_audio(source, lambda *_: process_result(b'{"streams":[{}],"format":[]}'))

    assert error.value.code == "UNSUPPORTED_STREAM"
