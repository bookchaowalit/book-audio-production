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


def create_quiet_bursty_audio(path: Path, *, duration: float = 24.0) -> Path:
    """Continuous quiet body with occasional loud peaks, matching meeting-speech crest.

    Deterministic stand-in for real meeting speech (~18 dB crest over a continuous
    body): the gain needed to reach the mastering target exceeds what two-pass
    linear loudnorm can bridge inside the true-peak headroom.
    """
    toolchain = verified_toolchain()
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
            f"aevalsrc=0.02*sin(2*PI*220*t)+if(lt(mod(t\\,3)\\,0.09)\\,0.35*sin(2*PI*330*t)\\,0):s=44100:d={duration:0.2f}",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            "-map_metadata",
            "-1",
            "-y",
            str(path),
        ],
        30,
        64 * 1024,
    )
    if result.returncode != 0 or result.output_truncated:
        raise RuntimeError("The pinned FFmpeg build could not create the bursty test signal")
    return path


def create_extreme_crest_audio(path: Path, *, duration: float = 24.0) -> Path:
    """Extreme crest (~26 dB) source whose target is physically unreachable.

    A signal that is silent 99.5% of the time cannot hold -16 LUFS integrated
    under a -1 dBTP ceiling; the engine must fail closed with QA_FAILED.
    """
    toolchain = verified_toolchain()
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
            f"aevalsrc=if(lt(mod(t\\,2)\\,0.01)\\,0.5\\,0.00005):s=44100:d={duration:0.2f}",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            "-map_metadata",
            "-1",
            "-y",
            str(path),
        ],
        30,
        64 * 1024,
    )
    if result.returncode != 0 or result.output_truncated:
        raise RuntimeError("The pinned FFmpeg build could not create the extreme test signal")
    return path
