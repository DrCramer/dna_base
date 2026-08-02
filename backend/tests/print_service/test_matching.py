from app.print_service.services.matching_service import contains_number_token, match_documents, normalize_text


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
    assert "Найдено несколько" in result["entries"][0]["error"]


def test_duplicate_numbers_block_build():
    result = match_documents("ее5968\nее5968", docs("Акт_ее5968.docx"))
    assert result["can_build"] is False
    assert "повторяется" in result["entries"][0]["error"]


def test_one_file_for_two_numbers_blocks_build():
    result = match_documents("ее5968\nее5968", docs("Документ_ее5968.docx"))
    assert result["can_build"] is False
    assert all(entry["blocking"] for entry in result["entries"])


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
