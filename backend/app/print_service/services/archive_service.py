from __future__ import annotations

import posixpath
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from fastapi import UploadFile

from app.print_service.config import Settings


class UploadValidationError(ValueError):
    pass


DOCX_CONTENT_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/octet-stream",
    "application/zip",
    "",
}
ZIP_CONTENT_TYPES = {"application/zip", "application/x-zip-compressed", "application/octet-stream", ""}
TXT_CONTENT_TYPES = {"text/plain", "application/octet-stream", ""}


def _safe_original_name(name: str) -> str:
    return Path(name.replace("\\", "/")).name.strip() or "file"


def _extension(name: str) -> str:
    return Path(name).suffix.lower()


def _is_ignored_path(name: str) -> bool:
    path = PurePosixPath(name.replace("\\", "/"))
    parts = path.parts
    if not parts:
        return True
    if any(part == "__MACOSX" or part.startswith(".") for part in parts):
        return True
    return path.name.startswith("~$") or path.name == ""


def _validate_zip_member(info: zipfile.ZipInfo, settings: Settings) -> None:
    raw_name = info.filename.replace("\\", "/")
    if raw_name.startswith("/") or PurePosixPath(raw_name).is_absolute():
        raise UploadValidationError(f"ZIP содержит абсолютный путь: {raw_name}")
    normalized = posixpath.normpath(raw_name)
    if normalized.startswith("../") or normalized == ".." or "/../" in normalized:
        raise UploadValidationError(f"ZIP содержит небезопасный путь: {raw_name}")
    if len(PurePosixPath(normalized).parts) > settings.max_zip_depth:
        raise UploadValidationError(f"Слишком большая вложенность в ZIP: {raw_name}")
    file_type = (info.external_attr >> 16) & 0o170000
    if file_type == 0o120000:
        raise UploadValidationError(f"ZIP содержит символическую ссылку: {raw_name}")


async def _copy_upload_limited(upload: UploadFile, target: Path, settings: Settings) -> int:
    size = 0
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as handle:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > settings.max_single_file_bytes:
                raise UploadValidationError(
                    f"Файл {upload.filename} превышает лимит {settings.max_single_file_mb} МБ"
                )
            handle.write(chunk)
    return size


def _copy_docx_from_file(
    source: Path,
    documents: list[dict],
    original_name: str,
    job_dir: Path,
    settings: Settings,
) -> None:
    if len(documents) >= settings.max_files:
        raise UploadValidationError(f"Превышен лимит файлов: {settings.max_files}")
    safe_name = f"doc_{len(documents) + 1:06d}.docx"
    destination = job_dir / "input" / safe_name
    shutil.copyfile(source, destination)
    documents.append(
        {
            "id": safe_name.removesuffix(".docx"),
            "original_name": original_name,
            "safe_name": safe_name,
            "path": str(destination.relative_to(job_dir)),
            "size": destination.stat().st_size,
        }
    )


def _copy_docx_from_zip(
    zip_file: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    documents: list[dict],
    original_name: str,
    job_dir: Path,
    settings: Settings,
) -> int:
    if len(documents) >= settings.max_files:
        raise UploadValidationError(f"Превышен лимит файлов: {settings.max_files}")
    safe_name = f"doc_{len(documents) + 1:06d}.docx"
    destination = job_dir / "input" / safe_name
    copied = 0
    with zip_file.open(info, "r") as source, destination.open("wb") as target:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            copied += len(chunk)
            if copied > settings.max_single_file_bytes:
                raise UploadValidationError(
                    f"Файл {original_name} превышает лимит {settings.max_single_file_mb} МБ"
                )
            target.write(chunk)
    documents.append(
        {
            "id": safe_name.removesuffix(".docx"),
            "original_name": original_name,
            "safe_name": safe_name,
            "path": str(destination.relative_to(job_dir)),
            "size": copied,
        }
    )
    return copied


def extract_zip(zip_path: Path, documents: list[dict], job_dir: Path, settings: Settings) -> int:
    accepted = 0
    unpacked_total = 0
    try:
        with zipfile.ZipFile(zip_path) as archive:
            for info in archive.infolist():
                _validate_zip_member(info, settings)
                if info.is_dir() or _is_ignored_path(info.filename):
                    continue
                if _extension(info.filename) != ".docx":
                    continue
                if info.file_size > settings.max_single_file_bytes:
                    raise UploadValidationError(
                        f"Файл {info.filename} превышает лимит {settings.max_single_file_mb} МБ"
                    )
                unpacked_total += info.file_size
                if unpacked_total > settings.max_unpacked_bytes:
                    raise UploadValidationError(
                        f"ZIP превышает лимит распаковки {settings.max_unpacked_mb} МБ"
                    )
                if info.compress_size and info.file_size / max(info.compress_size, 1) > 100:
                    raise UploadValidationError(f"Подозрительно высокая степень сжатия: {info.filename}")
                original = PurePosixPath(info.filename.replace("\\", "/")).name
                _copy_docx_from_zip(archive, info, documents, original, job_dir, settings)
                accepted += 1
    except zipfile.BadZipFile as exc:
        raise UploadValidationError(f"Повреждённый ZIP: {zip_path.name}") from exc
    return accepted


async def accept_uploads(files: list[UploadFile], job_dir: Path, settings: Settings) -> list[dict]:
    documents: list[dict] = []
    total_upload = 0
    for index, upload in enumerate(files, start=1):
        original = _safe_original_name(upload.filename or f"upload-{index}")
        ext = _extension(original)
        if ext not in {".docx", ".zip", ".txt"}:
            raise UploadValidationError(f"Неподдерживаемый тип файла: {original}")
        content_type = upload.content_type or ""
        if ext == ".docx" and content_type not in DOCX_CONTENT_TYPES:
            raise UploadValidationError(f"Неожиданный MIME-тип для DOCX: {content_type}")
        if ext == ".zip" and content_type not in ZIP_CONTENT_TYPES:
            raise UploadValidationError(f"Неожиданный MIME-тип для ZIP: {content_type}")
        if ext == ".txt" and content_type not in TXT_CONTENT_TYPES:
            raise UploadValidationError(f"Неожиданный MIME-тип для TXT: {content_type}")
        upload_path = job_dir / "extracted" / f"upload_{index:04d}{ext}"
        size = await _copy_upload_limited(upload, upload_path, settings)
        total_upload += size
        if total_upload > settings.max_upload_bytes:
            raise UploadValidationError(f"Суммарная загрузка превышает {settings.max_upload_mb} МБ")
        if ext == ".docx":
            if original.startswith("~$"):
                continue
            _copy_docx_from_file(upload_path, documents, original, job_dir, settings)
        elif ext == ".zip":
            extract_zip(upload_path, documents, job_dir, settings)
        else:
            continue
    return documents
