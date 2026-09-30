# Upgrade Plan

## Current state

Score: 7/10 (was 6/10) — careful fail-closed batch engine with good unit
coverage; real-audio tests only run on the Windows host with the pinned
FFmpeg 9.0.1 build, and the package only works from a source checkout.

## Backlog

### P0

- Confirm the first GitHub Actions run is green.

### P1

- `probe.py` and `replay.py` read `toolchain.lock.json` from
  `Path(__file__).parents[2]`, which exists only in a source/editable install;
  a wheel install always fails with `TOOLCHAIN_LOCK_INVALID`. Ship the lock as
  package data (or allow an explicit path) and share one loader.
- Add a CI job that downloads the pinned FFmpeg 9.0.1 build on
  `windows-latest` (checksum-verified) so the 32 real-audio tests run in CI.
- Add Ruff (and a config) to the test extras; `ruff check --select E,F,I`
  currently reports ~300 findings, mostly unused imports and import order.

### P2

- Add a `book-audio doctor` style command that reports the toolchain status
  and the exact mismatch instead of only the stable error code.

## Done in this pass

- Fixed: on Linux/macOS, publishing a batch onto an existing directory either
  silently replaced an empty directory or retried and reported
  `OUTPUT_UNAVAILABLE` for a non-empty one; both now fail with
  `OUTPUT_EXISTS` without touching the existing output.
- Real-audio tests skip with the toolchain error code when the pinned build is
  absent (was 33 failures on Linux); added `verified_toolchain()` tests using
  fake executables (match, mismatch, failing probe, missing tool, timeouts).
- Added `.github/workflows/ci.yml` and README test/CI notes.
