import subprocess
import threading
import time
from pathlib import Path

import pytest

from app.print_service.config import Settings
from app.print_service.services import conversion_service
from app.print_service.services.conversion_service import ConversionError, convert_docx_to_pdf, convert_entries


def test_convert_docx_reuses_existing_pdf(tmp_path, monkeypatch):
    job_dir = tmp_path / "job"
    input_dir = job_dir / "input"
    converted_dir = job_dir / "converted"
    input_dir.mkdir(parents=True)
    converted_dir.mkdir()
    (input_dir / "doc_000001.docx").write_bytes(b"docx")
    expected_pdf = converted_dir / "doc_000001.pdf"
    expected_pdf.write_bytes(b"%PDF cached")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("LibreOffice should not be called for cached PDF")

    monkeypatch.setattr("app.print_service.services.conversion_service.subprocess.run", fail_if_called)
    result = convert_docx_to_pdf(
        {"path": "input/doc_000001.docx"},
        job_dir,
        Settings(data_dir=tmp_path),
    )

    assert result == expected_pdf


def test_convert_docx_reports_libreoffice_output(tmp_path, monkeypatch):
    job_dir = tmp_path / "job"
    input_dir = job_dir / "input"
    input_dir.mkdir(parents=True)
    (input_dir / "doc_000001.docx").write_bytes(b"docx")

    monkeypatch.setattr(
        "app.print_service.services.conversion_service._libreoffice_binary",
        lambda: "libreoffice",
    )
    monkeypatch.setattr(
        "app.print_service.services.conversion_service.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0],
            returncode=81,
            stdout="stdout text",
            stderr="stderr text",
        ),
    )

    try:
        convert_docx_to_pdf(
            {"path": "input/doc_000001.docx", "original_name": "bad.docx"},
            job_dir,
            Settings(data_dir=tmp_path),
        )
    except ConversionError as exc:
        message = str(exc)
    else:
        raise AssertionError("ConversionError was not raised")

    assert "bad.docx" in message
    assert "код возврата: 81" in message
    assert "stdout text" in message
    assert "stderr text" in message


def test_convert_docx_retries_after_libreoffice_failure(tmp_path, monkeypatch):
    job_dir = tmp_path / "job"
    input_dir = job_dir / "input"
    input_dir.mkdir(parents=True)
    (input_dir / "doc_000001.docx").write_bytes(b"docx")
    calls = 0

    monkeypatch.setattr(
        "app.print_service.services.conversion_service._libreoffice_binary",
        lambda: "libreoffice",
    )

    def fake_run(command, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            output_dir = Path(command[command.index("--outdir") + 1])
            (output_dir / "doc_000001.pdf").write_bytes(b"%PDF generated")
            return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")
        return subprocess.CompletedProcess(args=command, returncode=81, stdout="", stderr="first fail")

    monkeypatch.setattr("app.print_service.services.conversion_service.subprocess.run", fake_run)

    result = convert_docx_to_pdf(
        {"path": "input/doc_000001.docx", "original_name": "retry.docx"},
        job_dir,
        Settings(data_dir=tmp_path),
    )

    assert calls == 2
    assert result == job_dir / "converted" / "doc_000001.pdf"


def _pdf_analysis(path: Path) -> dict:
    return {
        "path": str(path),
        "page_count": 1,
        "empty_pages": [],
        "pages": [
            {
                "index": 1,
                "width_mm": 210.0,
                "height_mm": 297.0,
                "size_label": "A4, книжная",
                "orientation": "книжная",
                "visible": True,
                "rotate": 0,
                "media_box": [0, 0, 595, 842],
                "crop_box": [0, 0, 595, 842],
            }
        ],
    }


@pytest.mark.asyncio
async def test_convert_entries_uses_configured_parallel_workers(tmp_path, monkeypatch):
    job_dir = tmp_path / "job"
    (job_dir / "input").mkdir(parents=True)
    active = 0
    peak = 0
    lock = threading.Lock()

    def fake_convert(doc, current_job_dir, _settings):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            time.sleep(0.05)
            output = current_job_dir / "converted" / f"{doc['id']}.pdf"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"%PDF")
            return output
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(conversion_service, "convert_docx_to_pdf", fake_convert)
    monkeypatch.setattr(conversion_service, "analyze_pdf", _pdf_analysis)
    documents = []
    entries = []
    for index in range(6):
        doc_id = f"doc_{index:06d}"
        path = job_dir / "input" / f"{doc_id}.docx"
        path.write_bytes(b"docx")
        documents.append({"id": doc_id, "path": f"input/{doc_id}.docx", "original_name": path.name})
        entries.append({"doc_id": doc_id, "warnings": []})

    await convert_entries(entries, documents, job_dir, Settings(data_dir=tmp_path, convert_workers=3))

    assert peak == 3


@pytest.mark.asyncio
async def test_convert_entries_converts_repeated_document_once(tmp_path, monkeypatch):
    job_dir = tmp_path / "job"
    (job_dir / "input").mkdir(parents=True)
    (job_dir / "input" / "doc_000001.docx").write_bytes(b"docx")
    calls = 0

    def fake_convert(doc, current_job_dir, _settings):
        nonlocal calls
        calls += 1
        output = current_job_dir / "converted" / "doc_000001.pdf"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"%PDF")
        return output

    monkeypatch.setattr(conversion_service, "convert_docx_to_pdf", fake_convert)
    monkeypatch.setattr(conversion_service, "analyze_pdf", _pdf_analysis)
    document = {"id": "doc_000001", "path": "input/doc_000001.docx", "original_name": "document.docx"}
    entries = [{"doc_id": document["id"], "warnings": []} for _ in range(3)]

    converted, paths = await convert_entries(
        entries,
        [document],
        job_dir,
        Settings(data_dir=tmp_path, convert_workers=3),
    )

    assert calls == 1
    assert len(converted) == 3
    assert len(paths) == 3
