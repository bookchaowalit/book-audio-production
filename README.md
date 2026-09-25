# Book Audio Production

A local, deterministic audio preparation tool for structured batches. It trims
audio by sample position, normalizes loudness with FFmpeg, checks the rendered
master, and writes a lossless FLAC or 24-bit PCM WAV result. The standard path
uses no LLM, transcription, or generative audio service; `model_calls` is always
zero. Monetary cost remains unknown until a local rate card is defined.

## Install and check the media tools

Use Python 3.12 and install the package in an isolated environment:

```powershell
python -m pip install -e ".[test]"
ffmpeg -version
ffprobe -version
book-audio --help
```

The executable versions must match [`toolchain.lock.json`](toolchain.lock.json).
The application does not download tools or access network media. FFprobe and
FFmpeg are run as local processes with bounded time and captured output.

## Create a batch manifest

Save a UTF-8 JSON file such as `batch.json`:

```json
{
  "schema_version": "audio-batch.v1",
  "batch_id": "episode-001",
  "tracks": [
    {
      "track_id": "intro",
      "source": "intro.wav",
      "trim": {"start_ms": 0, "end_ms": 30000},
      "targets": {
        "integrated_lufs": -16,
        "true_peak_dbtp": -1,
        "lra_lu": null
      },
      "output_format": "flac"
    }
  ]
}
```

`source` is relative to the input directory. Supported outputs are `flac` and
`wav_pcm24`. `trim` may be omitted; offsets are milliseconds converted to sample
positions at the source sample rate. Supported inputs have one mono or stereo
audio stream in a single-file `.aac`, `.aif`, `.aiff`, `.flac`, `.mka`, `.mkv`,
`.mp3`, `.oga`, `.ogg`, `.opus`, `.wav`, `.wave`, or `.webm` source. Playlist
formats and other containers are rejected before probing. Global tags, stream
tags, and chapters are removed from the output.

## Run, inspect, and replay

```powershell
book-audio run --manifest .\batch.json --input-root .\audio-in --output-root .\audio-out --json
book-audio verify .\audio-out\episode-001\result.json
```

Each batch writes `result.json`, a `result.json.sha256` integrity sidecar, and
accepted outputs under `artifacts/`. The manifest contains relative file paths,
input/output SHA-256 hashes, requested and measured loudness, sample/true peak,
duration, QA results, warnings, and process-time measurements. It contains no
raw media, absolute host paths, or FFmpeg command arguments. Verify checks the
manifest digest and every accepted output's size and hash.

The same batch ID, input bytes, settings, resource limits, recipe, and pinned
toolchain return the saved result without launching FFmpeg or FFprobe. Changing
any of them returns `REPLAY_CONFLICT`. Existing result files are never replaced.
The input manifest is limited to 1 MiB. One batch deadline covers source
fingerprinting, lock waiting, processing, artifact hashing, and verification.
Each attempt is built under `.staging/`; the complete verified batch directory
is published atomically. If a process is interrupted, its incomplete staging
attempt is discarded on the next run with the same batch ID. The tool does not
infer success from leftover files. A lock left by a crashed process is retained
for manual inspection and is not automatically removed.

Exit codes are `0` for accepted work or exact replay, `2` for invalid input or a
fully rejected batch, `3` for a partial batch, and `4` for a fatal error before
a result manifest is published.

## Resource and privacy boundaries

Default hard limits are 20 tracks, 2 GiB per source, 2 hours per track, 8 hours
of source audio per batch, 8 GiB estimated output per track, 40 GiB estimated
output per batch, 6 hours of processing per track, and 24 hours per batch.
`audio-production.toml.example` lists the local settings. A local config may
lower these limits, never raise them. The result reports CPU time only when the
local process monitor can measure it; otherwise it records `null` and marks the
measurement unavailable.

All media stays on the machine. Audio is not uploaded or sent to an AI provider.
Only local `file` and `pipe` protocols are allowed during processing. Synthetic
benchmark files and outputs also stay in the chosen benchmark directory.

## Synthetic benchmark

```powershell
book-audio benchmark --output .\benchmark-output --samples 20
```

The benchmark creates a local tone, processes up to 20 tracks, checks replay,
rejection, and partial-batch behavior, then reports time, bytes, QA failures,
`model_calls=0`, and unknown monetary cost. `qa_failures` counts only failed
render QA; rejected inputs are reported separately. The target directory must
be empty; existing files are preserved.

Latest local run on 2026-09-25 (`.runtime/audio-goal-20260925`): the 20-track
batch and follow-up partial-batch check reported 21 accepted outputs total
(20 full-batch outputs plus one partial success), 2 rejected tracks, 1 partial
batch, 1 replay hit, 0 QA failures, 633,297 bytes written, and
`model_calls=0`. Wall time was 14.171 s and measured CPU time was 5.547 s;
monetary cost remains `null`/unknown without a rate card.

## Audio review status

The tests generate tones and pink noise and measure numeric loudness, true peak,
trim accuracy, channels, sample rate, and lossless 24-bit output. Those checks
do not establish speech intelligibility. A local synthetic speech pair is
available for review:

- Source: `.runtime/manual-speech-qa-review/input/speech.wav`
- Master: `.runtime/manual-speech-qa-review/output/manual-speech-qa-review/artifacts/speech-review-5ef04100c658.flac`
- Result manifest: `.runtime/manual-speech-qa-review/output/manual-speech-qa-review/result.json`

The manifest reports 1 accepted track, 7/7 numeric QA checks, 10.192 s
duration, loudness from -21.4 to -18.0 LUFS, true peak from -2.81 to -1.0 dBTP,
and `model_calls=0`. A human source/output listening comparison is still
pending before calling the product pilot ready. No user speech recording is
committed or included in telemetry.
