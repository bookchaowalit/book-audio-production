"""Isolated, repeatable synthetic benchmark for the local audio pipeline."""

from __future__ import annotations

import math
import time
from pathlib import Path

from .engine import process_batch
from .errors import AudioError
from .models import AudioBatch, AudioLimits, BenchmarkResult, LoudnessTargets, TrackRequest
from .probe import verified_toolchain
from .runner import run_process


def _create_tone(path: Path, duration_seconds: float = 0.4) -> None:
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
            f"sine=frequency=440:sample_rate=44100:duration={duration_seconds}",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            "-map_metadata",
            "-1",
            "-n",
            str(path),
        ],
        10,
        64 * 1024,
    )
    if result.returncode != 0 or result.output_truncated or not path.is_file() or path.stat().st_size <= 0:
        raise AudioError("PROCESS_FAILED", "Pinned FFmpeg could not create the synthetic benchmark input")


def run_benchmark(output: Path, samples: int, limits: AudioLimits) -> BenchmarkResult:
    """Process synthetic tracks, then exercise rejection, partial, and replay paths."""
    from .limits import validate_limits

    validate_limits(limits)
    if isinstance(samples, bool) or not isinstance(samples, int) or not 1 <= samples <= limits.max_tracks:
        raise AudioError("INVALID_LIMITS", "Benchmark samples must fit within the configured track limit")
    root = Path(output).resolve(strict=False)
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise AudioError("OUTPUT_EXISTS", "Benchmark output directory must be empty")
    try:
        root.mkdir(parents=True, exist_ok=True)
        input_root = root / "inputs"
        run_root = root / "runs"
        input_root.mkdir()
    except FileExistsError:
        raise AudioError("OUTPUT_EXISTS", "Benchmark output directory must be empty") from None
    except OSError:
        raise AudioError("OUTPUT_UNAVAILABLE", "Benchmark output directory cannot be created") from None

    start = time.monotonic()
    tone_path = input_root / "tone.wav"
    _create_tone(tone_path)
    targets = LoudnessTargets(-18, -1, None)
    requests = tuple(
        TrackRequest(f"sample-{index + 1:02d}", "tone.wav", None, targets, "flac")
        for index in range(samples)
    )
    accepted_batch = AudioBatch("benchmark-accepted", requests)
    accepted_result = process_batch(accepted_batch, input_root, run_root, limits)
    replay_result = process_batch(accepted_batch, input_root, run_root, limits)

    rejected_batch = AudioBatch(
        "benchmark-rejected",
        (TrackRequest("missing", "missing.wav", None, targets, "flac"),),
    )
    rejected_result = process_batch(rejected_batch, input_root, run_root, limits)
    partial_batch = AudioBatch(
        "benchmark-partial",
        (
            TrackRequest("available", "tone.wav", None, targets, "flac"),
            TrackRequest("missing", "missing.wav", None, targets, "flac"),
        ),
    )
    partial_result = process_batch(partial_batch, input_root, run_root, limits)

    measured = [result for result in (accepted_result, partial_result) if result.accepted_tracks > 0]
    cpu_seconds = (
        sum(result.cpu_seconds for result in measured if result.cpu_seconds is not None)
        if measured and all(result.measurement_status == "measured" and result.cpu_seconds is not None for result in measured)
        else None
    )
    return BenchmarkResult(
        accepted=accepted_result.accepted_tracks + partial_result.accepted_tracks,
        rejected=rejected_result.rejected_tracks + partial_result.rejected_tracks,
        partial_batches=int(partial_result.status == "completed_with_errors"),
        qa_failures=sum(
            not track.qa.passed
            for result in (accepted_result, rejected_result, partial_result)
            for track in result.tracks
        ),
        replay_hits=int(replay_result.replay),
        wall_seconds=max(0.0, time.monotonic() - start),
        cpu_seconds=cpu_seconds if cpu_seconds is None or math.isfinite(cpu_seconds) else None,
        bytes_written=accepted_result.bytes_written + partial_result.bytes_written,
        model_calls=0,
        monetary_cost=None,
        cost_status="unknown",
    )
