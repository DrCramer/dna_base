from __future__ import annotations

import asyncio
import copy
import json
import re
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.api.deps import current_user, db_session, edit_user
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import User
from app.print_service.config import settings
from app.print_service.models import AutoRegistrationPayload, SequencePayload, StampingPayload
from app.print_service.services.archive_service import UploadValidationError, accept_uploads
from app.print_service.services.auto_registration_service import (
    apply_auto_registration,
    build_auto_registration_preview,
)
from app.print_service.services.cleanup_service import cleanup_loop
from app.print_service.services.conversion_service import ConversionError, convert_docx_to_pdf, convert_entries
from app.print_service.services.excel_service import ExcelValidationError, match_excel_groups
from app.print_service.services.job_store import (
    create_job,
    delete_job,
    get_job_dir,
    load_state,
    save_report_json,
    save_state,
)
from app.print_service.services.matching_service import match_documents
from app.print_service.services.pdf_service import PdfValidationError, merge_pdfs
from app.print_service.services.report_service import write_csv_report
from app.print_service.services.stamping_service import (
    StampingValidationError,
    apply_stamping_to_validation,
    copy_preview_with_stamp,
    default_stamp_config,
    normalize_stamp_config,
    parse_external_military_xlsx,
    parse_label_xlsx,
    render_preview_png,
    stamp_entries,
)


def _safe_download_stem(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-zА-Яа-яЁё._ -]+", "_", value).strip(" ._-")
    cleaned = re.sub(r"\s+", "_", cleaned)
    return (cleaned or fallback)[:80]


def _registration_pdf_name(entries: list[dict], fallback: str) -> str:
    if not entries:
        return f"{fallback}.pdf"
    party_no = str(entries[0].get("party_no") or fallback)
    first_no = str(entries[0].get("external_military_no") or entries[0].get("rcsme_reg_no") or "first")
    last_no = str(entries[-1].get("external_military_no") or entries[-1].get("rcsme_reg_no") or "last")
    stem = _safe_download_stem(f"{party_no}_{first_no}-{last_no}", fallback)
    return f"{stem}.pdf"


def _registration_entry_groups(entries: list[dict]) -> list[tuple[str, list[dict]]]:
    grouped: dict[str, list[dict]] = {}
    for entry in entries:
        party_no = str(entry.get("party_no") or "")
        grouped.setdefault(party_no, []).append(entry)
    return list(grouped.items())


def _reset_entry_for_build(entry: dict) -> None:
    if entry.get("doc_id"):
        entry["status"] = "Готов"
        entry["blocking"] = False
        entry["error"] = ""
        entry["conversion_status"] = "Ожидает"
        entry["pages"] = None
        entry["page_size"] = ""
        entry.pop("pdf_path", None)
        entry.pop("pdf_analysis", None)
        entry.pop("stamped_pdf_path", None)
        entry["stamp_applied"] = False


def _parse_stamping_json(raw: str | None) -> dict:
    if not raw:
        return default_stamp_config()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Не удалось прочитать настройки нанесения номеров") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Некорректные настройки нанесения номеров")
    return payload


def _has_excel_stamping_labels(config: dict) -> bool:
    groups = config.get("groups") if isinstance(config.get("groups"), dict) else {}
    for group_config in groups.values():
        if isinstance(group_config, dict):
            text = group_config.get("text") or ""
        else:
            text = str(group_config or "")
        if any(line.strip() for line in str(text).splitlines()):
            return True
    return False


def _parse_excel_stamping_json(raw: str | None) -> dict:
    config = _parse_stamping_json(raw)
    if config.get("enabled") and not _has_excel_stamping_labels(config):
        config = copy.deepcopy(config)
        config["enabled"] = False
    return config


async def _save_uploaded_xlsx(file: UploadFile, target: Path, error_message: str) -> None:
    size = 0
    with target.open("wb") as handle:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > settings.max_single_file_bytes:
                raise HTTPException(status_code=400, detail=error_message)
            handle.write(chunk)


def _registration_payload_with_job_numbers(state: dict, payload: AutoRegistrationPayload) -> AutoRegistrationPayload:
    if payload.external_military_numbers:
        return payload
    stored_numbers = state.get("registration_external_numbers") or []
    if not stored_numbers:
        return payload
    return payload.model_copy(update={"external_military_numbers": list(stored_numbers)})


