from pathlib import Path

import pytest

from book_audio_production.benchmark import run_benchmark
from book_audio_production.errors import AudioError
from book_audio_production.models import AudioLimits


def test_benchmark_reports_real_batch_replay_and_failure_counters(tmp_path: Path) -> None:
    result = run_benchmark(tmp_path / "benchmark", samples=2, limits=AudioLimits())

    assert result.accepted == 3
    assert result.rejected == 2
    assert result.partial_batches == 1
    assert result.qa_failures == 2
    assert result.replay_hits == 1
    assert result.model_calls == 0
    assert result.cost_status == "unknown" and result.monetary_cost is None
    assert result.bytes_written > 0


def test_benchmark_refuses_to_overwrite_nonempty_output_directory(tmp_path: Path) -> None:
    output = tmp_path / "already-used"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("preserve", encoding="utf-8")

    with pytest.raises(AudioError) as error:
        run_benchmark(output, samples=2, limits=AudioLimits())

    assert error.value.code == "OUTPUT_EXISTS"
    assert sentinel.read_text(encoding="utf-8") == "preserve"
