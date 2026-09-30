"""verified_toolchain() against fake FFmpeg/FFprobe executables on PATH."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from book_audio_production import probe
from book_audio_production.errors import AudioError

pytestmark = pytest.mark.skipif(os.name == "nt", reason="fake tools are POSIX shell scripts")

LOCK = json.loads((Path(__file__).parents[1] / "src" / "book_audio_production" / "toolchain.lock.json").read_text(encoding="utf-8"))


def _fake_tool(directory: Path, name: str, first_line: str, exit_code: int = 0) -> None:
    script = directory / name
    script.write_text(f"#!/bin/sh\nprintf '%s\\n' '{first_line}'\nprintf 'configuration: fake\\n'\nexit {exit_code}\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)


@pytest.fixture
def fake_bin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "bin"
    directory.mkdir()
    monkeypatch.setenv("PATH", str(directory))
    monkeypatch.setattr(probe, "_TOOLCHAIN_CACHE", None)
    return directory


def test_matching_pinned_builds_are_accepted_and_cached(fake_bin: Path) -> None:
    _fake_tool(fake_bin, "ffmpeg", LOCK["ffmpeg_version"])
    _fake_tool(fake_bin, "ffprobe", LOCK["ffprobe_version"])

    toolchain = probe.verified_toolchain()

    assert toolchain.ffmpeg_version == LOCK["ffmpeg_version"]
    assert toolchain.ffprobe_version == LOCK["ffprobe_version"]
    assert Path(toolchain.ffmpeg_path).parent == fake_bin
    (fake_bin / "ffmpeg").unlink()
    assert probe.verified_toolchain() is toolchain


def test_a_different_build_is_rejected(fake_bin: Path) -> None:
    _fake_tool(fake_bin, "ffmpeg", "ffmpeg version 6.1.1-3ubuntu5 Copyright (c) 2000-2023 the FFmpeg developers")
    _fake_tool(fake_bin, "ffprobe", LOCK["ffprobe_version"])

    with pytest.raises(AudioError) as error:
        probe.verified_toolchain()

    assert error.value.code == "TOOL_VERSION_MISMATCH"
    assert probe._TOOLCHAIN_CACHE is None


def test_a_failing_version_probe_is_rejected(fake_bin: Path) -> None:
    _fake_tool(fake_bin, "ffmpeg", LOCK["ffmpeg_version"], exit_code=1)
    _fake_tool(fake_bin, "ffprobe", LOCK["ffprobe_version"])

    with pytest.raises(AudioError) as error:
        probe.verified_toolchain()

    assert error.value.code == "TOOL_VERSION_MISMATCH"


def test_a_missing_tool_is_reported(fake_bin: Path) -> None:
    _fake_tool(fake_bin, "ffmpeg", LOCK["ffmpeg_version"])

    with pytest.raises(AudioError) as error:
        probe.verified_toolchain()

    assert error.value.code == "TOOL_NOT_FOUND"


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), True])
def test_invalid_timeouts_fail_before_running_anything(fake_bin: Path, timeout: float) -> None:
    with pytest.raises(AudioError) as error:
        probe.verified_toolchain(timeout)

    assert error.value.code == "PROCESS_TIMEOUT"


def test_packaged_lock_is_read_through_package_resources() -> None:
    from book_audio_production.toolchain_lock import pinned_versions

    assert pinned_versions() == (LOCK["ffmpeg_version"], LOCK["ffprobe_version"])


@pytest.mark.parametrize(
    "content",
    ["not json", json.dumps({"schema_version": "other"}), json.dumps({"schema_version": "audio-toolchain.v1", "ffmpeg_version": 1})],
)
def test_invalid_lock_content_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, content: str) -> None:
    from book_audio_production import toolchain_lock

    (tmp_path / "toolchain.lock.json").write_text(content, encoding="utf-8")
    monkeypatch.setattr(toolchain_lock.resources, "files", lambda _package: tmp_path)

    with pytest.raises(AudioError) as error:
        toolchain_lock.pinned_versions()

    assert error.value.code == "TOOLCHAIN_LOCK_INVALID"
