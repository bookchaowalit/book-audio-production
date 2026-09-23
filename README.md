# Book Audio Production

Local CLI for trimming and preparing batches of audio masters against explicit
loudness and true-peak targets. The standard pipeline uses FFprobe and FFmpeg;
it makes no LLM, transcription, or generative audio calls.

The current release is being built against the `audio-batch.v1` contract. It
accepts local files only, writes lossless outputs, records QA in a versioned
manifest, and reports monetary cost as unknown until a local rate card exists.

See `schemas/` for the input and result contracts. Product usage and runtime
limits will be documented here as the CLI implementation is completed.
