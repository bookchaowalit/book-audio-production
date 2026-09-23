"""Bounded subprocess adapter for local FFmpeg and FFprobe calls."""

from __future__ import annotations

import subprocess
import threading
import time
import math
from dataclasses import dataclass, field
from typing import Sequence

from .errors import AudioError
from .models import MeasurementStatus, ProcessResult

_MAX_OUTPUT_BYTES = 1024 * 1024


@dataclass
class _Capture:
    limit: int
    stdout: bytearray = field(default_factory=bytearray)
    stderr: bytearray = field(default_factory=bytearray)
    stored: int = 0
    truncated: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    def drain(self, pipe, target: bytearray) -> None:
        try:
            while chunk := pipe.read(64 * 1024):
                with self.lock:
                    available = max(0, self.limit - self.stored)
                    kept = chunk[:available]
                    target.extend(kept)
                    self.stored += len(kept)
                    if len(kept) != len(chunk):
                        self.truncated = True
        finally:
            pipe.close()


def run_process(argv: Sequence[str], timeout_seconds: float, output_limit_bytes: int) -> ProcessResult:
    """Run one argument vector without a shell and cap combined captured output."""
    if (
        isinstance(argv, (str, bytes))
        or not isinstance(argv, Sequence)
        or not argv
        or any(not isinstance(argument, str) for argument in argv)
        or not argv[0].strip()
    ):
        raise AudioError("INVALID_COMMAND", "Media command must be a non-empty argument list")
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
        or isinstance(output_limit_bytes, bool)
        or not isinstance(output_limit_bytes, int)
        or output_limit_bytes < 1
        or output_limit_bytes > _MAX_OUTPUT_BYTES
    ):
        raise AudioError("INVALID_LIMITS", "Media process limits are invalid")

    start = time.monotonic()
    try:
        process = subprocess.Popen(
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
    except FileNotFoundError:
        raise AudioError("TOOL_NOT_FOUND", "Required media tool is not available") from None
    except OSError:
        raise AudioError("PROCESS_FAILED", "Media process could not be started") from None

    assert process.stdout is not None and process.stderr is not None
    capture = _Capture(output_limit_bytes)
    stdout_thread = threading.Thread(target=capture.drain, args=(process.stdout, capture.stdout), daemon=True)
    stderr_thread = threading.Thread(target=capture.drain, args=(process.stderr, capture.stderr), daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    cpu_seconds: float | None = None
    measurement_status: MeasurementStatus = "unavailable"
    try:
        import psutil

        child = psutil.Process(process.pid)
    except Exception:
        child = None

    deadline = start + timeout_seconds
    timed_out = False
    while True:
        if child is not None:
            try:
                times = child.cpu_times()
                cpu_seconds = float(times.user + times.system)
                measurement_status = "measured"
            except Exception:
                pass
        if process.poll() is not None:
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            timed_out = True
            break
        time.sleep(min(0.01, remaining))

    if timed_out:
        try:
            process.terminate()
            process.wait(timeout=0.2)
        except (OSError, subprocess.TimeoutExpired):
            try:
                process.kill()
                process.wait(timeout=1)
            except (OSError, subprocess.TimeoutExpired):
                pass
    else:
        process.wait()

    stdout_thread.join(timeout=2)
    stderr_thread.join(timeout=2)
    elapsed = max(0.0, time.monotonic() - start)
    if timed_out:
        raise AudioError("PROCESS_TIMEOUT", "FFmpeg process exceeded its time limit", retryable=True)
    if cpu_seconds is None:
        measurement_status = "unavailable"
    return ProcessResult(
        returncode=process.returncode if process.returncode is not None else -1,
        stdout=bytes(capture.stdout),
        stderr=bytes(capture.stderr),
        elapsed_seconds=elapsed,
        cpu_seconds=cpu_seconds if measurement_status == "measured" else None,
        measurement_status=measurement_status,
        output_truncated=capture.truncated,
    )
