"""Deterministic local orchestration for validated audio batches."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import tempfile
import time
from dataclasses import asdict, replace
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import urlsplit

from .artifacts import publish_artifact, write_manifest_atomic
from .engine import _estimate_output_bytes, render_track
from .errors import AudioError
from .manifest import parse_manifest
from .models import (
    AudioBatch,
    AudioBatchResult,
    AudioLimits,
    ErrorInfo,
    QAResult,
    TrackRequest,
    TrackResult,
    VerificationResult,
)
from .probe import verified_toolchain
from .report import serialize_result
from .runner import run_process
from .validation import validate_roots, validate_track

_RECIPE_VERSION = "audio-v1a.1"


def _canonical_batch(batch: AudioBatch) -> AudioBatch:
    if not isinstance(batch, AudioBatch):
        raise AudioError("INVALID_MANIFEST", "Audio batch request is invalid")
    try:
        payload = {"schema_version": "audio-batch.v1", **asdict(batch)}
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError):
        raise AudioError("INVALID_MANIFEST", "Audio batch request is invalid") from None
    return parse_manifest(encoded.encode("utf-8"))


def _safe_reference(source: str) -> str | None:
    if not isinstance(source, str) or not source or "\\" in source:
        return None
    parsed = urlsplit(source)
    path = PurePosixPath(source)
    if parsed.scheme or parsed.netloc or path.is_absolute() or PureWindowsPath(source).is_absolute():
        return None
    if any(part in {"", ".", ".."} for part in source.split("/")):
        return None
    return path.as_posix()


def _fingerprint(batch: AudioBatch, limits: AudioLimits, ffmpeg: str, ffprobe: str, hashes: dict[str, str | None]) -> str:
    request = asdict(batch)
    document = {
        "recipe_version": _RECIPE_VERSION,
        "request": request,
        "source_sha256": hashes,
        "limits": asdict(limits),
        "ffmpeg_version": ffmpeg,
        "ffprobe_version": ffprobe,
    }
    encoded = json.dumps(document, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _rejected_track(request: TrackRequest, error: AudioError, seconds: float) -> TrackResult:
    return TrackResult(
        track_id=request.track_id,
        status="rejected",
        source_relative=_safe_reference(request.source),
        source_sha256=None,
        trim=request.trim,
        requested_targets=request.targets,
        pre_measurement=None,
        post_measurement=None,
        output_format=request.output_format,
        output_relative_path=None,
        output_sha256=None,
        output_bytes=0,
        normalization_type=None,
        qa=QAResult(False, (error.code,), {error.code: False}),
        wall_seconds=max(0.0, seconds),
        cpu_seconds=None,
        measurement_status="unavailable",
        warnings=(),
        error=ErrorInfo(error.code, str(error), error.retryable),
    )


def _validate_result_cpu(results) -> tuple[float | None, str]:
    if not results or any(result.measurement_status != "measured" or result.cpu_seconds is None for result in results):
        return None, "unavailable"
    return sum(result.cpu_seconds for result in results), "measured"


def process_batch(
    batch: AudioBatch,
    input_root: Path,
    output_root: Path,
    limits: AudioLimits,
) -> AudioBatchResult:
    """Validate, render, QA, and publish a complete local batch result."""
    from .limits import validate_batch_capacity, validate_limits

    start = time.monotonic()
    normalized = _canonical_batch(batch)
    validate_limits(limits)
    source_root, output_root = validate_roots(Path(input_root), Path(output_root))
    toolchain = verified_toolchain()
    batch_dir = output_root / normalized.batch_id
    manifest_path = batch_dir / "result.json"
    if manifest_path.exists():
        raise AudioError("OUTPUT_EXISTS", "Result manifest already exists")
    try:
        batch_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise AudioError("OUTPUT_UNAVAILABLE", "Batch output directory cannot be created") from None

    validated = {}
    errors: dict[str, AudioError] = {}
    process_results: dict[str, list] = {}
    total_duration = 0.0
    predicted_batch_bytes = 0
    for request in normalized.tracks:
        track_start = time.monotonic()
        calls = []

        def tracked_runner(argv, timeout_seconds, output_limit_bytes):
            result = run_process(argv, timeout_seconds, output_limit_bytes)
            calls.append(result)
            return result

        try:
            item = validate_track(request, source_root, limits, tracked_runner)
            estimate = _estimate_output_bytes(item)
            if estimate > limits.max_output_bytes_per_track:
                raise AudioError("RESOURCE_LIMIT_EXCEEDED", "Rendered audio may exceed its size limit")
            validated[request.track_id] = item
            process_results[request.track_id] = calls
            total_duration += item.probe.duration_seconds
            predicted_batch_bytes += estimate
        except AudioError as error:
            errors[request.track_id] = error
            process_results[request.track_id] = calls
        except OSError:
            errors[request.track_id] = AudioError("SOURCE_NOT_FOUND", "Source audio file could not be inspected")
            process_results[request.track_id] = calls
        # Keep the preflight timing for rejected tracks even when no media process ran.
        process_results[f"wall:{request.track_id}"] = [max(0.0, time.monotonic() - track_start)]

    validate_batch_capacity(len(normalized.tracks), total_duration, limits)
    if predicted_batch_bytes > limits.max_output_bytes_per_batch:
        raise AudioError("RESOURCE_LIMIT_EXCEEDED", "Batch output may exceed its configured size limit")

    source_hashes = {
        request.track_id: validated[request.track_id].source_sha256 if request.track_id in validated else None
        for request in normalized.tracks
    }
    fingerprint = _fingerprint(
        normalized, limits, toolchain.ffmpeg_version, toolchain.ffprobe_version, source_hashes
    )
    artifact_dir = batch_dir / "artifacts"
    try:
        artifact_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise AudioError("OUTPUT_UNAVAILABLE", "Artifact directory cannot be created") from None

    track_results: list[TrackResult] = []
    for request in normalized.tracks:
        track_start = time.monotonic()
        if request.track_id in errors:
            duration = process_results.get(f"wall:{request.track_id}", [0.0])[0]
            track_results.append(_rejected_track(request, errors[request.track_id], duration))
            continue

        item = validated[request.track_id]
        calls = process_results[request.track_id]

        def tracked_runner(argv, timeout_seconds, output_limit_bytes):
            result = run_process(argv, timeout_seconds, output_limit_bytes)
            calls.append(result)
            return result

        extension = ".flac" if request.output_format == "flac" else ".wav"
        filename = f"{request.track_id}-{item.source_sha256[:12]}{extension}"
        final_output = artifact_dir / filename
        source_stage = None
        try:
            source_stage = Path(tempfile.mkdtemp(prefix=f".{request.track_id}-", dir=batch_dir))
            rendered = render_track(item, source_stage / filename, tracked_runner)
            publish_artifact(source_stage / filename, final_output)
            relative_output = PurePosixPath("artifacts", filename).as_posix()
            cpu_seconds, measurement_status = _validate_result_cpu(calls)
            track_results.append(
                replace(
                    rendered,
                    output_relative_path=relative_output,
                    wall_seconds=(
                        process_results.get(f"wall:{request.track_id}", [0.0])[0]
                        + max(0.0, time.monotonic() - track_start)
                    ),
                    cpu_seconds=cpu_seconds,
                    measurement_status=measurement_status,
                )
            )
        except AudioError as error:
            track_results.append(_rejected_track(request, error, time.monotonic() - track_start))
        except OSError:
            error = AudioError("OUTPUT_UNAVAILABLE", "Audio artifact could not be published")
            track_results.append(_rejected_track(request, error, time.monotonic() - track_start))
        finally:
            if source_stage is not None:
                shutil.rmtree(source_stage, ignore_errors=True)

    accepted = sum(track.status == "accepted" for track in track_results)
    rejected = len(track_results) - accepted
    status = "accepted" if rejected == 0 else "rejected" if accepted == 0 else "completed_with_errors"
    flat_processes = [result for values in process_results.values() for result in values if hasattr(result, "cpu_seconds")]
    cpu_seconds, measurement_status = _validate_result_cpu(flat_processes)
    result = AudioBatchResult(
        schema_version="audio-batch-result.v1",
        batch_id=normalized.batch_id,
        status=status,
        recipe_version=_RECIPE_VERSION,
        fingerprint=fingerprint,
        ffmpeg_version=toolchain.ffmpeg_version,
        ffprobe_version=toolchain.ffprobe_version,
        model_calls=0,
        accepted_tracks=accepted,
        rejected_tracks=rejected,
        wall_seconds=max(0.0, time.monotonic() - start),
        cpu_seconds=cpu_seconds,
        measurement_status=measurement_status,
        bytes_written=sum(track.output_bytes for track in track_results if track.status == "accepted"),
        monetary_cost=None,
        cost_status="unknown",
        replay=False,
        tracks=tuple(track_results),
    )
    write_manifest_atomic(manifest_path, serialize_result(result))
    verification = VerificationResult(True, None, 0, 0)
    if accepted:
        from .artifacts import verify_manifest

        verification = verify_manifest(manifest_path)
    if not verification.passed:
        raise AudioError(verification.error_code or "REPLAY_INTEGRITY_ERROR", "Published audio artifacts failed verification")
    return result
