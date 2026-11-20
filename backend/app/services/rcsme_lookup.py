import csv
from collections import defaultdict
from collections.abc import Iterable
from io import BytesIO, StringIO
from pathlib import Path
import re
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile, ZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.utils.exceptions import InvalidFileException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Party, RegistryObject


MAX_NUMBERS = 5000
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TABLE_ROWS = MAX_NUMBERS * 2
MAX_TABLE_COLUMNS = 100
HEADERS = ("№ партии", "№ рег РЦСМЭ", "№ в в/ч №522")


class RcsmeLookupRow(BaseModel):
    party_no: str | None = Field(max_length=80)
    rcsme_reg_no: str = Field(min_length=1, max_length=120)
    external_military_no: str | None = Field(max_length=255)


class RcsmeLookupResult(BaseModel):
    rows: list[RcsmeLookupRow]
    missing: list[str]
    ambiguous: list[str]
    duplicates: int


def _is_header(value: object) -> bool:
    key = re.sub(r"[^а-яёa-z]", "", str(value).lower())
    return key in {"рцсмэ", "регрцсмэ", "номеррцсмэ", "номеррегрцсмэ", "регистрационныйномеррцсмэ"}


def _column_values(rows: Iterable[tuple | list]) -> Iterable[object]:
    column = None
    single_column = False
    for index, row in enumerate(rows):
        filled = [index for index, value in enumerate(row) if value is not None and str(value).strip()]
        if not filled:
            continue
        if index >= MAX_TABLE_ROWS or filled[-1] >= MAX_TABLE_COLUMNS:
            raise ValueError("Слишком большая таблица. Оставьте в файле столбец с номерами РЦСМЭ.")
        if column is None:
            headers = [index for index in filled if _is_header(row[index])]
            if len(headers) == 1:
                column = headers[0]
                continue
            if len(filled) != 1 or headers:
                raise ValueError("Оставьте один столбец или укажите заголовок «№ рег РЦСМЭ».")
            column = filled[0]
            single_column = True
        if single_column and any(index != column for index in filled):
            raise ValueError("В таблице несколько столбцов. Укажите заголовок «№ рег РЦСМЭ».")
        if column < len(row):
            yield row[column]


def _text_values(text: str, *, csv_file: bool = False) -> Iterable[object]:
    text = text.removeprefix("\ufeff")
    if not text.strip():
        return
    first_line = next(line for line in text.splitlines() if line.strip())
    if csv_file or "\t" in first_line:
        delimiter = max(("\t", ";", ","), key=first_line.count)
        yield from _column_values(csv.reader(StringIO(text), delimiter=delimiter, strict=True))
    else:
        for line in text.splitlines():
            if not _is_header(line):
                yield from re.split(r"[\s,;]+", line.strip())


def _xlsx_values(content: bytes) -> Iterable[object]:
    with ZipFile(BytesIO(content)) as archive:
        members = archive.infolist()
        if len(members) > 1000 or sum(member.file_size for member in members) > 24 * 1024 * 1024:
            raise ValueError("Слишком большой Excel-файл после распаковки.")
    workbook = load_workbook(BytesIO(content), read_only=True, data_only=True, keep_links=False)
    try:
        if not workbook.worksheets:
            return
        sheet = workbook.worksheets[0]
        if (sheet.max_row or 0) > MAX_TABLE_ROWS or (sheet.max_column or 0) > MAX_TABLE_COLUMNS:
            raise ValueError("Слишком большая таблица. Оставьте в файле столбец с номерами РЦСМЭ.")
        sheet.reset_dimensions()
        yield from _column_values(sheet.iter_rows(max_row=MAX_TABLE_ROWS + 1, max_col=MAX_TABLE_COLUMNS + 1, values_only=True))
    finally:
        workbook.close()


def parse_lookup_numbers(text: str = "", *, filename: str = "", content: bytes = b"") -> tuple[dict[str, str], int]:
    suffix = Path(filename).suffix.lower()
    if filename and suffix not in {".xlsx", ".csv", ".txt"}:
        raise ValueError("Поддерживаются файлы .xlsx, .csv и .txt.")
    if len(content) > MAX_FILE_BYTES or len(text) > MAX_FILE_BYTES:
        raise ValueError("Размер списка не должен превышать 2 МБ.")
    try:
        if suffix == ".xlsx":
            values = _xlsx_values(content)
        elif suffix:
            try:
                decoded = content.decode("utf-8-sig")
            except UnicodeDecodeError:
                decoded = content.decode("cp1251")
            values = _text_values(decoded, csv_file=suffix == ".csv")
        else:
            values = _text_values(text)
        numbers: dict[str, str] = {}
        duplicates = 0
        for value in values:
            if value is None or isinstance(value, bool):
                continue
            if isinstance(value, float) and value.is_integer():
                value = int(value)
            number = str(value).strip()
            if not number or _is_header(number):
                continue
            if len(number) > 120 or any(ord(char) < 32 for char in number):
                raise ValueError("Номер РЦСМЭ должен содержать не более 120 символов и не содержать управляющих символов.")
            if number.lower() in numbers:
                duplicates += 1
            else:
                numbers[number.lower()] = number
            if len(numbers) + duplicates > MAX_NUMBERS:
                raise ValueError(f"За один раз можно проверить не более {MAX_NUMBERS} номеров.")
    except (BadZipFile, InvalidFileException, KeyError, IndexError, OSError, ParseError, UnicodeError, csv.Error) as exc:
        raise ValueError("Не удалось прочитать файл со списком номеров.") from exc
    if not numbers:
        raise ValueError("В списке нет номеров РЦСМЭ.")
    return numbers, duplicates


async def lookup_rcsme(session: AsyncSession, numbers: dict[str, str], duplicates: int, case_year: int | None) -> RcsmeLookupResult:
    key = func.lower(func.trim(RegistryObject.rcsme_reg_no))
    stmt = (
        select(key, func.coalesce(Party.party_no, RegistryObject.party_no), RegistryObject.rcsme_reg_no, RegistryObject.external_military_no)
        .outerjoin(Party, Party.id == RegistryObject.party_id)
        .where(key.in_(list(numbers)))
    )
    if case_year is not None:
        stmt = stmt.where(RegistryObject.case_year == case_year)
    matches: dict[str, list[RcsmeLookupRow]] = defaultdict(list)
    for normalized, party, registration, military in (await session.execute(stmt)).all():
        matches[normalized].append(RcsmeLookupRow(party_no=party, rcsme_reg_no=registration, external_military_no=military))
    return RcsmeLookupResult(
        rows=[matches[key][0] for key in numbers if len(matches[key]) == 1],
        missing=[number for key, number in numbers.items() if not matches[key]],
        ambiguous=[number for key, number in numbers.items() if len(matches[key]) > 1],
        duplicates=duplicates,
    )


def build_rcsme_workbook(rows: list[RcsmeLookupRow]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Сопоставление"
    sheet.append(HEADERS)
    for row in rows:
        sheet.append(tuple(ILLEGAL_CHARACTERS_RE.sub("", value) if value is not None else None for value in (row.party_no, row.rcsme_reg_no, row.external_military_no)))
        for cell in sheet[sheet.max_row]:
            if isinstance(cell.value, str):
                cell.data_type = "s"
    for column, width in zip("ABC", (18, 25, 28)):
        sheet.column_dimensions[column].width = width
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
