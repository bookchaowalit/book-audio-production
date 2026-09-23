"""Strict parsers for FFmpeg loudness and EBU R 128 measurements."""

from __future__ import annotations

import json
import math
import re
from typing import Any

from .errors import AudioError
from .models import AudioMeasurement, LoudnessMeasurement

_NUMBER = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?\Z")


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        text = str(value).strip()
        if not _NUMBER.fullmatch(text):
            return None
        number = float(text)
    except (ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _measurement_error() -> AudioError:
    return AudioError("MEASUREMENT_UNAVAILABLE", "Required audio measurements are unavailable")


def _json_blocks(stderr: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for match in re.finditer(r"\{[^{}]*\}", stderr, flags=re.DOTALL):
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            blocks.append(value)
    return blocks


def _first_number(payload: dict[str, Any], names: tuple[str, ...]) -> float | None:
    for name in names:
        if name in payload:
            value = _finite_number(payload[name])
            if value is not None:
                return value
    return None


def parse_loudnorm_measurement(stderr: str) -> LoudnessMeasurement:
    """Parse the last valid loudnorm JSON block, ignoring unrelated logs."""
    for payload in reversed(_json_blocks(stderr)):
        integrated = _first_number(payload, ("input_i", "output_i"))
        true_peak = _first_number(payload, ("input_tp", "output_tp"))
        threshold = _first_number(payload, ("input_thresh", "output_thresh"))
        lra = _first_number(payload, ("input_lra", "output_lra"))
        mode = payload.get("normalization_type", "unknown")
        if integrated is None or true_peak is None or threshold is None:
            continue
        if not isinstance(mode, str) or not mode:
            mode = "unknown"
        return LoudnessMeasurement(integrated, lra, true_peak, threshold, mode)
    raise _measurement_error()


def _last_section(text: str, heading: str) -> str:
    headings = r"Integrated loudness|Loudness range|Sample peak|True peak"
    sections = re.findall(
        rf"(?ims)^\s*{re.escape(heading)}:\s*$(.*?)(?=^\s*(?:{headings}):\s*$|\Z)",
        text,
    )
    return sections[-1] if sections else ""


def parse_ebur128_measurement(stderr: str, duration_seconds: float) -> AudioMeasurement:
    """Parse final EBU R 128 measurements from FFmpeg's diagnostic output."""
    text = re.sub(r"(?m)^\[[^\]\r\n]+\]\s*", "", stderr)
    if not math.isfinite(duration_seconds) or duration_seconds <= 0:
        raise _measurement_error()
    integrated_matches = re.findall(r"(?im)^\s*I:\s*([^\s]+)\s*LUFS\s*$", text)
    lra_matches = re.findall(r"(?im)^\s*LRA:\s*([^\s]+)\s*LU\s*$", text)

    def peak(section_name: str) -> float | None:
        section = _last_section(text, section_name)
        matches = re.findall(r"(?im)^\s*Peak:\s*([^\s]+)\s*dBFS\s*$", section)
        return _finite_number(matches[-1]) if matches else None

    integrated = _finite_number(integrated_matches[-1]) if integrated_matches else None
    lra = _finite_number(lra_matches[-1]) if lra_matches else None
    sample_peak = peak("Sample peak")
    true_peak = peak("True peak")
    if integrated is None or sample_peak is None or true_peak is None:
        raise _measurement_error()
    return AudioMeasurement(integrated, lra, sample_peak, true_peak, duration_seconds)
