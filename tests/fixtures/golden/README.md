# Audio review samples

The automated integration suite creates short sine and pink-noise files in a
temporary directory at runtime. It does not commit generated audio binaries.

The release's manual listening gate requires a consented speech sample and a
human comparison of its source and rendered output for boundary clicks,
channel count, duration, obvious damage, and speech clarity. Keep that sample
in a local temporary/input directory; do not add it to Git or telemetry.
