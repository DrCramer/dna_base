from pathlib import Path
from zipfile import ZipFile, ZipInfo

import pytest

from app.print_service.config import Settings
from app.print_service.services.archive_service import UploadValidationError, extract_zip


def make_settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path, max_files=10, max_single_file_mb=1, max_unpacked_mb=2, max_zip_depth=4)


def test_extract_regular_zip_with_subfolders(tmp_path):
    zip_path = tmp_path / "docs.zip"
    with ZipFile(zip_path, "w") as archive:
        archive.writestr("folder/Акт_ее5968.docx", b"docx")
        archive.writestr("__MACOSX/ignored.docx", b"docx")
        archive.writestr("folder/~$temp.docx", b"temp")
        archive.writestr("folder/readme.txt", b"no")
    job_dir = tmp_path / "job"
    (job_dir / "input").mkdir(parents=True)
    documents = []
    accepted = extract_zip(zip_path, documents, job_dir, make_settings(tmp_path))
    assert accepted == 1
    assert documents[0]["original_name"] == "Акт_ее5968.docx"
    assert (job_dir / documents[0]["path"]).exists()


@pytest.mark.parametrize("member", ["../evil.docx", "/abs.docx"])
def test_zip_slip_and_absolute_paths_are_rejected(tmp_path, member):
    zip_path = tmp_path / "bad.zip"
    with ZipFile(zip_path, "w") as archive:
        archive.writestr(member, b"docx")
    with pytest.raises(UploadValidationError):
        extract_zip(zip_path, [], tmp_path / "job", make_settings(tmp_path))


def test_zip_symlink_is_rejected(tmp_path):
    zip_path = tmp_path / "bad.zip"
    info = ZipInfo("link.docx")
    info.external_attr = (0o120777 << 16)
    with ZipFile(zip_path, "w") as archive:
        archive.writestr(info, b"target")
    with pytest.raises(UploadValidationError):
        extract_zip(zip_path, [], tmp_path / "job", make_settings(tmp_path))


def test_unpacked_limit_is_enforced(tmp_path):
    zip_path = tmp_path / "large.zip"
    settings = Settings(data_dir=tmp_path, max_single_file_mb=5, max_unpacked_mb=1)
    with ZipFile(zip_path, "w") as archive:
        archive.writestr("large.docx", b"x" * (2 * 1024 * 1024))
    with pytest.raises(UploadValidationError):
        extract_zip(zip_path, [], tmp_path / "job", settings)


def test_corrupt_zip_is_rejected(tmp_path):
    zip_path = tmp_path / "corrupt.zip"
    zip_path.write_bytes(b"not a zip")
    with pytest.raises(UploadValidationError):
        extract_zip(zip_path, [], tmp_path / "job", make_settings(tmp_path))
