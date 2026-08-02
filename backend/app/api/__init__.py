from fastapi import APIRouter

from app.api import audit, auth, dashboard, employees, exports, files, imports, objects, parties, reference_items, reports, stage_table, work_sessions


api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(dashboard.router)
api_router.include_router(objects.router)
api_router.include_router(parties.router)
api_router.include_router(stage_table.router)
api_router.include_router(work_sessions.router)
api_router.include_router(employees.router)
api_router.include_router(reference_items.router)
api_router.include_router(reports.router)
api_router.include_router(imports.router)
api_router.include_router(exports.router)
api_router.include_router(files.router)
api_router.include_router(audit.router)
