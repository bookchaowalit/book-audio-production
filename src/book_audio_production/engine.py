"""Trim and normalize a validated track into a staged lossless audio file."""

from __future__ import annotations

import hashlib
import math
import os
import shutil
import tempfile
import time
from pathlib import Path

from .errors import AudioError
from .measurements import parse_ebur128_measurement, parse_loudnorm_measurement
from .models import (
    AudioMeasurement,
    CommandRunner,
    ErrorInfo,
    QAResult,
    TrackResult,
    ValidatedTrack,
)
from .probe import input_demuxer_for_path, probe_audio, verified_toolchain
from .qa import warnings_for_sample_peak

_RECIPE_VERSION = "audio-v1a.2"
_LOUDNESS_TOLERANCE_LU = 0.5
_TRUE_PEAK_TOLERANCE_DB = 0.1
_CONTAINER_ROUNDING_SECONDS = 0.002


def milliseconds_to_samples(milliseconds: int, sample_rate: int) -> int:
    """Convert a non-negative millisecond offset to a rounded sample index."""
    if (
        isinstance(milliseconds, bool)
        or not isinstance(milliseconds, int)
        or milliseconds < 0
        or isinstance(sample_rate, bool)
        or not isinstance(sample_rate, int)
        or sample_rate <= 0
    ):
        raise AudioError("INVALID_TRIM", "Trim offsets and sample rate must be non-negative integers")
    return round(milliseconds * sample_rate / 1000)


def _effective_samples(track: ValidatedTrack) -> int:
    total = round(track.probe.duration_seconds * track.probe.sample_rate)
    end = total if track.trim_end_sample is None else track.trim_end_sample
    return max(0, end - track.trim_start_sample)


def _estimate_output_bytes(track: ValidatedTrack) -> int:
    samples = _effective_samples(track)
    # PCM payload plus a conservative allowance for container and FLAC framing.
    return math.ceil(samples * track.probe.channels * 3 * 1.05 + 64 * 1024)


def _number(value: float) -> str:
    if not math.isfinite(value):
        raise AudioError("INVALID_TARGET", "Audio target must be finite")
    return format(value, ".8g")


def _trim_filter(track: ValidatedTrack) -> str:
    expression = f"atrim=start_sample={track.trim_start_sample}"
    if track.trim_end_sample is not None:
        expression += f":end_sample={track.trim_end_sample}"
    return f"{expression},asetpts=PTS-STARTPTS"


def _call(
    runner: CommandRunner,
    argv: list[str],
    track: ValidatedTrack,
    deadline: float,
):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise AudioError("PROCESS_TIMEOUT", "Audio track exceeded its time limit", retryable=True)
    result = runner(
        argv,
        min(remaining, float(track.limits.track_deadline_seconds)),
        min(track.limits.process_output_limit_bytes, 1024 * 1024),
    )
    if result.returncode != 0:
        raise AudioError("PROCESS_FAILED", "FFmpeg could not process the audio track", retryable=True)
    if result.output_truncated:
        raise AudioError("RESOURCE_LIMIT_EXCEEDED", "Media process output exceeded its size limit")
    return result


def _hash_file(path: Path, *, deadline: float | None = None) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as file:
            while True:
                if deadline is not None and time.monotonic() >= deadline:
                    raise AudioError("PROCESS_TIMEOUT", "Audio track exceeded its time limit", retryable=True)
                chunk = file.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
    except AudioError:
        raise
    except OSError:
        raise AudioError("RENDER_FAILED", "Rendered audio artifact cannot be read") from None
    return digest.hexdigest()


def _failure(checks: dict[str, bool]) -> tuple[str, ...]:
    return tuple(name for name, passed in checks.items() if not passed)


def _combine_pre_measurement(loudness, peaks: AudioMeasurement, expected_duration: float) -> AudioMeasurement:
    return AudioMeasurement(
        integrated_lufs=loudness.integrated_lufs,
        lra_lu=loudness.lra_lu if loudness.lra_lu is not None else peaks.lra_lu,
        sample_peak_dbfs=peaks.sample_peak_dbfs,
        true_peak_dbtp=loudness.true_peak_dbtp,
        duration_seconds=expected_duration,
    )


