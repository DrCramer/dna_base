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
    assert "Выбрать файлы" in html
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
