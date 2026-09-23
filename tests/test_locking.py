from pathlib import Path

import pytest

from book_audio_production.errors import AudioError
from book_audio_production.locking import exclusive_lock


def test_existing_lock_is_not_removed_or_reused(tmp_path: Path) -> None:
    lock = tmp_path / "batch.lock"
    lock.write_text("owned-by-another-run", encoding="utf-8")

    with pytest.raises(AudioError) as error:
        with exclusive_lock(lock, wait_seconds=0):
            pytest.fail("a lock owned by another run must not be entered")

    assert error.value.code == "LOCK_BUSY"
    assert lock.read_text(encoding="utf-8") == "owned-by-another-run"


def test_lock_created_by_this_run_is_released(tmp_path: Path) -> None:
    lock = tmp_path / "batch.lock"

    with exclusive_lock(lock, wait_seconds=0):
        assert lock.is_file()

    assert not lock.exists()
