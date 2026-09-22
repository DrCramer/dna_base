from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


THIN = Side(style="thin", color="000000")


def _plate_sheet(workbook: Workbook, title: str, plate: dict[str, Any]) -> None:
    ws = workbook.create_sheet(title[:31])
    ws.sheet_view.showGridLines = False
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.append([title])
    ws.merge_cells("A1:M1")
    ws["A1"].font = Font(bold=True, size=14)
    ws["A1"].alignment = Alignment(horizontal="center")
    ws.append([""] + list(range(1, 13)))
    by_well = {item["well"]: item for item in plate["wells"]}
    for row_name in "ABCDEFGH":
        ws.append([row_name] + [by_well[f"{row_name}{column}"].get("display_name") or "" for column in range(1, 13)])
    for row in ws.iter_rows(min_row=2, max_row=10, min_col=1, max_col=13):
        for cell in row:
            cell.border = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for column in range(2, 14):
        ws.column_dimensions[get_column_letter(column)].width = 14
    for row in range(3, 11):
        ws.row_dimensions[row].height = 36
    ws.print_area = "A1:M10"
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1


def build_protocol_workbook(snapshot: dict[str, Any]) -> bytes:
    workbook = Workbook()
    overview = workbook.active
    overview.title = "Единая_плашка_A4"
    overview.sheet_view.showGridLines = False
    overview.page_setup.orientation = "landscape"
    overview.page_setup.paperSize = overview.PAPERSIZE_A4
    protocol = snapshot["protocol"]
    overview.append(["ЕДИНЫЙ ПРОТОКОЛ ПЛАШКИ: ВЫДЕЛЕНИЕ / RT / PCR / ФОРЕЗ"])
    overview.merge_cells("A1:H1")
    overview["A1"].font = Font(bold=True, size=15)
    overview["A1"].alignment = Alignment(horizontal="center")
    overview.append(["Дата", protocol["protocol_date"], "№", protocol["protocol_no"], "Название", protocol["name"], "Объектов", len(snapshot["objects"])])
    labels = {"dna_extraction": "Выделение", "realtime": "Real Time", "pcr": "PCR", "electrophoresis": "Форез"}
    for stage in snapshot["stages"]:
        names = ", ".join(item["display_name"] for item in stage.get("performers", []))
        overview.append([labels[stage["stage_type"]], stage.get("work_date"), stage.get("kit_name"), names, stage.get("sequencer_name"), stage.get("comment")])
    for row in overview.iter_rows(min_row=2, max_row=6, min_col=1, max_col=8):
        for cell in row:
            cell.border = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    for key, title in (("source", "Исходная плашка"), ("pcr", "PCR")):
        for plate in snapshot["layouts"][key]["plates"]:
            _plate_sheet(workbook, f"{title} {plate['plate_index']}", plate)

    calculations = workbook.create_sheet("Расчёты")
    calculations.append(["Этап", "Плашка", "Компонент", "На реакцию", "Всего"])
    for block in snapshot["calculations"]["pcr"]:
        for component in block["components"]:
            calculations.append(["PCR", block["plate_index"], component["label"], component["per_reaction"], component["total"]])
    for component in snapshot["calculations"]["electrophoresis"]["components"]:
        calculations.append(["Форез", "", component["label"], component["per_reaction"], component["total"]])
    for cell in calculations[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="D9EAF7")

    dilution = workbook.create_sheet("Dilution")
    dilution.append(["Лунка", "Объект", "Исх. конц.", "Кон. конц.", "Фактор", "I разведение", "V ДНК", "V воды 1", "II разведение", "V ДНК 1", "V воды 2"])
    for item in snapshot.get("dilutions", []):
        steps = item.get("steps", [])
        first = steps[0] if steps else {}
        second = steps[1] if len(steps) > 1 else {}
        dilution.append([item.get("well"), item.get("display_name"), item.get("source_concentration"), item.get("target_concentration"), item.get("total_factor"), first.get("factor"), first.get("dna_volume"), first.get("water_volume"), second.get("factor"), second.get("dna_volume"), second.get("water_volume")])
    for cell in dilution[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="D9EAF7")
    for ws in workbook.worksheets:
        ws.freeze_panes = "A2"
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
