# Upgrade Plan

## Current state

Score: 7.5/10 (was 7/10 after pass 1, 6/10 before) — careful fail-closed
batch engine with good unit coverage, now installable as a wheel and linted in
CI; real-audio tests still only run on the Windows host with the pinned FFmpeg
9.0.1 build.

## Backlog

### P0

- Confirm the first GitHub Actions run is green.

### P1

- Add a CI job that downloads the pinned FFmpeg 9.0.1 build on
  `windows-latest` (checksum-verified) so the 32 real-audio tests run in CI.
- Widen Ruff one family at a time (next: `SIM`, `PT`, `RUF`) and add type
  annotations to `batch.py` (`_deadline_runner`, `_validate_result_cpu`) so
  strict mypy can be introduced.
- Decide with `book-production-platform` which repository owns audio
  (`audio_production` there duplicates this engine) and add a drift check like
  the platform's `scripts/graphics_fork_parity.py`.

### P2

- Add a `book-audio doctor` style command that reports the toolchain status
  and the exact mismatch instead of only the stable error code.

## Done in pass 1

- Fixed: on Linux/macOS, publishing a batch onto an existing directory either
  silently replaced an empty directory or retried and reported
  `OUTPUT_UNAVAILABLE` for a non-empty one; both now fail with
  `OUTPUT_EXISTS` without touching the existing output.
- Real-audio tests skip with the toolchain error code when the pinned build is
  absent (was 33 failures on Linux); added `verified_toolchain()` tests using
  fake executables (match, mismatch, failing probe, missing tool, timeouts).
- Added `.github/workflows/ci.yml` and README test/CI notes.

## Done in this pass (pass 2)

- Fixed: `probe.py` and `replay.py` read `toolchain.lock.json` via
  `Path(__file__).parents[2]`, so an installed wheel always failed with
  `TOOLCHAIN_LOCK_INVALID`. The lock now ships as package data
  (`src/book_audio_production/toolchain.lock.json`) and both use one loader,
  `toolchain_lock.pinned_versions()` (tests for valid and invalid content;
  verified by building a wheel and importing it from a clean venv; CI repeats
  that check).
- Added a Ruff config (`E`, `F`, `I`, `B`, `UP`, line length 140) and Ruff to
  the test extras and CI; fixed all findings, including the loop-variable
  closures in `batch.py` (B023), now a `_deadline_runner` factory.
