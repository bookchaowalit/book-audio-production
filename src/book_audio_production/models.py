"""Shared immutable models for audio validation, processing, and reporting."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal, Mapping, Sequence

OutputFormat = Literal["flac", "wav_pcm24"]
BatchStatus = Literal["accepted", "rejected", "completed_with_errors"]
TrackStatus = Literal["accepted", "rejected"]
MeasurementStatus = Literal["measured", "unavailable"]
CommandRunner = Callable[[Sequence[str], float, int], "ProcessResult"]


@dataclass(frozen=True)
class AudioLimits:
    max_tracks: int = 20
    max_source_bytes: int = 2 * 1024**3
    max_track_seconds: int = 7200
    max_batch_seconds: int = 28800
    max_output_bytes_per_track: int = 8 * 1024**3
    max_output_bytes_per_batch: int = 40 * 1024**3
    track_deadline_seconds: int = 21600
    batch_deadline_seconds: int = 86400
    process_output_limit_bytes: int = 1024 * 1024


@dataclass(frozen=True)
class TrimRange:
    start_ms: int | None
    end_ms: int | None


@dataclass(frozen=True)
class LoudnessTargets:
    integrated_lufs: float
    true_peak_dbtp: float
    lra_lu: float | None


@dataclass(frozen=True)
class TrackRequest:
    track_id: str
    source: str
    trim: TrimRange | None
    targets: LoudnessTargets
    output_format: OutputFormat


@dataclass(frozen=True)
class AudioBatch:
    batch_id: str
    tracks: tuple[TrackRequest, ...]


@dataclass(frozen=True)
class ProbeInfo:
    codec_name: str
    channels: int
    sample_rate: int
    duration_seconds: float
    file_bytes: int


@dataclass(frozen=True)
class AudioMeasurement:
    integrated_lufs: float
    lra_lu: float | None
    sample_peak_dbfs: float
    true_peak_dbtp: float
    duration_seconds: float


@dataclass(frozen=True)
class LoudnessMeasurement:
    integrated_lufs: float
    lra_lu: float | None
    true_peak_dbtp: float
    threshold_lufs: float
    normalization_type: str


@dataclass(frozen=True)
class ValidatedTrack:
    request: TrackRequest
    source_path: Path
    source_sha256: str
    trim_start_sample: int
    trim_end_sample: int | None
    probe: ProbeInfo


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: bytes
    stderr: bytes
    elapsed_seconds: float
    cpu_seconds: float | None
    measurement_status: MeasurementStatus
    output_truncated: bool


@dataclass(frozen=True)
class ErrorInfo:
    code: str
    message: str
    retryable: bool


@dataclass(frozen=True)
class QAResult:
    passed: bool
    failures: tuple[str, ...]
    checks: Mapping[str, bool]


@dataclass(frozen=True)
class TrackResult:
    track_id: str
    status: TrackStatus
    source_relative: str | None
    source_sha256: str | None
    trim: TrimRange | None
    requested_targets: LoudnessTargets
    pre_measurement: AudioMeasurement | None
    post_measurement: AudioMeasurement | None
    output_format: OutputFormat
    output_relative_path: str | None
    output_sha256: str | None
    output_bytes: int
    normalization_type: str | None
    qa: QAResult
    wall_seconds: float
    cpu_seconds: float | None
    measurement_status: MeasurementStatus
    warnings: tuple[str, ...]
    error: ErrorInfo | None


@dataclass(frozen=True)
class AudioBatchResult:
    schema_version: Literal["audio-batch-result.v1"]
    batch_id: str
    status: BatchStatus
    recipe_version: str
    fingerprint: str
    ffmpeg_version: str | None
    ffprobe_version: str | None
    model_calls: Literal[0]
    accepted_tracks: int
    rejected_tracks: int
    wall_seconds: float
    cpu_seconds: float | None
    measurement_status: MeasurementStatus
    bytes_written: int
    monetary_cost: float | None
    cost_status: Literal["known", "unknown"]
    replay: bool
    tracks: tuple[TrackResult, ...]


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    error_code: str | None
    artifacts_checked: int
    bytes_checked: int


@dataclass(frozen=True)
class BenchmarkResult:
    accepted: int
    rejected: int
    partial_batches: int
    qa_failures: int
    replay_hits: int
    wall_seconds: float
    cpu_seconds: float | None
    bytes_written: int
    model_calls: Literal[0]
    monetary_cost: float | None
    cost_status: Literal["known", "unknown"]
