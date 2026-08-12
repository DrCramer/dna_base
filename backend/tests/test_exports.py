from app.api.exports import _canonical_stage_type, _parse_int_tokens, _parse_text_tokens


def test_export_integer_tokens_are_deduplicated_and_invalid_values_are_ignored():
    assert _parse_int_tokens("12, 13\n12; x") == [12, 13]


def test_export_object_numbers_keep_input_order_and_repeat_suffixes():
    assert _parse_text_tokens("3303-1\n3303-1x, 3303-1*\n3303-1") == [
        "3303-1",
        "3303-1x",
        "3303-1*",
    ]


def test_export_stage_aliases_accept_ui_labels():
    assert _canonical_stage_type("Пробоподготовка") == "sample_prep"
    assert _canonical_stage_type("RealTime") == "realtime"
    assert _canonical_stage_type("Анализ") == "analysis"
    assert _canonical_stage_type("unknown") is None
