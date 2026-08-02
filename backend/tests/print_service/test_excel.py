from pathlib import Path

from openpyxl import Workbook

from app.print_service.services.excel_service import match_excel_groups, parse_excel_sequences


def docs(*names):
    return [
        {"id": f"doc_{index}", "original_name": name, "path": f"input/doc_{index}.docx"}
        for index, name in enumerate(names, start=1)
    ]


def write_workbook(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet["A1"] = "Первая пачка"
    sheet["A2"] = "ее5968"
    sheet["A3"] = "ее6032"
    sheet["B1"] = "Вторая пачка"
    sheet["B2"] = "нн2832"
    workbook.save(path)


def test_parse_excel_columns_as_separate_sequences(tmp_path):
    path = tmp_path / "order.xlsx"
    write_workbook(path)
    groups = parse_excel_sequences(
        path,
        docs("Документ_ее5968.docx", "Документ_ее6032.docx", "Документ_нн2832.docx"),
    )
    assert [group["title"] for group in groups] == ["Первая пачка", "Вторая пачка"]
    assert groups[0]["sequence"] == "ее5968\nее6032"
    assert groups[1]["sequence"] == "нн2832"


def test_match_excel_groups_reports_global_unused_documents(tmp_path):
    path = tmp_path / "order.xlsx"
    write_workbook(path)
    result = match_excel_groups(
        path,
        docs(
            "Документ_ее5968.docx",
            "Документ_ее6032.docx",
            "Документ_нн2832.docx",
            "Лишний_ии0001.docx",
        ),
    )
    assert result["mode"] == "excel"
    assert result["can_build"] is True
    assert result["total_groups"] == 2
    assert len(result["unused_documents"]) == 1
