"""Pinned toolchain checks and safe FFprobe inspection."""

from __future__ import annotations

import json
import math
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from .errors import AudioError
from .models import CommandRunner, ProbeInfo
from .runner import run_process


_INPUT_DEMUXERS = {
    ".aac": "aac",
    ".aif": "aiff",
    ".aiff": "aiff",
    ".flac": "flac",
    ".mka": "matroska",
    ".mkv": "matroska",
    ".mp3": "mp3",
    ".oga": "ogg",
    ".ogg": "ogg",
    ".opus": "ogg",
    ".wav": "wav",
    ".wave": "wav",
    ".webm": "matroska",
}


def input_demuxer_for_path(source: Path) -> str:
    """Select only single-file audio demuxers that do not follow playlists."""
    demuxer = _INPUT_DEMUXERS.get(Path(source).suffix.lower())
    if demuxer is None:
        raise AudioError("UNSUPPORTED_FORMAT", "Source audio format is not supported")
    return demuxer


@dataclass(frozen=True)
class Toolchain:
    ffmpeg_path: str
    ffprobe_path: str
    ffmpeg_version: str
    ffprobe_version: str


_TOOLCHAIN_CACHE: Toolchain | None = None


def verified_toolchain(timeout_seconds: float = 5.0) -> Toolchain:
    """Resolve and verify both local binaries against the committed version lock."""
    global _TOOLCHAIN_CACHE
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
    ):
        raise AudioError("PROCESS_TIMEOUT", "Audio batch exceeded its time limit", retryable=True)
    if _TOOLCHAIN_CACHE is not None:
        return _TOOLCHAIN_CACHE
    deadline = time.monotonic() + timeout_seconds
    lock_path = Path(__file__).parents[2] / "toolchain.lock.json"
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise AudioError("TOOLCHAIN_LOCK_INVALID", "Pinned media tool versions cannot be read") from None
    if not isinstance(lock, dict) or lock.get("schema_version") != "audio-toolchain.v1":
        raise AudioError("TOOLCHAIN_LOCK_INVALID", "Pinned media tool versions are invalid")

    paths: dict[str, str] = {}
    versions: dict[str, str] = {}
    for tool, version_field in (("ffmpeg", "ffmpeg_version"), ("ffprobe", "ffprobe_version")):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AudioError("PROCESS_TIMEOUT", "Audio batch exceeded its time limit", retryable=True)
        executable = shutil.which(tool)
        if executable is None:
            raise AudioError("TOOL_NOT_FOUND", "Required media tool is not available")
        result = run_process([executable, "-version"], remaining, 64 * 1024)
        first_line = result.stdout.decode("utf-8", errors="replace").splitlines()
        expected = lock.get(version_field)
        if result.returncode != 0 or result.output_truncated or not first_line or first_line[0] != expected:
            raise AudioError("TOOL_VERSION_MISMATCH", "Installed media tool does not match the pinned build")
        paths[tool] = executable
        versions[tool] = first_line[0]

    _TOOLCHAIN_CACHE = Toolchain(paths["ffmpeg"], paths["ffprobe"], versions["ffmpeg"], versions["ffprobe"])
    return _TOOLCHAIN_CACHE


def probe_audio(source: Path, runner: CommandRunner, *, toolchain: Toolchain | None = None) -> ProbeInfo:
    """Read the single supported audio stream from a local source file."""
    toolchain = verified_toolchain() if toolchain is None else toolchain
    demuxer = input_demuxer_for_path(source)
    argv = [
        toolchain.ffprobe_path,
        "-v",
        "error",
        "-of",
        "json",
        "-show_entries",
        "format=duration:stream=codec_type,codec_name,channels,sample_rate,duration,bits_per_raw_sample",
        "-protocol_whitelist",
        "file,pipe",
        "-f",
        demuxer,
        "-i",
        str(source),
    ]
    result = runner(argv, 30, 64 * 1024)
    if result.returncode != 0:
        raise AudioError("PROCESS_FAILED", "FFprobe could not inspect the source audio")
    if result.output_truncated:
        raise AudioError("RESOURCE_LIMIT_EXCEEDED", "FFprobe output exceeded its size limit")
    try:
        payload = json.loads(result.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise AudioError("UNSUPPORTED_STREAM", "FFprobe returned invalid audio metadata") from None

    streams = payload.get("streams") if isinstance(payload, dict) else None
    if not isinstance(streams, list) or len(streams) != 1 or not isinstance(streams[0], dict):
        raise AudioError("UNSUPPORTED_STREAM", "Source must contain exactly one audio stream")
    stream = streams[0]
    if stream.get("codec_type") != "audio":
        raise AudioError("UNSUPPORTED_STREAM", "Source must contain exactly one audio stream")
    try:
        channels = int(stream["channels"])
        sample_rate = int(stream["sample_rate"])
        duration_value = stream.get("duration")
        if duration_value in (None, "N/A"):
            duration_value = payload.get("format", {}).get("duration")
        duration = float(duration_value)
        codec_name = stream["codec_name"]
        raw_bits = stream.get("bits_per_raw_sample")
        bits_per_raw_sample = int(raw_bits) if raw_bits not in (None, "N/A") else None
        file_bytes = source.stat().st_size
    except (AttributeError, KeyError, TypeError, ValueError, OSError):
        raise AudioError("UNSUPPORTED_STREAM", "Audio stream metadata is incomplete") from None
    if (
        not isinstance(codec_name, str)
        or not codec_name
        or isinstance(stream.get("channels"), bool)
        or isinstance(stream.get("sample_rate"), bool)
        or channels <= 0
        or sample_rate <= 0
        or not math.isfinite(duration)
        or duration <= 0
        or file_bytes <= 0
    ):
        raise AudioError("UNSUPPORTED_STREAM", "Audio stream metadata is invalid")
    return ProbeInfo(codec_name, channels, sample_rate, duration, file_bytes, bits_per_raw_sample)
