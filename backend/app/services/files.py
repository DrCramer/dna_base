from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile, HTTPException

from app.core.config import get_settings


def ensure_storage_dirs() -> None:
    settings = get_settings()
    for name in ["uploads", "registry", "rt", "electrophoresis", "protocol", "exports"]:
        (settings.storage_dir / name).mkdir(parents=True, exist_ok=True)


async def save_upload(upload: UploadFile, category: str = "uploads", *, max_bytes: int | None = None) -> tuple[str, str, Path]:
    ensure_storage_dirs()
    settings = get_settings()
    original = Path(upload.filename or "upload.bin").name
    suffix = Path(original).suffix
    digest = sha256()
    upload_id = f"{uuid4().hex}{suffix}"
    category_dir = settings.storage_dir / category
    category_dir.mkdir(parents=True, exist_ok=True)
    path = category_dir / upload_id
    total = 0
    with path.open("wb") as fh:
        while chunk := await upload.read(1024 * 1024):
            total += len(chunk)
            if max_bytes is not None and total > max_bytes:
                fh.close()
                path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Файл превышает допустимый размер")
            digest.update(chunk)
            fh.write(chunk)
    meta = {
        "original_filename": original,
        "file_sha256": digest.hexdigest(),
        "upload_id": upload_id,
        "category": category,
    }
    path.with_suffix(path.suffix + ".meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return upload_id, digest.hexdigest(), path


def upload_path(upload_id: str, category: str = "uploads") -> Path:
    path = get_settings().storage_dir / category / Path(upload_id).name
    if not path.exists():
        raise FileNotFoundError(upload_id)
    return path


def upload_metadata(path: Path) -> dict[str, str]:
    meta_path = path.with_suffix(path.suffix + ".meta.json")
    if not meta_path.exists():
        return {"original_filename": path.name}
    return json.loads(meta_path.read_text(encoding="utf-8"))
