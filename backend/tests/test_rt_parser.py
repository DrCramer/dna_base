from app.parsers.rt import parse_rt_preview
from app.parsers.normalization import normalize_lab_sample


RT_FILE = "/home/drcramer/.codex/attachments/d72507f8-986a-4a95-b20a-3d2a76d050b1/25-06-26_1_data.xls"
ABS_QUANT_FILE = "/home/drcramer/.codex/attachments/df8712c0-f646-4539-8f72-0bfa28675ecf/21-05-2026_Abs Quant(Stage2_Step3).xlsx"
TRIO_FILE = "/home/drcramer/.codex/attachments/af4fd0f5-a150-4446-b1c7-a3bba2e8b150/21-06-26_2_data.xls"


def test_quantstudio_xls_preview_detects_expected_columns_and_samples():
    preview = parse_rt_preview(RT_FILE)

    assert preview.parser_type == "abi_quantstudio"
    assert "Sample Name" in preview.columns
    assert "Target Name" in preview.columns
    assert "Ct" in preview.columns
    assert "Quantity" in preview.columns
    assert "Degradation Index" in preview.columns
    assert "3208-1" in preview.sample_names


def test_abs_quant_preview_aggregates_long_small_y():
    preview = parse_rt_preview(ABS_QUANT_FILE)

    assert preview.parser_type == "abs_quant"
    assert preview.quant_method == "Real Quant"
    sample = next(row for row in preview.aggregated_samples or [] if row["normalized_sample_name"] == "998-1")
    assert sample["small_quantity"] == 0.0011
    assert sample["long_quantity"] == 0.0019
    assert sample["y_quantity"] == 0.0032


def test_trio_preview_reads_run_date_and_targets():
    preview = parse_rt_preview(TRIO_FILE)

    assert preview.parser_type == "abi_quantstudio"
    assert preview.quant_method == "TRIO"
    assert str(preview.run_date) == "2026-06-21"
    sample = next(row for row in preview.aggregated_samples or [] if row["normalized_sample_name"] == "2807-1")
    assert sample["small_quantity"] == 0.0002


def test_repeat_suffix_sample_normalization():
    sample = normalize_lab_sample("1201-1x")

    assert sample.normalized == "1201-1x"
    assert sample.object_no == "1201-1"
    assert sample.repeat_suffix == "x"