def render_track(
    track: ValidatedTrack,
    output_path: Path,
    runner: CommandRunner,
    *,
    toolchain=None,
    deadline: float | None = None,
) -> TrackResult:
    """Render one validated track to an unaccepted staging path and check it."""
    if output_path.exists():
        raise AudioError("OUTPUT_EXISTS", "Output file already exists")
    predicted_bytes = _estimate_output_bytes(track)
    if predicted_bytes > track.limits.max_output_bytes_per_track:
        raise AudioError("RESOURCE_LIMIT_EXCEEDED", "Rendered audio may exceed its size limit")
    start = time.monotonic()
    track_deadline = start + track.limits.track_deadline_seconds
    if deadline is not None:
        track_deadline = min(track_deadline, deadline)
    if start >= track_deadline:
        raise AudioError("PROCESS_TIMEOUT", "Audio track exceeded its time limit", retryable=True)
    try:
        source_bytes = track.source_path.stat().st_size
    except OSError:
        raise AudioError("SOURCE_NOT_FOUND", "Source audio file cannot be read") from None
    if source_bytes <= 0 or source_bytes > track.limits.max_source_bytes:
        raise AudioError("RESOURCE_LIMIT_EXCEEDED", "Source file is empty or exceeds its size limit")
    if _hash_file(track.source_path, deadline=track_deadline) != track.source_sha256:
        raise AudioError("SOURCE_CHANGED", "Source file changed after validation")

    toolchain = verified_toolchain() if toolchain is None else toolchain
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        staging_dir = Path(tempfile.mkdtemp(prefix=".audio-render-", dir=output_path.parent))
    except OSError:
        raise AudioError("OUTPUT_UNAVAILABLE", "Output staging directory cannot be created") from None
    staged_output = staging_dir / output_path.name
    target_lra = track.request.targets.lra_lu if track.request.targets.lra_lu is not None else 50.0
    trim_filter = _trim_filter(track)
    targets = track.request.targets
    input_args = [
        "-protocol_whitelist",
        "file,pipe",
        "-f",
        input_demuxer_for_path(track.source_path),
        "-i",
        str(track.source_path),
        "-map",
        "0:a:0",
    ]
    base = [toolchain.ffmpeg_path, "-nostdin", "-hide_banner", "-v", "info"]
    results = []
    try:
        analysis_filter = (
            f"{trim_filter},loudnorm=I={_number(targets.integrated_lufs)}:"
            f"TP={_number(targets.true_peak_dbtp)}:LRA={_number(target_lra)}:print_format=json"
        )
        loudness_pass = _call(
            runner,
            [*base, *input_args, "-af", analysis_filter, "-f", "null", os.devnull],
            track,
            track_deadline,
        )
        results.append(loudness_pass)
        analysis = parse_loudnorm_measurement(loudness_pass.stderr.decode("utf-8", errors="replace"))

        pre_peak_pass = _call(
            runner,
            [
                *base,
                "-n",
                *input_args,
                "-af",
                f"{trim_filter},ebur128=peak=true:framelog=quiet,astats=metadata=0:reset=0:measure_perchannel=none:measure_overall=Peak_level",
                "-f",
                "null",
                os.devnull,
            ],
            track,
            track_deadline,
        )
        results.append(pre_peak_pass)
        expected_samples = _effective_samples(track)
        expected_duration = expected_samples / track.probe.sample_rate
        pre_peaks = parse_ebur128_measurement(
            pre_peak_pass.stderr.decode("utf-8", errors="replace"), expected_duration
        )
        pre_measurement = _combine_pre_measurement(analysis, pre_peaks, expected_duration)

        measured_lra = analysis.lra_lu
        if measured_lra is None:
            if targets.lra_lu is not None:
                raise AudioError("MEASUREMENT_UNAVAILABLE", "Requested loudness range could not be measured")
            measured_lra = 50.0
        normalization_filter = (
            f"{trim_filter},loudnorm=I={_number(targets.integrated_lufs)}:"
            f"TP={_number(targets.true_peak_dbtp)}:LRA={_number(target_lra)}:"
            f"measured_I={_number(analysis.integrated_lufs)}:"
            f"measured_LRA={_number(measured_lra)}:"
            f"measured_TP={_number(analysis.true_peak_dbtp)}:"
            f"measured_thresh={_number(analysis.threshold_lufs)}:linear=true:print_format=json"
            ",asetnsamples=n=32768:p=0"
        )
        if track.request.output_format == "flac":
            encoding_args = ["-c:a", "flac", "-sample_fmt", "s32", "-bits_per_raw_sample", "24", "-compression_level", "5", "-f", "flac"]
        else:
            encoding_args = ["-c:a", "pcm_s24le", "-f", "wav"]
        render = _call(
            runner,
            [
                *base,
                *input_args,
                "-vn",
                "-sn",
                "-dn",
                "-af",
                normalization_filter,
                "-map_metadata",
                "-1",
                "-map_metadata:s",
                "-1",
                "-map_chapters",
                "-1",
                "-ar",
                str(track.probe.sample_rate),
                "-ac",
                str(track.probe.channels),
                *encoding_args,
                str(staged_output),
            ],
            track,
            track_deadline,
        )
        results.append(render)
        if not staged_output.is_file() or staged_output.stat().st_size <= 0:
            raise AudioError("RENDER_FAILED", "FFmpeg did not create a valid audio output")
        if staged_output.stat().st_size > track.limits.max_output_bytes_per_track:
            raise AudioError("RESOURCE_LIMIT_EXCEEDED", "Rendered audio exceeds its size limit")

        def probe_runner(argv, _timeout, _limit):
            result = _call(runner, list(argv), track, track_deadline)
            results.append(result)
            return result

        post_probe = probe_audio(staged_output, probe_runner)
        post_peak_pass = _call(
            runner,
            [
                toolchain.ffmpeg_path,
                "-nostdin",
                "-hide_banner",
                "-v",
                "info",
                "-protocol_whitelist",
                "file,pipe",
                "-i",
                str(staged_output),
                "-map",
                "0:a:0",
                "-af",
                "ebur128=peak=true:framelog=quiet,astats=metadata=0:reset=0:measure_perchannel=none:measure_overall=Peak_level",
                "-f",
                "null",
                os.devnull,
            ],
            track,
            track_deadline,
        )
        results.append(post_peak_pass)
        post_measurement = parse_ebur128_measurement(
            post_peak_pass.stderr.decode("utf-8", errors="replace"), post_probe.duration_seconds
        )
        second_pass_log = render.stderr.decode("utf-8", errors="replace")
        normalization = parse_loudnorm_measurement(second_pass_log)

        source_after_hash = _hash_file(track.source_path, deadline=track_deadline)
        if source_after_hash != track.source_sha256:
            raise AudioError("SOURCE_CHANGED", "Source file changed during audio processing")

        expected_duration_tolerance = 1 / track.probe.sample_rate + _CONTAINER_ROUNDING_SECONDS
        format_ok = (
            post_probe.codec_name == "flac"
            and post_probe.bits_per_raw_sample == 24
            if track.request.output_format == "flac"
            else post_probe.codec_name == "pcm_s24le"
        )
        checks = {
            "integrated_loudness_within_tolerance": abs(post_measurement.integrated_lufs - targets.integrated_lufs)
            <= _LOUDNESS_TOLERANCE_LU,
            "true_peak_under_ceiling": post_measurement.true_peak_dbtp
            <= targets.true_peak_dbtp + _TRUE_PEAK_TOLERANCE_DB,
            "duration_within_tolerance": abs(post_probe.duration_seconds - expected_duration)
            <= expected_duration_tolerance,
            "channels_preserved": post_probe.channels == track.probe.channels,
            "sample_rate_preserved": post_probe.sample_rate == track.probe.sample_rate,
            "lossless_24_bit_format": format_ok,
            "output_file_nonempty": staged_output.stat().st_size > 0,
        }
        failures = _failure(checks)
        qa = QAResult(passed=not failures, failures=failures, checks=checks)
        if not qa.passed:
            raise AudioError("QA_FAILED", "Rendered audio did not meet its quality checks")

        cpu_values = [result.cpu_seconds for result in results]
        measurement_status = "measured" if all(result.measurement_status == "measured" for result in results) and all(value is not None for value in cpu_values) else "unavailable"
        cpu_seconds = sum(value for value in cpu_values if value is not None) if measurement_status == "measured" else None
        output_hash = _hash_file(staged_output, deadline=track_deadline)
        relative_source = Path(track.request.source).as_posix()
        result = TrackResult(
            track_id=track.request.track_id,
            status="accepted",
            source_relative=relative_source,
            source_sha256=track.source_sha256,
            trim=track.request.trim,
            requested_targets=targets,
            pre_measurement=pre_measurement,
            post_measurement=post_measurement,
            output_format=track.request.output_format,
            output_relative_path=None,
            output_sha256=output_hash,
            output_bytes=staged_output.stat().st_size,
            normalization_type=normalization.normalization_type,
            qa=qa,
            wall_seconds=max(0.0, time.monotonic() - start),
            cpu_seconds=cpu_seconds,
            measurement_status=measurement_status,
            warnings=warnings_for_sample_peak(post_measurement.sample_peak_dbfs),
            error=None,
        )
        try:
            os.link(staged_output, output_path)
        except FileExistsError:
            raise AudioError("OUTPUT_EXISTS", "Output file already exists") from None
        except OSError:
            raise AudioError("OUTPUT_PUBLISH_FAILED", "Staged audio could not be published") from None
        return result
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)


def process_batch(batch, input_root, output_root, limits):
    """Run or replay one complete local batch under cross-process coordination."""
    from .replay import process_batch as _process_batch

    return _process_batch(batch, input_root, output_root, limits)
