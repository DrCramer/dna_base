from app.services.protocol_plate import build_pcr_plates, build_plates, build_protocol_layouts


def objects(count: int) -> list[dict]:
    return [{"id": index, "rcsme_reg_no": f"ии{index}"} for index in range(1, count + 1)]


def kinds(plate: dict) -> list[str]:
    return [item["kind"] for item in plate["wells"]]


def test_plate_without_controls_accepts_96_samples():
    result = build_plates(objects(96), {"nc_enabled": False})
    assert result["capacity"] == 96
    assert len(result["plates"]) == 1
    assert kinds(result["plates"][0]).count("sample") == 96


def test_plate_with_nc_accepts_95_samples():
    result = build_plates(objects(95), {"nc_enabled": True})
    assert result["capacity"] == 95
    assert kinds(result["plates"][0]).count("sample") == 95
    assert kinds(result["plates"][0]).count("nc") == 1


def test_plate_with_pc_and_nc_accepts_94_samples():
    result = build_plates(objects(94), {"pc_enabled": True, "nc_enabled": True})
    assert result["capacity"] == 94
    assert kinds(result["plates"][0])[-2:] == ["pc", "nc"]


def test_ladders_reserve_excel_wells():
    result = build_plates(objects(88), {"ladder_enabled": True, "pc_enabled": True, "nc_enabled": True})
    by_well = {item["well"]: item for item in result["plates"][0]["wells"]}
    assert result["capacity"] == 88
    assert [by_well[f"A{column}"]["kind"] for column in (1, 3, 5, 7, 9, 11)] == ["ladder"] * 6
    assert kinds(result["plates"][0]).count("pc") == 1
    assert kinds(result["plates"][0]).count("nc") == 1


def test_pcr_overflow_repeats_controls_on_every_plate():
    result = build_pcr_plates(objects(177))
    assert result["capacity"] == 88
    assert [plate["sample_count"] for plate in result["plates"]] == [88, 88, 1]
    for plate in result["plates"]:
        assert kinds(plate).count("ladder") == 6
        assert kinds(plate).count("pc") == 1
        assert kinds(plate).count("nc") == 1


def test_source_and_pcr_use_same_natural_object_order():
    source = [{"id": 10, "rcsme_reg_no": "ии10"}, {"id": 2, "rcsme_reg_no": "ии2"}, {"id": 1, "rcsme_reg_no": "ии1"}]
    layouts = build_protocol_layouts(source, {"nc_enabled": False})
    for key in ("source", "pcr"):
        samples = [item["display_name"] for item in layouts[key]["plates"][0]["wells"] if item["kind"] == "sample"]
        assert samples == ["ии1", "ии2", "ии10"]
