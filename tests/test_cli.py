import json
from pathlib import Path

from book_audio_production.cli import exit_code_for_status, main
from tests.audio_fixtures import create_synthetic_audio


def test_status_exit_codes_are_stable() -> None:
    assert exit_code_for_status("accepted", published=True) == 0
    assert exit_code_for_status("rejected", published=True) == 2
    assert exit_code_for_status("completed_with_errors", published=True) == 3
    assert exit_code_for_status("rejected", published=False) == 4


def test_main_help_is_successful(capsys) -> None:
    assert main(["--help"]) == 0
    assert "usage: book-audio" in capsys.readouterr().out


def test_cli_runs_local_manifest_and_verifies_result(tmp_path: Path, capsys) -> None:
    input_root = tmp_path / "input"
    output_root = tmp_path / "output"
    input_root.mkdir()
    create_synthetic_audio(input_root / "tone.wav", duration=0.8)
    manifest = tmp_path / "batch.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "audio-batch.v1",
                "batch_id": "cli-1",
                "tracks": [
                    {
                        "track_id": "tone",
                        "source": "tone.wav",
                        "targets": {"integrated_lufs": -18, "true_peak_dbtp": -1},
                        "output_format": "flac",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    run_code = main(
        ["run", "--manifest", str(manifest), "--input-root", str(input_root), "--output-root", str(output_root), "--json"]
    )
    run_output = capsys.readouterr().out
    result_manifest = output_root / "cli-1" / "result.json"
    verify_code = main(["verify", str(result_manifest)])
    verify_output = capsys.readouterr().out

    assert run_code == 0
    assert json.loads(run_output)["model_calls"] == 0
    assert str(input_root) not in run_output and str(output_root) not in run_output
    assert verify_code == 0
    assert json.loads(verify_output)["passed"] is True


def test_cli_rejects_malformed_manifest_without_echoing_path(tmp_path: Path, capsys) -> None:
    manifest = tmp_path / "private-manifest.json"
    manifest.write_text("not json", encoding="utf-8")

    code = main(["run", "--manifest", str(manifest), "--input-root", str(tmp_path), "--output-root", str(tmp_path / "out")])
    output = capsys.readouterr().err

    assert code == 2
    assert "INVALID_MANIFEST" in output
    assert str(tmp_path) not in output


def test_cli_rejects_oversized_manifest_with_stable_code(tmp_path: Path, capsys) -> None:
    manifest = tmp_path / "oversized.json"
    manifest.write_bytes(b" " * (1024 * 1024 + 1))

    code = main(
        ["run", "--manifest", str(manifest), "--input-root", str(tmp_path), "--output-root", str(tmp_path / "out")]
    )

    assert code == 2
    assert "RESOURCE_LIMIT_EXCEEDED" in capsys.readouterr().err
