"""Cross-process exclusive locks that never remove another run's lock file."""

from __future__ import annotations

import math
import os
import secrets
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .errors import AudioError


@contextmanager
def exclusive_lock(path: Path, *, wait_seconds: float = 30.0) -> Iterator[None]:
    """Acquire an O_EXCL lock, wait briefly for active runs, and preserve stale locks."""
    if (
        isinstance(wait_seconds, bool)
        or not isinstance(wait_seconds, (int, float))
        or not math.isfinite(wait_seconds)
        or wait_seconds < 0
    ):
        raise AudioError("INVALID_LIMITS", "Lock wait duration must be a non-negative finite number")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise AudioError("OUTPUT_UNAVAILABLE", "Batch lock directory cannot be created") from None

    token = secrets.token_hex(24)
    deadline = time.monotonic() + wait_seconds
    descriptor = None
    while descriptor is None:
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AudioError("LOCK_BUSY", "Another run owns this batch lock", retryable=True) from None
            time.sleep(min(0.05, remaining))
        except OSError:
            raise AudioError("OUTPUT_UNAVAILABLE", "Batch lock cannot be created") from None

    try:
        with os.fdopen(descriptor, "w", encoding="ascii", newline="\n") as file:
            file.write(token + "\n")
            file.flush()
            os.fsync(file.fileno())
            owned_stat = os.fstat(file.fileno())
        yield
    finally:
        try:
            current_stat = path.stat()
            current_token = path.read_text(encoding="ascii").strip()
            if (
                current_token == token
                and current_stat.st_dev == owned_stat.st_dev
                and current_stat.st_ino == owned_stat.st_ino
            ):
                path.unlink()
        except (OSError, UnboundLocalError):
            pass
