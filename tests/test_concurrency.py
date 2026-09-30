from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from book_audio_production.engine import process_batch
from book_audio_production.models import (
    AudioBatch,
    AudioLimits,
    LoudnessTargets,
    TrackRequest,
)
from tests.audio_fixtures import create_synthetic_audio
from tests.toolchain import requires_pinned_toolchain


def run_batch_in_child_process(arguments):
    return process_batch(*arguments)


@requires_pinned_toolchain
def test_two_same_key_processes_publish_once(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    output_root = tmp_path / "output"
    input_root.mkdir()
    create_synthetic_audio(input_root / "sample.wav", duration=0.8)
    batch = AudioBatch(
        "concurrent-1",
        (TrackRequest("sample", "sample.wav", None, LoudnessTargets(-16, -1, None), "flac"),),
    )
    arguments = (batch, input_root, output_root, AudioLimits())

    with ProcessPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run_batch_in_child_process, [arguments, arguments]))

    assert sum(not result.replay for result in results) == 1
    assert sum(result.replay for result in results) == 1
    artifact_dir = output_root / batch.batch_id / "artifacts"
    assert len(list(artifact_dir.glob("*.flac"))) == 1
