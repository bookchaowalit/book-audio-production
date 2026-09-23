# Local Audio Product Baseline

Recorded: 2026-09-24

## Repository

- Standalone product repository initialized locally on branch `main`.
- No remote is configured; no hosted repository or catalog entry is claimed.
- Product source, tests, fixtures, dependencies, and runtime output belong in this repository.
- The Solo Empire control-plane checkout contains unrelated pre-existing changes; they are outside this product repository.

## Local toolchain

- Python: `3.12.10`
- FFmpeg: `9.0.1-full_build-www.gyan.dev`
- FFprobe: `9.0.1-full_build-www.gyan.dev`
- Both media executables are available through `PATH`.

## Fixture boundary

- No user audio, credentials, or private payloads are used in fixtures.
- Acceptance audio will be generated synthetically and kept inside this repository.
- Monetary processing cost remains unknown without an approved local rate card.
