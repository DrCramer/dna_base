from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.print_service.config import settings


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_job() -> dict[str, Any]:
    settings.jobs_dir.mkdir(parents=True, exist_ok=True)
    job_id = str(uuid.uuid4())
    job_dir = get_job_dir(job_id)
    for name in ("input", "extracted", "converted", "stamped", "result"):
        (job_dir / name).mkdir(parents=True, exist_ok=True)
    state = {
        "id": job_id,
        "status": "uploaded",
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
        "documents": [],
        "registration_external_numbers": [],
        "registration_external_excel": None,
        "base_validation": None,
        "validation": None,
        "build": None,
        "stamping": None,
        "result_pdf": None,
        "report_csv": None,
        "error": None,
    }
    save_state(job_id, state)
    return state


def get_job_dir(job_id: str) -> Path:
    return settings.jobs_dir / job_id


def state_path(job_id: str) -> Path:
    return get_job_dir(job_id) / "status.json"


def report_json_path(job_id: str) -> Path:
    return get_job_dir(job_id) / "report.json"


def ensure_job_id(job_id: str) -> None:
    try:
        parsed = uuid.UUID(job_id)
    except ValueError as exc:
        raise FileNotFoundError("Задача не найдена") from exc
    if str(parsed) != job_id:
        raise FileNotFoundError("Задача не найдена")


def load_state(job_id: str) -> dict[str, Any]:
    ensure_job_id(job_id)
    path = state_path(job_id)
    if not path.exists():
        raise FileNotFoundError("Задача не найдена")
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(job_id: str, state: dict[str, Any]) -> None:
    state["updated_at"] = utc_now_iso()
    path = state_path(job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def save_report_json(job_id: str, report: dict[str, Any]) -> None:
    report_json_path(job_id).write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def delete_job(job_id: str) -> None:
    ensure_job_id(job_id)
    shutil.rmtree(get_job_dir(job_id), ignore_errors=True)
