from __future__ import annotations

import asyncio
import shutil
from datetime import datetime, timedelta, timezone

from app.print_service.config import Settings


def cleanup_expired_jobs(settings: Settings) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.job_ttl_hours)
    removed = 0
    if not settings.jobs_dir.exists():
        return 0
    for job_dir in settings.jobs_dir.iterdir():
        if not job_dir.is_dir():
            continue
        status_path = job_dir / "status.json"
        try:
            if status_path.exists():
                created_at = datetime.fromisoformat(
                    status_path.read_text(encoding="utf-8").split('"created_at": "')[1].split('"')[0]
                )
            else:
                created_at = datetime.fromtimestamp(job_dir.stat().st_mtime, tz=timezone.utc)
        except Exception:
            created_at = datetime.fromtimestamp(job_dir.stat().st_mtime, tz=timezone.utc)
        if created_at < cutoff:
            shutil.rmtree(job_dir, ignore_errors=True)
            removed += 1
    return removed


async def cleanup_loop(settings: Settings) -> None:
    while True:
        cleanup_expired_jobs(settings)
        await asyncio.sleep(30 * 60)
