from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.print_service import main


APP_JS = main.PACKAGE_DIR / "static" / "app.js"


def test_print_page_requires_dna_session():
    app = FastAPI()
    app.include_router(main.router)

    with TestClient(app) as client:
        response = client.get("/print")

    assert response.status_code == 401


def test_homepage_uses_redesigned_step_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(main.settings, "data_dir", tmp_path)
    app = FastAPI()
    app.include_router(main.router)
    app.dependency_overrides[main.current_user] = lambda: SimpleNamespace(id=1, username="viewer", role="viewer")
    with TestClient(app) as client:
        response = client.get("/print")

    assert response.status_code == 200
    html = response.text
    assert "Подготовим документы к печати" in html
    assert "data-step=\"documents\"" in html
    assert "data-step=\"order\"" in html
    assert "data-step=\"check\"" in html
    assert "data-step=\"result\"" in html
    assert "Добавить файлы" in html
    assert "Добавить папку" in html
    assert "webkitdirectory" in html
    assert 'id="txtInput" type="file" multiple' in html
    assert "Сортировать ↑" in html
    assert "Выбрать DOCX или ZIP" not in html
    assert "Предварительный просмотр" not in html


def test_frontend_script_has_no_preview_runtime():
    text = APP_JS.read_text(encoding="utf-8")
    assert "renderPreviews" not in text
    assert "preview_url" not in text


def test_frontend_keeps_stamp_settings_between_tasks():
    text = APP_JS.read_text(encoding="utf-8")
    assert "removeItem(STORAGE.stampUi)" not in text


def test_frontend_does_not_restore_stamp_enabled_between_tasks():
    text = APP_JS.read_text(encoding="utf-8")
    save_function = text.split("function saveStampUiSettings()", 1)[1].split("function restoreStampUiSettings()", 1)[0]
    assert "enabled:" not in save_function
    assert "els.stampEnabledInput.checked = false" in text


def test_frontend_does_not_send_empty_excel_stamp_labels_for_initial_validation():
    text = APP_JS.read_text(encoding="utf-8")
    assert "collectExcelValidationStampingConfig" in text
    assert "return { ...config, enabled: false }" in text


def test_registration_mode_shows_stamp_style_without_manual_label_options():
    text = APP_JS.read_text(encoding="utf-8")
    assert 'els.stampPanel.hidden = !hasMode;' in text
    assert 'els.stampRejectDuplicatesRow.hidden = isRegistration;' in text
    assert 'els.stampAllowSkipRow.hidden = isRegistration;' in text
    assert 'els.stampSourceActions.hidden = isRegistration;' in text
    assert 'els.stampTextBlock.hidden = isRegistration || state.mode === "excel";' in text
    assert 'state.mode === "registration" ? false : els.stampRejectDuplicatesInput.checked' in text
    assert 'state.mode === "registration" ? false : els.stampAllowSkipInput.checked' in text


def test_registration_mode_auto_uses_uploaded_excel_as_external_list():
    text = APP_JS.read_text(encoding="utf-8")
    assert 'if (mode === "registration") {' in text
    assert "loadSelectedExcelAsRegistrationExternalNumbers();" in text
    assert 'formData.append("purpose", "external_military");' in text
    assert '["0 номеров"]' in text
    assert "state.registrationExternalLoadedFileKey = null;" in text
    assert "if (state.registrationExternalLoadedFileKey === key) return;" not in text
    assert 'formData.append("files", file, queuedRelativePath(record) || file.name)' in text
    assert "job.registration_external_numbers?.length" in text


def test_registration_preview_uses_one_expandable_table_and_party_pdf_count():
    text = APP_JS.read_text(encoding="utf-8")

    assert 'data-registration-party=' in text
    assert 'registration-preview-table compact' not in text
    assert 'validation.registration?.party_count || 0' in text
    assert '["excel", "registration"].includes(validation.mode)' in text


def test_frontend_accumulates_folders_and_filters_folder_contents():
    text = APP_JS.read_text(encoding="utf-8")

    assert "state.pendingFiles.push(normalized)" in text
    assert 'name.endsWith(".docx")' in text
    assert 'file.name.startsWith("~$")' in text
    assert "droppedEntryRecords" in text
    assert "readDirectoryBatch" in text
    assert "pendingQueueLimitError" in text


def test_frontend_merges_multiple_txt_and_has_natural_sort():
    text = APP_JS.read_text(encoding="utf-8")

    assert 'contents.map(normalizeTxtBoundary).join("\\n")' in text
    assert "askListMergeChoice" in text
    assert "naturalSortParts" in text
    assert "compareNaturalValues" in text
    assert "SORT_CONFUSABLES" in text
    assert "state.sequenceBeforeSort" in text


def test_text_validation_waits_for_stamp_validation_when_enabled():
    text = APP_JS.read_text(encoding="utf-8")
    validate_function = text.split("async function validateTextJob()", 1)[1].split("async function validateExcelJob()", 1)[0]

    assert "collectTextValidationStampingConfig()" in validate_function
    assert "if (stampingEnabled)" in validate_function
    assert 'setStep("order")' in validate_function
    assert 'setStep("check")' in validate_function
    assert "if (data.can_build)" in text.split("async function applyStampingToCurrentValidation", 1)[1]
