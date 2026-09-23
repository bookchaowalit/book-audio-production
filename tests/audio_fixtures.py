"""Synthetic, runtime-generated audio inputs for integration tests."""

from pathlib import Path

from book_audio_production.probe import verified_toolchain
from book_audio_production.runner import run_process


def create_synthetic_audio(path: Path, *, duration: float = 1.2, channels: int = 1, kind: str = "tone") -> Path:
    toolchain = verified_toolchain()
    source = "sine=frequency=440:sample_rate=44100" if kind == "tone" else "anoisesrc=color=pink:sample_rate=44100"
    result = run_process(
        [
            toolchain.ffmpeg_path,
            "-nostdin",
            "-hide_banner",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"{source}:duration={duration}",
            "-ac",
            str(channels),
            "-c:a",
            "pcm_s16le",
            "-map_metadata",
            "-1",
            "-y",
            str(path),
        ],
        10,
        64 * 1024,
    )
    if result.returncode != 0 or result.output_truncated:
        raise RuntimeError("The pinned FFmpeg build could not create a synthetic test signal")
    return path
