from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, db_session
from app.models import ElectrophoresisControlFile, ElectrophoresisResultFile, User


router = APIRouter(prefix="/electrophoresis-files", tags=["electrophoresis-files"])


@router.get("/{file_id}")
async def electrophoresis_file(
    file_id: str,
    download: bool = Query(False),
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(current_user),
):
    record = None
    if file_id.startswith("control-"):
        try:
            control_id = int(file_id.removeprefix("control-"))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Файл фореза не найден") from exc
        record = await session.get(ElectrophoresisControlFile, control_id)
    else:
        try:
            result_id = int(file_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Файл фореза не найден") from exc
        record = await session.get(ElectrophoresisResultFile, result_id)
    if not record:
        raise HTTPException(status_code=404, detail="Файл фореза не найден")
    path = Path(record.file_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="PDF-файл отсутствует на диске")
    disposition = "attachment" if download else "inline"
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=record.filename,
        content_disposition_type=disposition,
    )
