from pathlib import Path

import pytest

from book_audio_production.config import load_limits
from book_audio_production.errors import AudioError


def test_load_limits_uses_defaults_when_config_is_absent() -> None:
    assert load_limits(None).max_tracks == 20


def test_load_limits_accepts_local_caps_below_hard_max(tmp_path: Path) -> None:
    config = tmp_path / "audio.toml"
    config.write_text("[limits]\nmax_tracks = 3\nmax_source_bytes = 4096\n", encoding="utf-8")

    limits = load_limits(config)

    assert limits.max_tracks == 3
    assert limits.max_source_bytes == 4096
    assert limits.max_track_seconds == 7200


@pytest.mark.parametrize(
    "text",
    [
        "[limits]\nmax_tracks = 21\n",
        "[limits]\nmax_tracks = 0\n",
        "[limits]\nmax_tracks = true\n",
        "[limits]\nunknown = 1\n",
        "[other]\nmax_tracks = 1\n",
        "not toml = [\n",
    ],
)
def test_rejects_invalid_config_values_and_shapes(tmp_path: Path, text: str) -> None:
    config = tmp_path / "audio.toml"
    config.write_text(text, encoding="utf-8")

    with pytest.raises(AudioError) as error:
        load_limits(config)

    assert error.value.code == "INVALID_CONFIG"


def test_rejects_missing_explicit_config(tmp_path: Path) -> None:
    with pytest.raises(AudioError) as error:
        load_limits(tmp_path / "missing.toml")

    assert error.value.code == "INVALID_CONFIG"
