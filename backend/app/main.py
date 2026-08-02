import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import api_router
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.print_service.config import settings as print_settings
from app.print_service.main import PACKAGE_DIR as print_package_dir
from app.print_service.main import api_router as print_api_router
from app.print_service.main import router as print_router
from app.print_service.services.cleanup_service import cleanup_loop as print_cleanup_loop
from app.services.auth import ensure_dev_users
from app.services.files import ensure_storage_dirs


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_storage_dirs()
    print_settings.jobs_dir.mkdir(parents=True, exist_ok=True)
    print_cleanup_task = asyncio.create_task(print_cleanup_loop(print_settings))
    try:
        async with SessionLocal() as session:
            await ensure_dev_users(session)
    except Exception:
        # The database may not be migrated yet; Docker entrypoint runs Alembic first.
        pass
    try:
        yield
    finally:
        print_cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await print_cleanup_task


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)
app.include_router(print_router)
app.include_router(print_api_router)
app.mount("/print/static", StaticFiles(directory=str(print_package_dir / "static")), name="print-static")


@app.get("/health")
async def health():
    return {"status": "ok"}
