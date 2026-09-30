from pathlib import Path

from book_audio_production.probe import probe_audio, verified_toolchain
from book_audio_production.runner import run_process
from tests.toolchain import requires_pinned_toolchain

pytestmark = requires_pinned_toolchain


def test_pinned_ffmpeg_toolchain_is_available() -> None:
    toolchain = verified_toolchain()

    assert toolchain.ffmpeg_version.startswith("ffmpeg version 9.0.1-full_build-www.gyan.dev")
    assert toolchain.ffprobe_version.startswith("ffprobe version 9.0.1-full_build-www.gyan.dev")


def test_pinned_ffprobe_reads_a_locally_generated_audio_file(tmp_path: Path) -> None:
    toolchain = verified_toolchain()
    source = tmp_path / "tone.wav"
    rendered = run_process(
        [
            toolchain.ffmpeg_path,
            "-nostdin",
            "-hide_banner",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=0.2:sample_rate=44100",
            "-c:a",
            "pcm_s16le",
            str(source),
        ],
        10,
        64 * 1024,
    )
    assert rendered.returncode == 0

    info = probe_audio(source, run_process)

    assert info.codec_name == "pcm_s16le"
    assert info.channels == 1
    assert info.sample_rate == 44100
    assert 0.19 <= info.duration_seconds <= 0.21
