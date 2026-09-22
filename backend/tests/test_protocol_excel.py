from io import BytesIO

from openpyxl import load_workbook

from app.services.protocol_excel import build_protocol_workbook
from app.services.protocol_plate import build_protocol_layouts


def test_protocol_excel_keeps_snapshot_order_and_multiple_pcr_plates():
    objects = [{"id": index, "rcsme_reg_no": f"ии{index}", "order_index": index - 1} for index in range(1, 97)]
    layouts = build_protocol_layouts(objects, {"nc_enabled": False})
    snapshot = {
        "protocol": {"protocol_date": "2026-09-21", "protocol_no": 1, "name": "21-09-26_1"},
        "objects": objects,
        "stages": [
            {"stage_type": stage, "work_date": "2026-09-21", "kit_name": None, "performers": [], "sequencer_name": None, "comment": None}
            for stage in ("dna_extraction", "realtime", "pcr", "electrophoresis")
        ],
        "layouts": layouts,
        "calculations": {"pcr": [], "electrophoresis": {"components": []}},
        "dilutions": [],
    }
    workbook = load_workbook(BytesIO(build_protocol_workbook(snapshot)), data_only=True)
    assert "Исходная плашка 1" in workbook.sheetnames
    assert "PCR 1" in workbook.sheetnames
    assert "PCR 2" in workbook.sheetnames
    assert workbook["Исходная плашка 1"]["B3"].value == "ии1"
    assert workbook["PCR 1"]["C3"].value == "ии8"
    assert workbook["PCR 2"]["B4"].value == "ии89"
