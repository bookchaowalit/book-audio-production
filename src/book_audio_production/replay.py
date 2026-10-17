"""Fingerprint-based replay and collision handling for batch processing."""

from __future__ import annotations

import json
import time
from pathlib import Path

from .artifacts import verify_manifest
from .batch import _canonical_batch, _fingerprint, discard_incomplete_staging, fingerprint_sources, process_batch_once
from .errors import AudioError
from .locking import exclusive_lock
from .models import AudioBatch, AudioBatchResult, AudioLimits
from .report import deserialize_result
from .toolchain_lock import pinned_versions
from .validation import validate_output_locations, validate_roots


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise AudioError("PROCESS_TIMEOUT", "Audio batch exceeded its time limit", retryable=True)
    return remaining


def _pinned_versions() -> tuple[str, str]:
    return pinned_versions()


def _load_exact_replay(
    manifest: Path,
    batch_id: str,
    fingerprint: str,
    ffmpeg_version: str,
    ffprobe_version: str,
    *,
    deadline: float | None = None,
) -> AudioBatchResult | None:
    if deadline is not None:
        _remaining(deadline)
    if not manifest.exists():
        return None
    verification = verify_manifest(manifest, deadline=deadline)
    if not verification.passed:
        code = verification.error_code or "REPLAY_INTEGRITY_ERROR"
        if code == "PROCESS_TIMEOUT":
            raise AudioError(code, "Audio batch exceeded its time limit", retryable=True)
        if code != "UNSAFE_PATH":
            code = "REPLAY_INTEGRITY_ERROR"
        raise AudioError(code, "Stored audio result failed integrity verification")
    if deadline is not None:
        _remaining(deadline)
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise AudioError("REPLAY_INTEGRITY_ERROR", "Stored audio result failed integrity verification") from None
    if not isinstance(payload, dict):
        raise AudioError("REPLAY_INTEGRITY_ERROR", "Stored audio result failed integrity verification")
    if payload.get("batch_id") != batch_id or payload.get("fingerprint") != fingerprint:
        raise AudioError("REPLAY_CONFLICT", "Batch ID already belongs to a different request")
    if payload.get("ffmpeg_version") != ffmpeg_version or payload.get("ffprobe_version") != ffprobe_version:
        raise AudioError("REPLAY_CONFLICT", "Batch ID was produced with a different media toolchain")
    try:
        result = deserialize_result(payload, replay=True)
    except AudioError:
        raise AudioError("REPLAY_INTEGRITY_ERROR", "Stored audio result failed integrity verification") from None
    if deadline is not None:
        _remaining(deadline)
    return result


def process_batch(
    batch: AudioBatch,
    input_root: Path,
    output_root: Path,
    limits: AudioLimits,
) -> AudioBatchResult:
    """Return an exact prior result or run once under a per-batch process lock."""
    from .limits import validate_limits

    start = time.monotonic()
    normalized = _canonical_batch(batch)
    validate_limits(limits)
    deadline = start + limits.batch_deadline_seconds
    source_root, output_path = validate_roots(Path(input_root), Path(output_root))
    validate_output_locations(output_path, normalized.batch_id)
    ffmpeg_version, ffprobe_version = _pinned_versions()
    fingerprint = _fingerprint(
        normalized,
        limits,
        ffmpeg_version,
        ffprobe_version,
        fingerprint_sources(normalized, source_root, limits, deadline=deadline),
    )
    _remaining(deadline)
    manifest = output_path / normalized.batch_id / "result.json"
    prior = _load_exact_replay(manifest, normalized.batch_id, fingerprint, ffmpeg_version, ffprobe_version, deadline=deadline)
    if prior is not None:
        return prior

    try:
        output_path.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise AudioError("OUTPUT_UNAVAILABLE", "Output root cannot be created") from None
    validate_output_locations(output_path, normalized.batch_id)
    lock_path = output_path / ".locks" / f"{normalized.batch_id}.lock"
    with exclusive_lock(lock_path, wait_seconds=_remaining(deadline)):
        validate_output_locations(output_path, normalized.batch_id)
        prior = _load_exact_replay(
            manifest,
            normalized.batch_id,
            fingerprint,
            ffmpeg_version,
            ffprobe_version,
            deadline=deadline,
        )
        if prior is not None:
            return prior
        discard_incomplete_staging(output_path, normalized.batch_id)
        return process_batch_once(
            normalized,
            source_root,
            output_path,
            limits,
            deadline=deadline,
            started_at=start,
        )
