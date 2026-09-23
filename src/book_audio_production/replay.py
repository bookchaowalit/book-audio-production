"""Fingerprint-based replay and collision handling for batch processing."""

from __future__ import annotations

import json
from pathlib import Path

from .artifacts import verify_manifest
from .batch import _canonical_batch, _fingerprint, fingerprint_sources, process_batch_once
from .errors import AudioError
from .locking import exclusive_lock
from .models import AudioBatch, AudioBatchResult, AudioLimits
from .report import deserialize_result
from .validation import validate_roots


def _pinned_versions() -> tuple[str, str]:
    lock_path = Path(__file__).parents[2] / "toolchain.lock.json"
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise AudioError("TOOLCHAIN_LOCK_INVALID", "Pinned media tool versions cannot be read") from None
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != "audio-toolchain.v1"
        or not isinstance(payload.get("ffmpeg_version"), str)
        or not isinstance(payload.get("ffprobe_version"), str)
    ):
        raise AudioError("TOOLCHAIN_LOCK_INVALID", "Pinned media tool versions are invalid")
    return payload["ffmpeg_version"], payload["ffprobe_version"]


def _load_exact_replay(
    manifest: Path,
    batch_id: str,
    fingerprint: str,
    ffmpeg_version: str,
    ffprobe_version: str,
) -> AudioBatchResult | None:
    if not manifest.exists():
        return None
    verification = verify_manifest(manifest)
    if not verification.passed:
        code = verification.error_code or "REPLAY_INTEGRITY_ERROR"
        if code != "UNSAFE_PATH":
            code = "REPLAY_INTEGRITY_ERROR"
        raise AudioError(code, "Stored audio result failed integrity verification")
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
        return deserialize_result(payload, replay=True)
    except AudioError:
        raise AudioError("REPLAY_INTEGRITY_ERROR", "Stored audio result failed integrity verification") from None


def process_batch(
    batch: AudioBatch,
    input_root: Path,
    output_root: Path,
    limits: AudioLimits,
) -> AudioBatchResult:
    """Return an exact prior result or run once under a per-batch process lock."""
    from .limits import validate_limits

    normalized = _canonical_batch(batch)
    validate_limits(limits)
    source_root, output_path = validate_roots(Path(input_root), Path(output_root))
    ffmpeg_version, ffprobe_version = _pinned_versions()
    fingerprint = _fingerprint(
        normalized,
        limits,
        ffmpeg_version,
        ffprobe_version,
        fingerprint_sources(normalized, source_root, limits),
    )
    manifest = output_path / normalized.batch_id / "result.json"
    prior = _load_exact_replay(
        manifest, normalized.batch_id, fingerprint, ffmpeg_version, ffprobe_version
    )
    if prior is not None:
        return prior

    try:
        output_path.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise AudioError("OUTPUT_UNAVAILABLE", "Output root cannot be created") from None
    lock_path = output_path / ".locks" / f"{normalized.batch_id}.lock"
    with exclusive_lock(lock_path):
        prior = _load_exact_replay(
            manifest, normalized.batch_id, fingerprint, ffmpeg_version, ffprobe_version
        )
        if prior is not None:
            return prior
        return process_batch_once(normalized, source_root, output_path, limits)
