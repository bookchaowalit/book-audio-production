"""Command-line interface for local deterministic audio production."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from .benchmark import run_benchmark
from .config import load_limits
from .engine import process_batch
from .errors import AudioError
from .manifest import parse_manifest
from .models import BatchStatus
from .report import serialize_result
from .artifacts import verify_manifest


def exit_code_for_status(status: BatchStatus, published: bool) -> int:
    """Map stable batch outcomes to shell exit statuses."""
    if not published:
        return 4
    return {"accepted": 0, "rejected": 2, "completed_with_errors": 3}.get(status, 4)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="book-audio", description="Process local audio batches with deterministic FFmpeg tools.")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="validate and process an audio batch manifest")
    run.add_argument("--manifest", required=True, type=Path)
    run.add_argument("--input-root", required=True, type=Path)
    run.add_argument("--output-root", required=True, type=Path)
    run.add_argument("--config", type=Path)
    run.add_argument("--json", action="store_true", help="print the versioned JSON result")

    verify = commands.add_parser("verify", help="verify a result manifest and its output hashes")
    verify.add_argument("manifest", type=Path)

    benchmark = commands.add_parser("benchmark", help="run an isolated synthetic local benchmark")
    benchmark.add_argument("--output", required=True, type=Path)
    benchmark.add_argument("--samples", type=int, default=20)
    return parser


def _json_line(payload: object, *, stream=None) -> None:
    print(json.dumps(payload, ensure_ascii=False, allow_nan=False, sort_keys=True), file=stream)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        try:
            args = _parser().parse_args(argv)
        except SystemExit as exit_signal:
            return int(exit_signal.code or 0)

        if args.command == "run":
            try:
                request = parse_manifest(args.manifest.read_bytes())
            except AudioError:
                raise
            except OSError:
                raise AudioError("INVALID_MANIFEST", "Audio batch manifest cannot be read") from None
            limits = load_limits(args.config)
            result = process_batch(request, args.input_root, args.output_root, limits)
            if args.json:
                _json_line(serialize_result(result))
            else:
                print(
                    f"{result.batch_id}: {result.status}; {result.accepted_tracks} accepted, "
                    f"{result.rejected_tracks} rejected; model_calls=0; monetary_cost=unknown"
                )
            published = (args.output_root / result.batch_id / "result.json").is_file()
            return exit_code_for_status(result.status, published)

        if args.command == "verify":
            result = verify_manifest(args.manifest)
            _json_line(asdict(result))
            return 0 if result.passed else 2

        if args.command == "benchmark":
            result = run_benchmark(args.output, args.samples, load_limits(None))
            _json_line(asdict(result))
            return 0

        raise AudioError("INVALID_COMMAND", "Unknown audio command")
    except AudioError as error:
        _json_line(
            {"error_code": error.code, "message": str(error), "retryable": error.retryable},
            stream=sys.stderr,
        )
        if error.code in {"INVALID_MANIFEST", "UNSUPPORTED_SCHEMA", "INVALID_CONFIG", "INVALID_LIMITS"}:
            return 2
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