PACKAGE_DIR = Path(__file__).resolve().parent
BUILD_TASKS: dict[str, asyncio.Task] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.jobs_dir.mkdir(parents=True, exist_ok=True)
    cleanup_task = asyncio.create_task(cleanup_loop(settings))
    try:
        yield
    finally:
        cleanup_task.cancel()


router = APIRouter()
api_router = APIRouter(prefix="/api/print", dependencies=[Depends(current_user)])
templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена")


def _load_state_or_404(job_id: str) -> dict:
    try:
        return load_state(job_id)
    except FileNotFoundError as exc:
        raise _not_found() from exc


def _validation_total(validation: dict) -> int:
    if validation.get("mode") == "excel":
        return sum(group["validation"]["total"] for group in validation.get("groups", []))
    return validation.get("total") or len(validation.get("entries") or [])


async def _render_stamping_preview(job_id: str, state: dict, validation: dict) -> FileResponse:
    stamp_config = normalize_stamp_config(validation.get("stamping", {}).get("config"))
    if not stamp_config.get("enabled"):
        raise HTTPException(status_code=400, detail="Нанесение номеров выключено")
    entries = (
        validation.get("groups", [])[0]["validation"]["entries"]
        if validation.get("mode") == "excel" and validation.get("groups")
        else validation.get("entries") or []
    )
    entry = next((item for item in entries if item.get("doc_id") and item.get("stamp_label")), None)
    if not entry:
        raise HTTPException(status_code=400, detail="Для примера нужен найденный документ и хотя бы одна метка")
    doc = next((item for item in state["documents"] if item["id"] == entry["doc_id"]), None)
    if not doc:
        raise HTTPException(status_code=400, detail="Документ для примера не найден")
    job_dir = get_job_dir(job_id)
    pdf_path = await asyncio.to_thread(convert_docx_to_pdf, doc, job_dir, settings)
    preview_pdf = job_dir / "stamped" / "preview.pdf"
    preview_png = job_dir / "stamped" / "preview.png"
    await asyncio.to_thread(
        copy_preview_with_stamp,
        pdf_path,
        preview_pdf,
        "" if entry.get("stamp_skip") else entry.get("stamp_label", ""),
        stamp_config["style"],
    )
    await asyncio.to_thread(render_preview_png, preview_pdf, preview_png)
    return FileResponse(preview_png, media_type="image/png")


def _recent_state() -> dict | None:
    if not settings.jobs_dir.exists():
        return None
    candidates = sorted(settings.jobs_dir.glob("*/status.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in candidates:
        try:
            return load_state(path.parent.name)
        except FileNotFoundError:
            continue
    return None


async def _save_progress(
    job_id: str,
    *,
    done: int,
    total: int,
    message: str,
    current_group: str | None = None,
    done_groups: int | None = None,
    total_groups: int | None = None,
) -> None:
    state = load_state(job_id)
    build = state.get("build") or {}
    build.update(
        {
            "progress": "converting",
            "done": done,
            "total": total,
            "percent": round((done / total) * 100, 1) if total else 0,
            "message": message,
        }
    )
    if current_group is not None:
        build["current_group"] = current_group
    if done_groups is not None:
        build["done_groups"] = done_groups
    if total_groups is not None:
        build["total_groups"] = total_groups
    state["build"] = build
    state["status"] = "converting"
    save_state(job_id, state)


@router.get("/print", dependencies=[Depends(current_user)])
async def index(request: Request, user: User = Depends(current_user)):
    embedded = request.query_params.get("embedded") == "1"
    can_edit = str(user.role) in {"admin", "user"}
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "embedded": embedded, "can_edit": can_edit},
    )


@api_router.get("/health")
async def health():
    return {"status": "ok"}


@api_router.get("/jobs/recent")
async def get_recent_job():
    state = _recent_state()
    if not state:
        return {}
    return state


