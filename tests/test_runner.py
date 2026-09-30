import sys

import pytest

from book_audio_production.errors import AudioError
from book_audio_production.runner import run_process


def test_process_timeout_is_stable_and_sanitized() -> None:
    command = [sys.executable, "-c", "import time; time.sleep(1)"]

    with pytest.raises(AudioError) as error:
        run_process(command, 0.01, 1024)

    assert error.value.code == "PROCESS_TIMEOUT"
    assert str(error.value) == "FFmpeg process exceeded its time limit"


def test_runner_preserves_argument_boundaries_without_shell() -> None:
    argument = "sound & echo must-not-run"
    command = [sys.executable, "-c", "import sys; print(sys.argv[1])", argument]

    result = run_process(command, 3, 4096)

    assert result.returncode == 0
    assert result.stdout.decode().strip() == argument


def test_runner_bounds_combined_stdout_and_stderr() -> None:
    script = "import sys; sys.stdout.write('o'*8192); sys.stderr.write('e'*8192)"
    result = run_process([sys.executable, "-c", script], 3, 512)

    assert len(result.stdout) + len(result.stderr) <= 512
    assert result.output_truncated is True


def test_runner_returns_nonzero_exit_without_command_details() -> None:
    result = run_process([sys.executable, "-c", "raise SystemExit(7)"], 3, 128)

    assert result.returncode == 7
    assert result.stderr == b""


def test_runner_rejects_missing_executable_without_leaking_argv() -> None:
    with pytest.raises(AudioError) as error:
        run_process(["private-missing-tool-name"], 1, 128)

    assert error.value.code == "TOOL_NOT_FOUND"
    assert "private-missing" not in str(error.value)


@pytest.mark.parametrize("argv", [[], "ffmpeg -version", ["ffmpeg", 1]])
def test_runner_rejects_invalid_argument_vectors(argv) -> None:
    with pytest.raises(AudioError) as error:
        run_process(argv, 3, 128)

    assert error.value.code == "INVALID_COMMAND"


@pytest.mark.parametrize(("timeout", "limit"), [(float("nan"), 128), (0, 128), (1, True)])
def test_runner_rejects_invalid_process_limits(timeout, limit) -> None:
    with pytest.raises(AudioError) as error:
        run_process([sys.executable, "-c", "pass"], timeout, limit)

    assert error.value.code == "INVALID_LIMITS"
