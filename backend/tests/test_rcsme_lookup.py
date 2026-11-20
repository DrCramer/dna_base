from io import BytesIO

import httpx
from fastapi import FastAPI
from openpyxl import Workbook, load_workbook
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import current_user, db_session
from app.api.exports import router
from app.services.rcsme_lookup import HEADERS, parse_lookup_numbers


def make_workbook(*rows):
    workbook = Workbook()
    for row in rows:
        workbook.active.append(row)
    other_sheet = workbook.create_sheet("Unused")
    other_sheet.append(["999"])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_parse_xlsx_named_column_and_preserve_order():
    content = make_workbook((None, "№ партии", "№ рег РЦСМЭ"), (None, "8", "0012-1"), (None, "5", 14), (None, "8", "0012-1"))
    assert parse_lookup_numbers(filename="numbers.XLSX", content=content) == ({"0012-1": "0012-1", "14": "14"}, 1)


@pytest.mark.parametrize("filename,content", [
    ("numbers.csv", "№ партии;№ рег РЦСМЭ\r\n2;ии15\r\n1;001".encode("cp1251")),
    ("numbers.txt", "№ рег РЦСМЭ\nии15;001".encode("utf-8-sig")),
])
def test_parse_delimited_lists(filename, content):
    assert parse_lookup_numbers(filename=filename, content=content) == ({"ии15": "ии15", "001": "001"}, 0)


def test_reject_ambiguous_columns_and_oversized_lists():
    with pytest.raises(ValueError, match="несколько столбцов"):
        parse_lookup_numbers(filename="list.xlsx", content=make_workbook(("12",), ("14", "18")))
    with pytest.raises(ValueError, match="5000"):
        parse_lookup_numbers("12\n" * 5001)
    with pytest.raises(ValueError, match="прочитать"):
        parse_lookup_numbers(filename="invalid.xlsx", content=b"not a workbook")


@pytest.mark.asyncio
async def test_preview_and_download_use_registry_columns_and_year():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.execute(text("CREATE TABLE parties (id INTEGER, party_no TEXT)"))
            await connection.execute(text("CREATE TABLE objects (party_id INTEGER, party_no TEXT, rcsme_reg_no TEXT, external_military_no TEXT, case_year INTEGER)"))
            await connection.execute(text("INSERT INTO parties VALUES (1, '007')"))
            await connection.execute(text(
                "INSERT INTO objects VALUES "
                "(1, 'old no', '001-1', '0005', 2026), (NULL, '02', '001-2', NULL, 2026), "
                "(NULL, '06', '001-1', '88', 2025), (NULL, '09', '001', '66', 2026), "
                "(NULL, '07', 'ABC', '=1+1', 2026)"
            ))
        app = FastAPI()
        app.include_router(router)
        sessions = async_sessionmaker(engine)

        async def database():
            async with sessions() as session:
                yield session

        app.dependency_overrides[db_session] = database
        app.dependency_overrides[current_user] = lambda: object()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/exports/rcsme/preview", data={"case_year": 2026}, files={
                "file": ("list.csv", b"001-2\n001-1\nabc\nmissing\n001-2\n"),
            })
            assert response.status_code == 200, response.text
            preview = response.json()
            assert [row["rcsme_reg_no"] for row in preview["rows"]] == ["001-2", "001-1", "ABC"]
            assert preview["missing"] == ["missing"]
            assert preview["duplicates"] == 1

            no_year = await client.post("/exports/rcsme/preview", data={"numbers": "001-1 001-2"})
            assert no_year.json()["ambiguous"] == ["001-1"]
            assert [row["rcsme_reg_no"] for row in no_year.json()["rows"]] == ["001-2"]

            download = await client.post("/exports/rcsme.xlsx", json=preview["rows"])
            assert download.status_code == 200, download.text
            sheet = load_workbook(BytesIO(download.content)).active
            assert list(sheet.values) == [HEADERS, ("02", "001-2", None), ("007", "001-1", "0005"), ("07", "ABC", "=1+1")]
            assert sheet["C4"].data_type == "s"
            assert (await client.post("/exports/rcsme/preview", data={"numbers": " "})).status_code == 422
    finally:
        await engine.dispose()