@api_router.post("/jobs")
async def create_job_endpoint(request: Request):
    form = await request.form(max_files=settings.max_files + 10, max_fields=20)
    files = [
        value
        for key, value in form.multi_items()
        if key == "files" and hasattr(value, "filename") and hasattr(value, "read")
    ]
    if not files:
        raise HTTPException(status_code=400, detail="Загрузите хотя бы один DOCX или ZIP")
    xlsx_files = [file for file in files if str(file.filename or "").lower().endswith(".xlsx")]
    document_files = [file for file in files if file not in xlsx_files]
    if not document_files:
        raise HTTPException(status_code=400, detail="Загрузите хотя бы один DOCX или ZIP")
    state = create_job()
    job_dir = get_job_dir(state["id"])
    try:
        documents = await accept_uploads(document_files, job_dir, settings)
        if not documents:
            raise UploadValidationError("Не найдено ни одного DOCX для обработки")
        external_excel = None
        if xlsx_files:
            external_path = job_dir / "extracted" / "external-military.xlsx"
            await _save_uploaded_xlsx(
                xlsx_files[0],
                external_path,
                "Excel-файл с номерами № в в/ч №522 слишком большой",
            )
            external_excel = parse_external_military_xlsx(external_path)
            state["registration_external_numbers"] = external_excel["all_labels"]
            state["registration_external_excel"] = {
                "filename": xlsx_files[0].filename,
                "count": len(external_excel["all_labels"]),
                "column_count": external_excel["column_count"],
            }
        state["documents"] = documents
        state["status"] = "uploaded"
        save_state(state["id"], state)
        return {
            "id": state["id"],
            "status": state["status"],
            "accepted_documents": len(documents),
            "documents": documents,
            "registration_external_excel": external_excel,
        }
    except (UploadValidationError, StampingValidationError) as exc:
        delete_job(state["id"])
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@api_router.post("/jobs/{job_id}/validate")
async def validate_job(job_id: str, payload: SequencePayload):
    state = _load_state_or_404(job_id)
    if not state.get("documents"):
        raise HTTPException(status_code=400, detail="В задаче нет загруженных DOCX")
    base_validation = match_documents(payload.sequence, state["documents"])
    validation = copy.deepcopy(base_validation)
    try:
        validation = apply_stamping_to_validation(validation, payload.stamping)
    except StampingValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    state["base_validation"] = base_validation
    state["validation"] = validation
    state["stamping"] = validation.get("stamping")
    state["status"] = "validated"
    state["build"] = None
    state["result_pdf"] = None
    state["result_zip"] = None
    state["report_csv"] = None
    save_state(job_id, state)
    report = {"job_id": job_id, "validation": validation, "build": None}
    save_report_json(job_id, report)
    write_csv_report(validation["entries"], get_job_dir(job_id) / "result" / "report.csv")
    state["report_csv"] = "result/report.csv"
    save_state(job_id, state)
    return validation


