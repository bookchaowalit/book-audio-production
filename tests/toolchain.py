"""Skip marker for tests that run the pinned FFmpeg/FFprobe build."""

from __future__ import annotations

import pytest

from book_audio_production.errors import AudioError
from book_audio_production.probe import verified_toolchain


def _pinned_toolchain_problem() -> str | None:
    try:
        verified_toolchain()
    except AudioError as error:
        return error.code
    return None


_PROBLEM = _pinned_toolchain_problem()

requires_pinned_toolchain = pytest.mark.skipif(
    _PROBLEM is not None,
    reason=(
        f"the FFmpeg/FFprobe build pinned in toolchain.lock.json is unavailable ({_PROBLEM}); "
        "loudness and replay results are only asserted against that exact build"
    ),
)
