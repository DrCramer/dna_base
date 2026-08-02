from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.auth import ensure_dev_users
from app.services.files import ensure_storage_dirs


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_storage_dirs()
    try:
        async with SessionLocal() as session:
            await ensure_dev_users(session)
    except Exception:
        # The database may not be migrated yet; Docker entrypoint runs Alembic first.
        pass
    yield


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


@app.get("/health")
async def health():
    return {"status": "ok"}
