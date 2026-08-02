import subprocess
from pathlib import Path

from app.print_service.config import Settings
from app.print_service.services.conversion_service import ConversionError, convert_docx_to_pdf


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
