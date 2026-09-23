"""Safe conversion of internal results to the public JSON contract."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import PurePosixPath, PureWindowsPath
from urllib.parse import urlsplit

from .errors import AudioError
from .models import AudioBatchResult


def _safe_relative_reference(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    parsed = urlsplit(value)
    path = PurePosixPath(value)
    return (
        not parsed.scheme
        and not parsed.netloc
        and not path.is_absolute()
        and not PureWindowsPath(value).is_absolute()
        and all(part not in {"", ".", ".."} for part in value.split("/"))
    )


def serialize_result(result: AudioBatchResult) -> dict[str, object]:
    """Return JSON-ready data without commands, host paths, or non-finite numbers."""
    if result.model_calls != 0 or result.monetary_cost is not None or result.cost_status != "unknown":
        raise AudioError("UNSAFE_REPORT", "Audio report cost and model-call fields are inconsistent")
    try:
        payload = asdict(result)
        for track in payload["tracks"]:
            for field in ("source_relative", "output_relative_path"):
                reference = track[field]
                if reference is not None and not _safe_relative_reference(reference):
                    raise AudioError("UNSAFE_REPORT", "Audio report contains an unsafe file reference")
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        decoded = json.loads(encoded)
    except AudioError:
        raise
    except (TypeError, ValueError, KeyError):
        raise AudioError("UNSAFE_REPORT", "Audio report contains invalid data") from None
    if not isinstance(decoded, dict):
        raise AudioError("UNSAFE_REPORT", "Audio report is invalid")
    return decoded
