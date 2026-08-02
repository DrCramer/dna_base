from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.print_service.config import Settings
from app.print_service.services.pdf_service import (
    PdfValidationError,
    analyze_pdf,
    ensure_single_non_empty_page,
    reduce_to_single_page,
)


class ConversionError(RuntimeError):
    pass


CONVERSION_ATTEMPTS = 2
ERROR_OUTPUT_LIMIT = 1200


def _libreoffice_binary() -> str:
    binary = shutil.which("libreoffice") or shutil.which("soffice")
    if not binary:
        raise ConversionError("LibreOffice не найден в PATH")
    return binary


def _short_process_output(value: str | None) -> str:
    text = (value or "").strip()
    if len(text) <= ERROR_OUTPUT_LIMIT:
        return text
    return f"{text[:ERROR_OUTPUT_LIMIT]}..."


def _describe_libreoffice_failure(
    doc: dict[str, Any],
    command: list[str],
    completed: subprocess.CompletedProcess[str] | None = None,
    timeout: subprocess.TimeoutExpired | None = None,
) -> str:
    name = doc.get("original_name") or doc.get("safe_name") or doc.get("path") or "DOCX"
    details = [f"LibreOffice не смог конвертировать файл: {name}"]
    if timeout is not None:
        details.append("превышен тайм-аут конвертации")
        if timeout.stdout:
            details.append(f"stdout: {_short_process_output(str(timeout.stdout))}")
        if timeout.stderr:
            details.append(f"stderr: {_short_process_output(str(timeout.stderr))}")
    elif completed is not None:
        details.append(f"код возврата: {completed.returncode}")
        if completed.stdout:
            details.append(f"stdout: {_short_process_output(completed.stdout)}")
        if completed.stderr:
            details.append(f"stderr: {_short_process_output(completed.stderr)}")
    details.append(f"команда: {' '.join(command)}")
    return "; ".join(details)


def convert_docx_to_pdf(doc: dict[str, Any], job_dir: Path, settings: Settings) -> Path:
    input_path = job_dir / doc["path"]
    output_dir = job_dir / "converted"
    output_dir.mkdir(parents=True, exist_ok=True)
    expected_pdf = output_dir / f"{input_path.stem}.pdf"
    if expected_pdf.exists() and expected_pdf.stat().st_size > 0:
        return expected_pdf
    expected_pdf.unlink(missing_ok=True)
    last_error = "LibreOffice завершился с ошибкой при конвертации DOCX"
    for _attempt in range(CONVERSION_ATTEMPTS):
        profile_dir = tempfile.mkdtemp(prefix="lo-profile-")
        command = [
            _libreoffice_binary(),
            "--headless",
            "--nologo",
            "--nodefault",
            "--nolockcheck",
            "--nofirststartwizard",
            f"-env:UserInstallation=file://{profile_dir}",
            "--convert-to",
            "pdf:writer_pdf_Export",
            "--outdir",
            str(output_dir),
            str(input_path),
        ]
        env = {
            **os.environ,
            "HOME": profile_dir,
            "TMPDIR": tempfile.gettempdir(),
        }
        try:
            completed = subprocess.run(
                command,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=settings.conversion_timeout_seconds,
                env=env,
            )
            if not expected_pdf.exists():
                produced = list(output_dir.glob(f"{input_path.stem}*.pdf"))
                if produced:
                    produced[0].rename(expected_pdf)
            if expected_pdf.exists() and expected_pdf.stat().st_size > 0:
                return expected_pdf
            if completed.returncode != 0:
                last_error = _describe_libreoffice_failure(doc, command, completed=completed)
            else:
                last_error = (
                    f"LibreOffice завершился без ошибки, но не создал PDF для файла: "
                    f"{doc.get('original_name') or doc.get('path')}"
                )
        except subprocess.TimeoutExpired as exc:
            last_error = _describe_libreoffice_failure(doc, command, timeout=exc)
        finally:
            shutil.rmtree(profile_dir, ignore_errors=True)
    raise ConversionError(last_error)


async def convert_entries(
    entries: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    job_dir: Path,
    settings: Settings,
    progress_callback: Callable[[int, int, dict[str, Any]], Awaitable[None]] | None = None,
) -> tuple[list[dict[str, Any]], list[Path]]:
    by_id = {doc["id"]: doc for doc in documents}
    semaphore = asyncio.Semaphore(max(settings.convert_workers, 1))
    ordered_paths: list[Path | None] = [None] * len(entries)
    completed = 0
    completed_lock = asyncio.Lock()

    async def mark_completed(entry: dict[str, Any]) -> None:
        nonlocal completed
        async with completed_lock:
            completed += 1
            done = completed
        if progress_callback:
            await progress_callback(done, len(entries), entry)

    async def convert_one(index: int, entry: dict[str, Any]) -> None:
        async with semaphore:
            doc = by_id[entry["doc_id"]]
            try:
                input_path = job_dir / doc["path"]
                cached_pdf = job_dir / "converted" / f"{input_path.stem}.pdf"
                was_cached = cached_pdf.exists() and cached_pdf.stat().st_size > 0
                pdf_path = await asyncio.to_thread(convert_docx_to_pdf, doc, job_dir, settings)
                try:
                    analysis = await asyncio.to_thread(analyze_pdf, pdf_path)
                except PdfValidationError:
                    if not was_cached:
                        raise
                    pdf_path.unlink(missing_ok=True)
                    pdf_path = await asyncio.to_thread(convert_docx_to_pdf, doc, job_dir, settings)
                    analysis = await asyncio.to_thread(analyze_pdf, pdf_path)
                if analysis["page_count"] != 1 and settings.allow_drop_blank_extra_pages:
                    visible_pages = [
                        page["index"] for page in analysis["pages"] if page.get("visible")
                    ]
                    if len(visible_pages) == 1:
                        await asyncio.to_thread(reduce_to_single_page, pdf_path, visible_pages[0])
                        entry["warnings"].append(
                            "LibreOffice создал лишнюю пустую страницу; она удалена без масштабирования."
                        )
                        analysis = await asyncio.to_thread(analyze_pdf, pdf_path)
                ensure_single_non_empty_page(analysis, doc["original_name"])
                page = analysis["pages"][0]
                entry["conversion_status"] = "Готов"
                entry["pages"] = analysis["page_count"]
                entry["page_size"] = (
                    f"{page['width_mm']} × {page['height_mm']} мм · {page['size_label']}"
                )
                entry["pdf_path"] = str(pdf_path.relative_to(job_dir))
                entry["pdf_analysis"] = analysis
                ordered_paths[index] = pdf_path
            except (ConversionError, PdfValidationError, Exception) as exc:
                entry["status"] = "Ошибка"
                entry["blocking"] = True
                entry["conversion_status"] = "Ошибка"
                entry["error"] = str(exc)
            finally:
                await mark_completed(entry)

    await asyncio.gather(*(convert_one(index, entry) for index, entry in enumerate(entries)))
    failed = [entry for entry in entries if entry.get("blocking")]
    if failed:
        raise ConversionError("; ".join(entry["error"] for entry in failed[:3]))
    return entries, [path for path in ordered_paths if path is not None]