@api_router.post("/jobs/{job_id}/validate/excel")
async def validate_excel_job(
    job_id: str,
    file: UploadFile = File(...),
    stamping_json: str | None = Form(default=None),
):
    state = _load_state_or_404(job_id)
    if not state.get("documents"):
        raise HTTPException(status_code=400, detail="В задаче нет загруженных DOCX")
    filename = file.filename or ""
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Загрузите Excel-файл .xlsx")
    job_dir = get_job_dir(job_id)
    excel_path = job_dir / "extracted" / "order.xlsx"
    size = 0
    with excel_path.open("wb") as handle:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > settings.max_single_file_bytes:
                raise HTTPException(status_code=400, detail="Excel-файл слишком большой")
            handle.write(chunk)
    try:
        base_validation = match_excel_groups(excel_path, state["documents"])
        validation = copy.deepcopy(base_validation)
        validation = apply_stamping_to_validation(validation, _parse_excel_stamping_json(stamping_json))
    except (ExcelValidationError, StampingValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    state["base_validation"] = base_validation
    state["validation"] = validation
    state["stamping"] = validation.get("stamping")
    state["status"] = "validated"
    state["build"] = None
    state["result_pdf"] = None
    state["result_zip"] = None
    state["report_csv"] = None
    save_state(job_id, state)
    flat_entries = [
        {**entry, "group": group["title"]}
        for group in validation["groups"]
        for entry in group["validation"]["entries"]
    ]
    write_csv_report(flat_entries, job_dir / "result" / "report.csv")
    state["report_csv"] = "result/report.csv"
    save_state(job_id, state)
    save_report_json(job_id, {"job_id": job_id, "validation": validation, "build": None})
    return validation


@api_router.post("/jobs/{job_id}/registration/preview")
async def preview_auto_registration(
    job_id: str,
    payload: AutoRegistrationPayload,
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(edit_user),
):
    state = _load_state_or_404(job_id)
    if not state.get("documents"):
        raise HTTPException(status_code=400, detail="В задаче нет загруженных DOCX")
    payload = _registration_payload_with_job_numbers(state, payload)
    return await build_auto_registration_preview(session, state["documents"], payload)


@api_router.post("/jobs/{job_id}/registration/apply")
async def apply_registration_to_job(
    job_id: str,
    payload: AutoRegistrationPayload,
    session: AsyncSession = Depends(db_session),
    user: User = Depends(edit_user),
):
    state = _load_state_or_404(job_id)
    if not state.get("documents"):
        raise HTTPException(status_code=400, detail="В задаче нет загруженных DOCX")
    payload = _registration_payload_with_job_numbers(state, payload)
    preview, validation = await apply_auto_registration(session, user, state["documents"], payload)
    state["registration"] = preview
    state["base_validation"] = copy.deepcopy(validation)
    state["validation"] = validation
    state["stamping"] = validation.get("stamping")
    state["status"] = "validated"
    state["build"] = None
    state["result_pdf"] = None
    state["result_zip"] = None
    state["report_csv"] = "result/report.csv"
    state["error"] = None
    save_state(job_id, state)
    job_dir = get_job_dir(job_id)
    write_csv_report(validation["entries"], job_dir / "result" / "report.csv")
    save_report_json(job_id, {"job_id": job_id, "registration": preview, "validation": validation, "build": None})
    return {"registration": preview, "validation": validation}


@api_router.post("/jobs/{job_id}/build")
async def build_job(job_id: str, wait: bool = False):
    state = _load_state_or_404(job_id)
    validation = state.get("validation")
    if not validation:
        raise HTTPException(status_code=400, detail="Сначала выполните проверку документов")
    if not validation.get("can_build"):
        raise HTTPException(status_code=400, detail="Сборка невозможна: есть блокирующие ошибки")

    existing_task = BUILD_TASKS.get(job_id)
    if state.get("status") == "converting" and existing_task and not existing_task.done():
        return state.get("build") or {"progress": "converting"}
    if wait:
        return await _run_build_job(job_id)

    total = _validation_total(validation)
    state["status"] = "converting"
    state["build"] = {
        "progress": "converting",
        "done": 0,
        "total": total,
        "percent": 0,
        "warnings": [],
        "error": None,
        "message": "Сборка запущена. Можно закрыть вкладку и вернуться позже.",
    }
    save_state(job_id, state)
    task = asyncio.create_task(_run_build_task(job_id))
    BUILD_TASKS[job_id] = task
    return state["build"]


async def _run_build_task(job_id: str) -> None:
    try:
        await _run_build_job(job_id)
    except HTTPException:
        pass
    except Exception as exc:
        try:
            state = load_state(job_id)
            state["status"] = "failed"
            state["error"] = str(exc)
            state["build"] = {
                **(state.get("build") or {}),
                "progress": "failed",
                "error": str(exc),
            }
            save_state(job_id, state)
        except Exception:
            pass
    finally:
        BUILD_TASKS.pop(job_id, None)


async def _run_build_job(job_id: str):
    state = _load_state_or_404(job_id)
    validation = state.get("validation")
    if not validation:
        raise HTTPException(status_code=400, detail="Сначала выполните проверку документов")
    if not validation.get("can_build"):
        raise HTTPException(status_code=400, detail="Сборка невозможна: есть блокирующие ошибки")

    job_dir = get_job_dir(job_id)
    state["status"] = "converting"
    state["build"] = {
        "progress": "converting",
        "done": 0,
        "total": _validation_total(validation),
        "percent": 0,
        "warnings": [],
        "error": None,
        "message": "Идёт конвертация DOCX в отдельные PDF.",
    }
    save_state(job_id, state)

    if validation.get("mode") == "excel":
        return await _build_excel_job(job_id, state)
    if validation.get("mode") == "registration":
        return await _build_registration_job(job_id, state)

    entries = copy.deepcopy(validation["entries"])
    for entry in entries:
        _reset_entry_for_build(entry)
    try:
        async def on_progress(done: int, total: int, entry: dict) -> None:
            if done == total or done % 5 == 0 or entry.get("blocking"):
                await _save_progress(
                    job_id,
                    done=done,
                    total=total,
                    message=f"Конвертация документов: {done} из {total}",
                )

        converted_entries, pdf_paths = await convert_entries(
            entries,
            state["documents"],
            job_dir,
            settings,
            progress_callback=on_progress,
        )
        size_keys = {
            (
                entry["pdf_analysis"]["pages"][0]["width_mm"],
                entry["pdf_analysis"]["pages"][0]["height_mm"],
                entry["pdf_analysis"]["pages"][0]["rotate"],
            )
            for entry in converted_entries
        }
        build_warnings: list[str] = []
        if len(size_keys) > 1:
            message = "В наборе присутствуют страницы разных размеров или ориентаций."
            if settings.require_same_page_size:
                raise PdfValidationError(message)
            build_warnings.append(message)
        stamped_paths, stamp_summary = stamp_entries(
            converted_entries,
            pdf_paths,
            job_dir,
            validation.get("stamping", {}).get("config"),
        )
        for page_index, entry in enumerate(converted_entries, start=1):
            entry["final_page"] = page_index
            entry["result_pdf_name"] = "result.pdf"
        output_pdf = job_dir / "result" / "result.pdf"
        merge = merge_pdfs(stamped_paths, output_pdf)
        report_csv = job_dir / "result" / "report.csv"
        write_csv_report(converted_entries, report_csv)
        state["validation"]["entries"] = converted_entries
        state["build"] = {
            "progress": "ready",
            "warnings": build_warnings,
            "merge": merge,
            "stamping": stamp_summary,
            "message": "PDF собран без масштабирования страниц.",
            "print_warning": "При печати выберите «Фактический размер» или «100%».",
        }
        state["result_pdf"] = "result/result.pdf"
        state["result_zip"] = None
        state["report_csv"] = "result/report.csv"
        state["status"] = "ready"
        state["error"] = None
        save_state(job_id, state)
        save_report_json(job_id, {"job_id": job_id, "validation": state["validation"], "build": state["build"]})
        return state["build"]
    except (ConversionError, PdfValidationError) as exc:
        state["status"] = "failed"
        state["build"] = {"progress": "failed", "warnings": [], "error": str(exc)}
        state["error"] = str(exc)
        state["validation"]["entries"] = entries
        write_csv_report(entries, job_dir / "result" / "report.csv")
        state["report_csv"] = "result/report.csv"
        save_state(job_id, state)
        save_report_json(job_id, {"job_id": job_id, "validation": state["validation"], "build": state["build"]})
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _build_registration_job(job_id: str, state: dict):
    job_dir = get_job_dir(job_id)
    validation = state["validation"]
    groups = _registration_entry_groups(validation["entries"])
    output_dir = job_dir / "result" / "party_pdfs"
    output_dir.mkdir(parents=True, exist_ok=True)
    total = len(validation["entries"])
    completed = 0
    result_pdfs: list[dict] = []
    converted_all: list[dict] = []
    build_warnings: list[str] = []

    try:
        for group_index, (party_no, source_entries) in enumerate(groups, start=1):
            entries = copy.deepcopy(source_entries)
            for entry in entries:
                _reset_entry_for_build(entry)

            await _save_progress(
                job_id,
                done=completed,
                total=total,
                message=f"Конвертация партии {party_no}",
                current_group=f"Партия {party_no}",
                done_groups=group_index - 1,
                total_groups=len(groups),
            )

            async def on_progress(done_in_group: int, group_total: int, entry: dict) -> None:
                if done_in_group == group_total or done_in_group % 5 == 0 or entry.get("blocking"):
                    await _save_progress(
                        job_id,
                        done=completed + done_in_group,
                        total=total,
                        message=f"Партия {party_no}: {done_in_group} из {group_total}",
                        current_group=f"Партия {party_no}",
                        done_groups=group_index - 1,
                        total_groups=len(groups),
                    )

            converted_entries, pdf_paths = await convert_entries(
                entries,
                state["documents"],
                job_dir,
                settings,
                progress_callback=on_progress,
            )
            size_keys = {
                (
                    entry["pdf_analysis"]["pages"][0]["width_mm"],
                    entry["pdf_analysis"]["pages"][0]["height_mm"],
                    entry["pdf_analysis"]["pages"][0]["rotate"],
                )
                for entry in converted_entries
            }
            if len(size_keys) > 1:
                message = f"Партия {party_no}: в PDF есть страницы разного размера или ориентации."
                if settings.require_same_page_size:
                    raise PdfValidationError(message)
                build_warnings.append(message)

            stamped_paths, stamp_summary = stamp_entries(
                converted_entries,
                pdf_paths,
                job_dir,
                validation.get("stamping", {}).get("config"),
            )
            download_name = _registration_pdf_name(converted_entries, f"party_{group_index:02d}")
            output_pdf = output_dir / download_name
            merge = merge_pdfs(stamped_paths, output_pdf)
            for page_index, entry in enumerate(converted_entries, start=1):
                entry["final_page"] = page_index
                entry["result_pdf_name"] = download_name

            result_pdfs.append(
                {
                    "title": f"Партия {party_no}",
                    "download_name": download_name,
                    "path": str(output_pdf.relative_to(job_dir)),
                    "page_count": merge["page_count"],
                    "size_bytes": merge["size_bytes"],
                    "stamping": stamp_summary,
                }
            )
            converted_all.extend(converted_entries)
            completed += len(converted_entries)

        zip_path = job_dir / "result" / "registration-parties.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for pdf in result_pdfs:
                archive.write(job_dir / pdf["path"], arcname=pdf["download_name"])

        state["validation"]["entries"] = converted_all
        state["build"] = {
            "progress": "ready",
            "mode": "registration",
            "warnings": build_warnings,
            "result_pdfs": result_pdfs,
            "stamping": {
                "enabled": bool(validation.get("stamping", {}).get("config", {}).get("enabled")),
                "applied": sum(pdf["stamping"]["applied"] for pdf in result_pdfs),
                "skipped": sum(pdf["stamping"]["skipped"] for pdf in result_pdfs),
            },
            "zip": {
                "path": str(zip_path.relative_to(job_dir)),
                "size_bytes": zip_path.stat().st_size,
                "pdf_count": len(result_pdfs),
                "page_count": sum(pdf["page_count"] for pdf in result_pdfs),
            },
            "message": "PDF собраны по партиям в порядке списка № в в/ч №522.",
            "print_warning": "При печати выберите «Фактический размер» или «100%».",
        }
        state["result_pdf"] = None
        state["result_zip"] = "result/registration-parties.zip"
        state["report_csv"] = None
        state["status"] = "ready"
        state["error"] = None
        save_state(job_id, state)
        save_report_json(job_id, {"job_id": job_id, "validation": state["validation"], "build": state["build"]})
        return state["build"]
    except (ConversionError, PdfValidationError) as exc:
        state["status"] = "failed"
        state["build"] = {"progress": "failed", "mode": "registration", "warnings": [], "error": str(exc)}
        state["error"] = str(exc)
        if converted_all:
            state["validation"]["entries"] = converted_all
            write_csv_report(converted_all, job_dir / "result" / "report.csv")
            state["report_csv"] = "result/report.csv"
        save_state(job_id, state)
        save_report_json(job_id, {"job_id": job_id, "validation": state["validation"], "build": state["build"]})
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _build_excel_job(job_id: str, state: dict):
    job_dir = get_job_dir(job_id)
    validation = state["validation"]
    build_warnings: list[str] = []
    output_dir = job_dir / "result" / "pdf_parts"
    output_dir.mkdir(parents=True, exist_ok=True)
    result_pdfs: list[dict] = []
    updated_groups: list[dict] = []
    all_entries: list[dict] = []
    total = _validation_total(validation)
    completed_before_group = 0
    total_groups = len(validation["groups"])

    try:
        for group_index, group in enumerate(validation["groups"], start=1):
            entries = copy.deepcopy(group["validation"]["entries"])
            for entry in entries:
                _reset_entry_for_build(entry)

            await _save_progress(
                job_id,
                done=completed_before_group,
                total=total,
                message=f"Конвертация столбца «{group['title']}»",
                current_group=group["title"],
                done_groups=group_index - 1,
                total_groups=total_groups,
            )

            async def on_progress(done_in_group: int, group_total: int, entry: dict) -> None:
                overall_done = completed_before_group + done_in_group
                if done_in_group == group_total or done_in_group % 5 == 0 or entry.get("blocking"):
                    await _save_progress(
                        job_id,
                        done=overall_done,
                        total=total,
                        message=(
                            f"Конвертация столбца «{group['title']}»: "
                            f"{done_in_group} из {group_total}"
                        ),
                        current_group=group["title"],
                        done_groups=group_index - 1,
                        total_groups=total_groups,
                    )

            converted_entries, pdf_paths = await convert_entries(
                entries,
                state["documents"],
                job_dir,
                settings,
                progress_callback=on_progress,
            )
            size_keys = {
                (
                    entry["pdf_analysis"]["pages"][0]["width_mm"],
                    entry["pdf_analysis"]["pages"][0]["height_mm"],
                    entry["pdf_analysis"]["pages"][0]["rotate"],
                )
                for entry in converted_entries
            }
            if len(size_keys) > 1:
                message = f"{group['title']}: в PDF присутствуют страницы разных размеров или ориентаций."
                if settings.require_same_page_size:
                    raise PdfValidationError(message)
                build_warnings.append(message)
            stamped_paths, stamp_summary = stamp_entries(
                converted_entries,
                pdf_paths,
                job_dir,
                validation.get("stamping", {}).get("config"),
            )
            stem = _safe_download_stem(group["title"], f"part_{group_index:02d}")
            output_pdf = output_dir / f"{group_index:02d}_{stem}.pdf"
            merge = merge_pdfs(stamped_paths, output_pdf)
            for page_index, entry in enumerate(converted_entries, start=1):
                entry["final_page"] = page_index
                entry["result_pdf_name"] = output_pdf.name
                entry["group_column"] = group.get("column", "")
                entry["stamp_column"] = group.get("stamping", {}).get("labels_column", "")
            result_pdfs.append(
                {
                    "title": group["title"],
                    "download_name": output_pdf.name,
                    "path": str(output_pdf.relative_to(job_dir)),
                    "page_count": merge["page_count"],
                    "size_bytes": merge["size_bytes"],
                    "stamping": stamp_summary,
                }
            )
            updated_group = copy.deepcopy(group)
            updated_group["validation"]["entries"] = converted_entries
            updated_group["result_pdf"] = str(output_pdf.relative_to(job_dir))
            updated_group["merge"] = merge
            updated_group["stamping"] = {**(group.get("stamping") or {}), "build": stamp_summary}
            updated_groups.append(updated_group)
            all_entries.extend({**entry, "group": group["title"]} for entry in converted_entries)
            completed_before_group += len(converted_entries)
            await _save_progress(
                job_id,
                done=completed_before_group,
                total=total,
                message=f"Собрано PDF: {group_index} из {total_groups}",
                current_group=group["title"],
                done_groups=group_index,
                total_groups=total_groups,
            )

        zip_path = job_dir / "result" / "result-parts.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for pdf in result_pdfs:
                archive.write(job_dir / pdf["path"], arcname=pdf["download_name"])
            report_path = job_dir / "result" / "report.csv"
            write_csv_report(all_entries, report_path)
            archive.write(report_path, arcname="report.csv")

        state["validation"]["groups"] = updated_groups
        state["build"] = {
            "progress": "ready",
            "mode": "excel",
            "warnings": build_warnings,
            "result_pdfs": result_pdfs,
            "stamping": {
                "enabled": bool(validation.get("stamping", {}).get("config", {}).get("enabled")),
                "applied": sum(pdf["stamping"]["applied"] for pdf in result_pdfs),
                "skipped": sum(pdf["stamping"]["skipped"] for pdf in result_pdfs),
            },
            "zip": {
                "path": str(zip_path.relative_to(job_dir)),
                "size_bytes": zip_path.stat().st_size,
                "pdf_count": len(result_pdfs),
                "page_count": sum(pdf["page_count"] for pdf in result_pdfs),
            },
            "message": "PDF собраны по столбцам Excel без масштабирования страниц.",
            "print_warning": "При печати выберите «Фактический размер» или «100%».",
        }
        state["result_pdf"] = None
        state["result_zip"] = "result/result-parts.zip"
        state["report_csv"] = "result/report.csv"
        state["status"] = "ready"
        state["error"] = None
        save_state(job_id, state)
        save_report_json(job_id, {"job_id": job_id, "validation": state["validation"], "build": state["build"]})
        return state["build"]
    except (ConversionError, PdfValidationError) as exc:
        state["status"] = "failed"
        state["build"] = {"progress": "failed", "mode": "excel", "warnings": [], "error": str(exc)}
        state["error"] = str(exc)
        if all_entries:
            write_csv_report(all_entries, job_dir / "result" / "report.csv")
            state["report_csv"] = "result/report.csv"
        save_state(job_id, state)
        save_report_json(job_id, {"job_id": job_id, "validation": state["validation"], "build": state["build"]})
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@api_router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    return _load_state_or_404(job_id)


@api_router.post("/jobs/{job_id}/stamping")
async def update_stamping(job_id: str, payload: StampingPayload):
    state = _load_state_or_404(job_id)
    base_validation = state.get("base_validation") or state.get("validation")
    if not base_validation:
        raise HTTPException(status_code=400, detail="Сначала выполните проверку документов")
    validation = copy.deepcopy(base_validation)
    try:
        validation = apply_stamping_to_validation(validation, payload.stamping)
    except StampingValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    state["validation"] = validation
    state["stamping"] = validation.get("stamping")
    state["status"] = "validated"
    state["build"] = None
    state["result_pdf"] = None
    state["result_zip"] = None
    save_state(job_id, state)
    if validation.get("mode") == "excel":
        flat_entries = [
            {**entry, "group": group["title"], "group_column": group.get("column", "")}
            for group in validation.get("groups", [])
            for entry in group["validation"]["entries"]
        ]
    else:
        flat_entries = validation.get("entries") or []
    write_csv_report(flat_entries, get_job_dir(job_id) / "result" / "report.csv")
    state["report_csv"] = "result/report.csv"
    save_state(job_id, state)
    save_report_json(job_id, {"job_id": job_id, "validation": validation, "build": None})
    return validation


@api_router.post("/jobs/{job_id}/stamping/xlsx")
async def parse_stamping_xlsx(
    job_id: str,
    file: UploadFile = File(...),
    column: str | None = Form(default=None),
    purpose: str = Form(default="stamp"),
):
    state = _load_state_or_404(job_id)
    filename = file.filename or ""
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Загрузите Excel-файл .xlsx")
    job_dir = get_job_dir(job_id)
    labels_path = job_dir / "extracted" / "stamp-labels.xlsx"
    await _save_uploaded_xlsx(file, labels_path, "Excel-файл с метками слишком большой")
    try:
        if purpose == "external_military":
            parsed = parse_external_military_xlsx(labels_path, column)
            state["registration_external_numbers"] = parsed["all_labels"]
            state["registration_external_excel"] = {
                "filename": filename,
                "count": len(parsed["all_labels"]),
                "column_count": parsed["column_count"],
            }
            save_state(job_id, state)
            return parsed
        return parse_label_xlsx(labels_path, column)
    except StampingValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@api_router.get("/jobs/{job_id}/stamping/preview")
async def get_stamping_preview(job_id: str):
    state = _load_state_or_404(job_id)
    validation = state.get("validation")
    if not validation:
        raise HTTPException(status_code=400, detail="Сначала выполните проверку документов")
    return await _render_stamping_preview(job_id, state, validation)


@api_router.post("/jobs/{job_id}/stamping/preview")
async def create_stamping_preview(job_id: str, payload: SequencePayload):
    state = _load_state_or_404(job_id)
    if not state.get("documents"):
        raise HTTPException(status_code=400, detail="В задаче нет загруженных DOCX")
    validation = match_documents(payload.sequence, state["documents"])
    try:
        validation = apply_stamping_to_validation(validation, payload.stamping)
    except StampingValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _render_stamping_preview(job_id, state, validation)


@api_router.get("/jobs/{job_id}/download/pdf")
async def download_pdf(job_id: str):
    state = _load_state_or_404(job_id)
    if not state.get("result_pdf"):
        raise HTTPException(status_code=404, detail="Итоговый PDF ещё не создан")
    path = get_job_dir(job_id) / state["result_pdf"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Итоговый PDF не найден")
    return FileResponse(path, media_type="application/pdf", filename=f"docx-print-order-{job_id}.pdf")


@api_router.get("/jobs/{job_id}/download/zip")
async def download_zip(job_id: str):
    state = _load_state_or_404(job_id)
    if not state.get("result_zip"):
        raise HTTPException(status_code=404, detail="ZIP с итоговыми PDF ещё не создан")
    path = get_job_dir(job_id) / state["result_zip"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="ZIP с итоговыми PDF не найден")
    return FileResponse(path, media_type="application/zip", filename=f"docx-print-order-{job_id}.zip")


@api_router.get("/jobs/{job_id}/download/part/{part_index}")
async def download_part_pdf(job_id: str, part_index: int):
    state = _load_state_or_404(job_id)
    result_pdfs = (state.get("build") or {}).get("result_pdfs") or []
    if part_index < 1 or part_index > len(result_pdfs):
        raise HTTPException(status_code=404, detail="PDF не найден")
    pdf = result_pdfs[part_index - 1]
    path = get_job_dir(job_id) / pdf["path"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="PDF не найден")
    return FileResponse(path, media_type="application/pdf", filename=pdf["download_name"])


@api_router.get("/jobs/{job_id}/download/report.csv")
async def download_report(job_id: str):
    state = _load_state_or_404(job_id)
    if not state.get("report_csv"):
        raise HTTPException(status_code=404, detail="Отчёт ещё не создан")
    path = get_job_dir(job_id) / state["report_csv"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Отчёт не найден")
    return FileResponse(path, media_type="text/csv; charset=utf-8", filename=f"docx-print-order-{job_id}.csv")


@api_router.delete("/jobs/{job_id}")
async def delete_job_endpoint(job_id: str):
    _load_state_or_404(job_id)
    delete_job(job_id)
    return {"status": "deleted"}
