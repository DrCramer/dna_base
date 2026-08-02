import pytest
from fastapi import HTTPException

from app.print_service.models import AutoRegistrationPayload
from app.print_service.services.auto_registration_service import (
    _document_label,
    _external_numbers,
    _ordered_documents_from_external_numbers,
    build_registration_validation,
)


def test_document_label_extracts_external_number_from_docx_name():
    doc = {"original_name": "{№ трупа} - 3ПОСТ ген ии6525 ( РЦ СМЭ Минздрав РФ).docx"}

    assert _document_label(doc) == "ии6525"


def test_external_numbers_are_normalized_and_counted_against_documents():
    payload = AutoRegistrationPayload(
        start_party_no="193",
        case_year=2026,
        external_military_numbers=[" ИИ6525 ", "ИИ-6526"],
    )

    assert _external_numbers(payload, 2) == ["ии6525", "ии-6526"]


def test_external_numbers_count_mismatch_blocks_registration_preview():
    payload = AutoRegistrationPayload(
        start_party_no="193",
        case_year=2026,
        external_military_numbers=["ии6525"],
    )

    with pytest.raises(HTTPException) as exc:
        _external_numbers(payload, 2)

    assert exc.value.status_code == 400
    assert "Не совпадает количество DOCX и номеров № в в/ч №522" in exc.value.detail


def test_external_numbers_define_document_order_and_are_matched_like_classic_mode():
    documents = [
        {"id": "doc_1", "original_name": "Акт ии1002.docx"},
        {"id": "doc_2", "original_name": "Акт ии1001.docx"},
    ]

    ordered, external_by_doc_id, matching = _ordered_documents_from_external_numbers(
        documents,
        ["ии1001", "ии1002"],
    )

    assert matching["can_build"] is True
    assert [doc["id"] for doc in ordered] == ["doc_2", "doc_1"]
    assert external_by_doc_id == {"doc_2": "ии1001", "doc_1": "ии1002"}


def test_external_numbers_matching_reports_missing_documents():
    documents = [{"id": "doc_1", "original_name": "Акт ии1002.docx"}]

    ordered, _external_by_doc_id, matching = _ordered_documents_from_external_numbers(
        documents,
        ["ии9999"],
    )

    assert ordered == []
    assert matching["can_build"] is False
    assert matching["entries"][0]["status"] == "Не найден"


def test_registration_validation_uses_decree_numbers_as_stamp_labels():
    documents = [
        {"id": "doc_000001", "original_name": "Акт ии6525.docx"},
        {"id": "doc_000002", "original_name": "Акт ии9125.docx"},
    ]
    preview = {
        "case_year": 2026,
        "party_count": 1,
        "total_objects": 2,
        "stamp_field": "decree_no",
        "warnings": [],
        "rows": [
            {
                "party_no": "193",
                "doc_id": "doc_000001",
                "document_name": "Акт ии6525.docx",
                "external_military_no": "ии6525",
                "rcsme_reg_no": "6528-1",
                "decree_no": "6528-2026",
                "stamp_label": "6528-2026",
            },
            {
                "party_no": "193",
                "doc_id": "doc_000002",
                "document_name": "Акт ии9125.docx",
                "external_military_no": "ии9125",
                "rcsme_reg_no": "6529-1",
                "decree_no": "6529-2026",
                "stamp_label": "6529-2026",
            },
        ],
    }

    validation = build_registration_validation(documents, preview, {"style": {"corner": "top_right"}})

    assert validation["mode"] == "registration"
    assert validation["can_build"] is True
    assert [entry["stamp_label"] for entry in validation["entries"]] == ["6528-2026", "6529-2026"]
    assert validation["stamping"]["summary"]["labels"] == 2
    assert validation["stamping"]["config"]["enabled"] is True
    assert validation["stamping"]["config"]["source"] == "registration"
    assert validation["stamping"]["config"]["style"]["corner"] == "top_right"
