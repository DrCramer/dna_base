from app.print_service.services.matching_service import (
    canonical_match_key,
    contains_number_token,
    match_documents,
    normalize_text,
)


def docs(*names):
    return [
        {"id": f"doc_{index}", "original_name": name, "path": f"input/doc_{index}.docx"}
        for index, name in enumerate(names, start=1)
    ]


def test_exact_case_insensitive_match():
    result = match_documents("ЕЕ5968", docs("Заключение по материалу ее5968 от 2026 года.docx"))
    assert result["can_build"] is True
    assert result["entries"][0]["matched_file"].startswith("Заключение")


def test_number_in_middle_of_filename():
    result = match_documents("нн2832", docs("Скан нн2832 финал.docx"))
    assert result["entries"][0]["status"] == "Готов"


def test_short_number_does_not_match_longer_number_token():
    result = match_documents("нн388", docs("Акт_нн3888.docx", "Акт_нн388.docx"))
    assert result["can_build"] is True
    assert result["entries"][0]["matched_file"] == "Акт_нн388.docx"
    assert contains_number_token("акт_нн3888", "нн388") is False


def test_missing_file_blocks_build():
    result = match_documents("ее5968", docs("Документ_ее6032.docx"))
    assert result["can_build"] is False
    assert result["entries"][0]["status"] == "Не найден"


def test_multiple_files_for_one_number_blocks_build():
    result = match_documents("ее5968", docs("Акт_ее5968.docx", "Копия_ее5968.docx"))
    assert result["can_build"] is False
    assert result["entries"][0]["error"] == (
        "Для номера ее5968 найдено 2 документа. Нужно уточнить соответствие."
    )


def test_duplicate_numbers_require_the_same_document_count():
    result = match_documents("ее5968\nее5968", docs("Акт_ее5968.docx"))
    assert result["can_build"] is False
    assert result["entries"][0]["error"] == (
        "Для номера ее5968 указано 2 записи, найден только 1 документ."
    )


def test_one_file_for_two_numbers_blocks_build():
    result = match_documents("ее5968\nее5968", docs("Документ_ее5968.docx"))
    assert result["can_build"] is False
    assert all(entry["blocking"] for entry in result["entries"])


def test_slash_in_source_matches_underscore_in_filename_and_preserves_original():
    result = match_documents("ии6578/1", docs("Акт_ии6578_1.docx"))

    assert result["can_build"] is True
    assert canonical_match_key("ИИ6578/1") == "ии6578_1"
    assert result["entries"][0]["source_number_original"] == "ии6578/1"
    assert result["entries"][0]["source_number_canonical"] == "ии6578_1"
    assert result["entries"][0]["matched_docx"] == "Акт_ии6578_1.docx"


def test_slash_match_keeps_strict_token_boundary():
    result = match_documents("ии6578/1", docs("Акт_ии6578_10.docx", "Акт_ии6578_1.docx"))

    assert result["can_build"] is True
    assert result["entries"][0]["matched_docx"] == "Акт_ии6578_1.docx"


def test_duplicate_rows_are_stably_assigned_to_distinct_documents():
    result = match_documents(
        "аб2356\nаб2356",
        docs("72 аб2356.docx", "62 аб2356.docx"),
    )

    assert result["can_build"] is True
    assert [entry["matched_docx"] for entry in result["entries"]] == [
        "72 аб2356.docx",
        "62 аб2356.docx",
    ]
    assert [entry["occurrence_index"] for entry in result["entries"]] == [1, 2]
    assert len({entry["entry_id"] for entry in result["entries"]}) == 2


def test_cyrillic_latin_confusable_is_warning_not_match():
    result = match_documents("ее5968", docs("Document_ee5968.docx"))
    assert result["can_build"] is False
    assert result["entries"][0]["matched_file"] is None
    assert "похожие кириллические" in result["entries"][0]["warnings"][0]


def test_unicode_nfc_and_trimmed_blank_lines():
    decomposed = "е\u03015968"
    assert normalize_text(f" \ufeff{decomposed}\u00a0 ") == "е́5968"
    result = match_documents("\n ее5968 \n\n", docs("Акт_ее5968.docx"))
    assert result["total"] == 1
    assert result["can_build"] is True


def test_unused_documents_are_reported_as_warning():
    result = match_documents("ее5968", docs("Акт_ее5968.docx", "Лишний_ее6032.docx"))
    assert result["can_build"] is True
    assert len(result["unused_documents"]) == 1
