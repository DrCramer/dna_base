from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass
class Settings:
    data_dir: Path = Path(os.getenv("PRINT_DATA_DIR", "/app/data/print"))
    job_ttl_hours: int = _int_env("PRINT_JOB_TTL_HOURS", 2)
    max_upload_mb: int = _int_env("PRINT_MAX_UPLOAD_MB", 500)
    max_files: int = _int_env("PRINT_MAX_FILES", 2000)
    max_single_file_mb: int = _int_env("PRINT_MAX_SINGLE_FILE_MB", 50)
    max_unpacked_mb: int = _int_env("PRINT_MAX_UNPACKED_MB", 1500)
    max_zip_depth: int = _int_env("PRINT_MAX_ZIP_DEPTH", 8)
    convert_workers: int = _int_env("PRINT_CONVERT_WORKERS", 1)
    conversion_timeout_seconds: int = _int_env("PRINT_CONVERSION_TIMEOUT_SECONDS", 120)
    require_same_page_size: bool = os.getenv("PRINT_REQUIRE_SAME_PAGE_SIZE", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    allow_drop_blank_extra_pages: bool = os.getenv("PRINT_ALLOW_DROP_BLANK_EXTRA_PAGES", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    debug: bool = os.getenv("PRINT_DEBUG", "").lower() in {"1", "true", "yes", "on"}

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def max_single_file_bytes(self) -> int:
        return self.max_single_file_mb * 1024 * 1024

    @property
    def max_unpacked_bytes(self) -> int:
        return self.max_unpacked_mb * 1024 * 1024

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"


settings = Settings()
