import pytest

from book_audio_production.errors import AudioError
from book_audio_production.measurements import parse_ebur128_measurement, parse_loudnorm_measurement


def test_loudnorm_parser_ignores_surrounding_ffmpeg_logs() -> None:
    stderr = """[Parsed_loudnorm_0 @ 0x1] frame=12\nnoise\n{
      "input_i": "-16.25", "input_tp": "-0.80", "input_lra": "4.25",
      "input_thresh": "-28.00", "normalization_type": "linear"
    }\nend"""

    measurement = parse_loudnorm_measurement(stderr)

    assert measurement.integrated_lufs == -16.25
    assert measurement.lra_lu == 4.25
    assert measurement.true_peak_dbtp == -0.8
    assert measurement.threshold_lufs == -28
    assert measurement.normalization_type == "linear"


@pytest.mark.parametrize(
    "stderr",
    [
        "{\"input_i\":\"NaN\",\"input_tp\":\"-1\",\"input_thresh\":\"-20\"}",
        "{\"input_i\":\"-16\",\"input_tp\":\"-1\"}",
        "no measurement block",
    ],
)
def test_loudnorm_parser_rejects_non_finite_or_incomplete_data(stderr: str) -> None:
    with pytest.raises(AudioError) as error:
        parse_loudnorm_measurement(stderr)

    assert error.value.code == "MEASUREMENT_UNAVAILABLE"


def test_ebur128_parser_reads_final_summary_measurements() -> None:
    stderr = (
        "[Parsed_ebur128_0] frame log\nSummary:\nIntegrated loudness:\n  I: -16.2 LUFS\n  Threshold: -27.0 LUFS\n"
        "Loudness range:\n  LRA: 4.1 LU\nTrue peak:\n  Peak: -0.3 dBFS\n"
        "[Parsed_astats_1 @ 0x1] Overall\n[Parsed_astats_1 @ 0x1] Peak level dB: -0.5\n"
    )

    result = parse_ebur128_measurement(stderr, duration_seconds=1.5)

    assert result.integrated_lufs == -16.2
    assert result.lra_lu == 4.1
    assert result.sample_peak_dbfs == -0.5
    assert result.true_peak_dbtp == -0.3
    assert result.duration_seconds == 1.5


def test_ebur128_parser_rejects_missing_required_measurements() -> None:
    with pytest.raises(AudioError) as error:
        parse_ebur128_measurement("Summary: no values", duration_seconds=1)

    assert error.value.code == "MEASUREMENT_UNAVAILABLE"
