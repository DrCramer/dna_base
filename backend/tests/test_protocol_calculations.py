import copy

import pytest

from app.services.protocol_calculations import (
    aggregate_pcr_reagents,
    calculate_dilution,
    calculate_electrophoresis_reagents,
    calculate_electrophoresis_plate_reagents,
    protocol_plate_calculations,
    calculate_pcr_reagents,
    pcr_reaction_count,
)
from app.services.protocol_profile_seed import load_profile_rows
from app.schemas.protocols import ProtocolDilutionSettings
from app.services.protocol_plate import build_pcr_plates, count_active_electrophoresis_wells


def test_electrophoresis_reagents_are_calculated_for_each_physical_plate():
    plates = build_pcr_plates([{"id": index, "rcsme_reg_no": str(index)} for index in range(120)])["plates"]
    config = {"hidi_formamide": 9.5, "ils": 0.5, "pcr_products": 1}
    result = calculate_electrophoresis_plate_reagents(plates, config, "GTZ G16")
    assert [item["plate_index"] for item in result] == [1, 2]
    assert [item["reaction_count"] for item in result] == [99, 49]
    for plate, item in zip(plates, result):
        assert item == {"plate_index": plate["plate_index"], **calculate_electrophoresis_reagents(count_active_electrophoresis_wells([plate]), config, "GTZ G16")}


@pytest.mark.asyncio
async def test_preview_calculates_reagents_from_each_plate_not_protocol_total(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.schemas.protocols import ProtocolPreviewRequest
    from app.services import protocols

    objects = [{"id": index, "rcsme_reg_no": str(index)} for index in range(1, 102)]
    stages = [{"stage_type": stage, "enabled": True, "sequencer_name": "GTZ G24"} for stage in protocols.STAGE_ORDER]
    profiles = {
        "pcr": SimpleNamespace(reagent_config_json={"master_mix": 5, "dna": 1}),
        "electrophoresis": SimpleNamespace(reagent_config_json={"ils": 0.5, "pcr_products": 1}),
    }
    monkeypatch.setattr(protocols, "protocol_object_snapshots", AsyncMock(return_value=objects))
    monkeypatch.setattr(protocols, "_stage_snapshots", AsyncMock(return_value=(stages, profiles)))
    payload = ProtocolPreviewRequest(protocol_date="2026-10-14", protocol_no=1, name="test", object_ids=[obj["id"] for obj in objects], dilution={"enabled": False})
    preview = await protocols.build_protocol_snapshot(None, payload)
    pcr = preview["calculations"]["pcr"]
    forez = preview["calculations"]["electrophoresis_plates"]
    assert preview["selected_count"] == 101
    assert [plate["sample_count"] for plate in preview["layouts"]["pcr"]["plates"]] == [88, 13]
    assert [block["sample_count"] for block in pcr] == [88, 13]
    assert [block["reaction_count"] for block in pcr] == [92, 15]
    assert [next(item["total"] for item in block["components"] if item["key"] == "master_mix") for block in pcr] == [506, 82.5]
    assert [block["loaded_wells"] for block in forez] == [96, 24]
    assert [next(item["total"] for item in block["components"] if item["key"] == "ils") for block in forez] == [54.5, 13.2]


def test_dna_and_pcr_products_keep_per_reaction_without_totals():
    pcr = calculate_pcr_reagents(88, {"dna": 1, "master_mix": 5})
    forez = calculate_electrophoresis_reagents(96, {"pcr_products": 1, "ils": 0.5}, "GTZ G24")
    aggregate = aggregate_pcr_reagents([{"sample_count": 88}, {"sample_count": 13}], {"dna": 1})
    for block, key in ((pcr, "dna"), (forez, "pcr_products"), (aggregate, "dna")):
        component = next(item for item in block["components"] if item["key"] == key)
        assert component["per_reaction"] == 1
        assert component["total"] is None
    assert pcr["components"][0]["total"] == 506
    assert next(item["total"] for item in forez["components"] if item["key"] == "ils") == 54.5


def test_legacy_print_calculations_use_snapshot_values_without_mutating_document():
    plates = build_pcr_plates([{"id": index, "rcsme_reg_no": str(index)} for index in range(120)])["plates"]
    config = {"hidi_formamide": 9.5, "ils": 0.5}
    snapshot = {"layouts": {"pcr": {"plates": plates}}, "calculations": {
        "pcr": [{"plate_index": 1, "components": [{"key": "master_mix", "per_reaction": 5, "total": 506}]}],
        "electrophoresis": calculate_electrophoresis_reagents(count_active_electrophoresis_wells(plates), config, "GTZ G24"),
    }}
    original = copy.deepcopy(snapshot)
    result = protocol_plate_calculations(snapshot)
    assert snapshot == original
    assert result["pcr"] == original["calculations"]["pcr"]
    assert result["electrophoresis_plates"] == calculate_electrophoresis_plate_reagents(plates, config, "GTZ G24")
    snapshot["calculations"]["electrophoresis_plates"] = result["electrophoresis_plates"]
    snapshot["calculations"]["electrophoresis"]["components"][0]["per_reaction"] = 999
    assert protocol_plate_calculations(snapshot)["electrophoresis_plates"] == result["electrophoresis_plates"]
    assert protocol_plate_calculations({}) == {"pcr": [], "electrophoresis_plates": []}


def test_protocol_api_exposes_print_calculations_without_replacing_saved_snapshot():
    from datetime import date, datetime, timezone
    from app.api.protocols import _protocol_out
    from app.models import LabProtocol

    plates = build_pcr_plates([{"id": 1, "rcsme_reg_no": "7606-1"}])["plates"]
    snapshot = {"layouts": {"pcr": {"plates": plates}}, "calculations": {
        "pcr": [], "electrophoresis": calculate_electrophoresis_reagents(count_active_electrophoresis_wells(plates), {"ils": 0.5}, "GTZ G16"),
    }}
    original = copy.deepcopy(snapshot)
    stamp = datetime.now(timezone.utc)
    protocol = LabProtocol(id=1, series_key="test", protocol_no=1, protocol_date=date(2026, 10, 14), name="test", status="final", revision_no=1, comment=None, created_by_user_id=None, created_at=stamp, updated_at=stamp, finalized_at=stamp, snapshot_json=snapshot)
    result = _protocol_out(protocol)
    assert result.snapshot == original
    assert protocol.snapshot_json == original
    assert result.plate_calculations["electrophoresis_plates"] == calculate_electrophoresis_plate_reagents(plates, {"ils": 0.5}, "GTZ G16")


def test_dilution_is_not_required_below_target():
    result = calculate_dilution(0.05, target_concentration=0.1)
    assert result["total_factor"] == 0.5
    assert result["steps"] == []
    assert result["actual_final_concentration"] == 0.05
    assert result["no_dilution_reason"] == "source_below_target"


@pytest.mark.parametrize("source,target,factor,count", [(10, 0.1, 100, 1), (10, 1, 10, 1), (1000, 0.1, 10000, 2), (1000, 1, 1000, 2), (0.4, 1, 0.4, 0), (1, 1, 1, 0)])
def test_custom_target_concentration_uses_existing_dilution_rules(source, target, factor, count):
    result = calculate_dilution(source, target_concentration=target)
    assert result["total_factor"] == factor
    assert len(result["steps"]) == count
    assert all(step["water_volume"] >= 0 for step in result["steps"])


@pytest.mark.parametrize("kind", ["chs", "genetic_examination"])
@pytest.mark.parametrize("dna_volume", [1, 15])
@pytest.mark.asyncio
async def test_target_changes_all_rows_but_never_pcr_recipe_layout_or_active_target(monkeypatch, kind, dna_volume):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.schemas.protocols import ProtocolPreviewRequest
    from app.services import protocols

    objects = [{"id": index, "source_kind": kind, "display_name": str(index), "rcsme_reg_no": str(index), "rt": {"small_quantity": small, "long_quantity": long, "y_quantity": y}} for index, (small, long, y) in enumerate([(10, 20, 5), (1000, 2000, 500), (0.4, 0.8, 0.2), (None, 5, 2)], 1)]
    stages = [{"stage_type": stage, "enabled": True, "sequencer_name": None} for stage in protocols.STAGE_ORDER]
    config = {"master_mix": 5, "h2o": 2, "dna": dna_volume}
    original_config = copy.deepcopy(config)
    monkeypatch.setattr(protocols, "protocol_object_snapshots", AsyncMock(return_value=objects))
    monkeypatch.setattr(protocols, "genetic_object_snapshots", AsyncMock(return_value=objects))
    monkeypatch.setattr(protocols, "_stage_snapshots", AsyncMock(return_value=(stages, {"pcr": SimpleNamespace(reagent_config_json=config)})))
    payload = ProtocolPreviewRequest(kind=kind, examination_year=2026 if kind == "genetic_examination" else None, protocol_date="2026-10-27", protocol_no=1, name="Target", object_ids=[1, 2, 3, 4], dilution={"target_overrides": {f"{kind}:1": "long"}})
    first = await protocols.build_protocol_snapshot(None, payload)
    payload.dilution.target_concentration = 1
    second = await protocols.build_protocol_snapshot(None, payload)
    assert first["layouts"] == second["layouts"]
    assert first["calculations"] == second["calculations"]
    assert config == original_config
    assert [row["total_factor"] for row in second["dilutions"]] == [20, 1000, 0.4, None]
    assert second["dilutions"][0]["active_target"] == "long"
    assert second["dilutions"][3]["available"] is False
    assert all(row["target_concentration"] == 1 for row in second["dilutions"])
    assert second["snapshot"]["dilution_settings"]["target_concentration"] == 1
    for index in (0, 1):
        assert sum(step["water_volume"] for step in second["dilutions"][index]["steps"]) < sum(step["water_volume"] for step in first["dilutions"][index]["steps"])
        if len(first["dilutions"][index]["steps"]) == len(second["dilutions"][index]["steps"]):
            assert all(new["water_volume"] < old["water_volume"] for old, new in zip(first["dilutions"][index]["steps"], second["dilutions"][index]["steps"]))
    assert first["snapshot"]["dilution_settings"]["target_concentration"] == 0.1


@pytest.mark.parametrize("value", [0, -1, float('nan'), float('inf')])
def test_target_validation_rejects_nonpositive_and_nonfinite_values(value):
    with pytest.raises(ValueError):
        ProtocolDilutionSettings(target_concentration=value)


def test_single_dilution():
    result = calculate_dilution(1, target_concentration=0.1, source_dna_volume=3, threshold=100)
    assert result["total_factor"] == 10
    assert result["steps"] == [{"factor": 10.0, "dna_volume": 3, "water_volume": 27.0}]


def test_dilution_water_is_always_rounded_up_to_integer():
    above_integer = calculate_dilution(1.0003333333333333, target_concentration=0.1)
    exact_integer = calculate_dilution(1, target_concentration=0.1)
    assert above_integer["steps"][0]["water_volume"] == 28
    assert exact_integer["steps"][0]["water_volume"] == 27


def test_two_sequential_dilutions_above_threshold():
    result = calculate_dilution(1000, target_concentration=0.1, source_dna_volume=3, dilution_one_volume=10, threshold=100)
    assert result["total_factor"] == 10000
    assert result["steps"][0] == {"factor": 100.0, "dna_volume": 3, "water_volume": 297.0}
    assert result["steps"][1] == {"factor": 100.0, "dna_volume": 10, "water_volume": 990.0}


def test_minimum_volume_disabled_preserves_existing_single_dilution():
    result = calculate_dilution(0.2, target_concentration=0.1)
    assert result["steps"] == [{"factor": 2.0, "dna_volume": 3, "water_volume": 3}]


def test_minimum_volume_scales_single_step_with_integer_water_and_exact_factor():
    result = calculate_dilution(0.2, target_concentration=0.1, minimum_final_volume_enabled=True)
    step = result["steps"][0]
    assert step["dna_volume"] == 8
    assert step["water_volume"] == 8
    assert step["dna_volume"] + step["water_volume"] >= 15
    assert (step["dna_volume"] + step["water_volume"]) / step["dna_volume"] == step["factor"]
    assert isinstance(step["water_volume"], int)
    assert step["dna_volume"] <= 50


def test_minimum_volume_leaves_sufficient_existing_single_steps_unchanged():
    factor_five = calculate_dilution(0.5, target_concentration=0.1, minimum_final_volume_enabled=True)
    factor_ten = calculate_dilution(1, target_concentration=0.1, minimum_final_volume_enabled=True)
    assert factor_five["steps"] == [{"factor": 5.0, "dna_volume": 3, "water_volume": 12}]
    assert factor_ten["steps"] == [{"factor": 10.0, "dna_volume": 3, "water_volume": 27}]


def test_minimum_volume_scales_both_steps_and_keeps_second_step_supplied():
    result = calculate_dilution(
        100,
        target_concentration=0.01,
        source_dna_volume=0.01,
        dilution_one_volume=0.01,
        minimum_final_volume_enabled=True,
    )
    first, second = result["steps"]
    for step in result["steps"]:
        assert step["dna_volume"] + step["water_volume"] >= 15
        assert (step["dna_volume"] + step["water_volume"]) / step["dna_volume"] == step["factor"]
        assert isinstance(step["water_volume"], int)
    assert first["dna_volume"] <= 50
    assert first["dna_volume"] + first["water_volume"] >= second["dna_volume"]


def test_minimum_volume_reports_when_source_limit_makes_scaling_impossible():
    result = calculate_dilution(
        1.01,
        target_concentration=1,
        minimum_final_volume_enabled=True,
    )
    assert result["minimum_volume_available"] is False
    assert "более 50 мкл исходной ДНК" in result["minimum_volume_warning"]
    assert result["steps"] == [{"factor": 1.01, "dna_volume": 3, "water_volume": 1}]


def test_minimum_volume_does_not_create_step_when_dilution_is_unneeded():
    result = calculate_dilution(0.05, target_concentration=0.1, minimum_final_volume_enabled=True)
    assert result["steps"] == []


def test_dilution_settings_snapshot_values_round_trip():
    settings = ProtocolDilutionSettings(minimum_final_volume_enabled=True)
    snapshot_settings = settings.model_dump()
    assert snapshot_settings == {
        "enabled": True,
        "show_all_targets": False,
        "target_overrides": {},
        "target_concentration": 0.1,
        "source_dna_volume": 3,
        "dilution_one_volume": 10,
        "threshold": 100,
        "minimum_final_volume_enabled": True,
        "minimum_final_volume": 15,
        "source_available_volume": 50,
        "optimize_water_volumes": False,
        "allowed_concentration_error_percent": 5,
        "preferred_water_step_ul": 10,
        "optimization_priority": "fewest_volumes",
        "max_under_target_pct": None,
        "max_over_target_pct": None,
        "pipetting": {"water_increment_ul": None, "water_min_ul": None, "water_max_ul": None, "dna_increment_ul": None, "dna_min_ul": None, "dna_max_ul": None, "first_dilution_reserve_ul": 0},
    }
    restored = ProtocolDilutionSettings.model_validate(snapshot_settings)
    assert restored.minimum_final_volume_enabled is True
    assert restored.minimum_final_volume == 15
    assert restored.source_available_volume == 50
    legacy = ProtocolDilutionSettings.model_validate({"minimum_final_volume_enabled": True})
    assert legacy.optimize_water_volumes is False


def test_pcr_reagent_formula_matches_excel_overage():
    assert pcr_reaction_count(88) == 92
    result = calculate_pcr_reagents(88, {"master_mix": 5, "primer": 2.5, "taq": None})
    assert result["components"][0]["total"] == 506.0
    assert result["components"][1]["total"] == 253.0
    assert result["components"][2]["total"] is None


def test_pcr_reagents_aggregate_all_plates_into_one_total():
    result = aggregate_pcr_reagents(
        [{"sample_count": 10}, {"sample_count": 10}],
        {"master_mix": 5, "taq": "-"},
    )
    assert result["sample_count"] == 20
    assert result["reaction_count"] == 24
    master_mix = next(item for item in result["components"] if item["key"] == "master_mix")
    taq = next(item for item in result["components"] if item["key"] == "taq")
    assert master_mix["per_reaction"] == 5
    assert master_mix["total"] == 132.0
    assert taq["per_reaction"] is None
    assert taq["total"] is None


def test_electrophoresis_rounds_to_sequencer_capacity():
    result = calculate_electrophoresis_reagents(64, {"hidi_formamide": 9.5, "ils": 0.5}, "GTZ G16")
    assert result["loaded_wells"] == 64
    assert result["sequencer_capacity"] == 16
    assert result["reaction_count"] == 66


def test_v13_profiles_include_required_systems_and_unavailable_values():
    profiles = {row["СИСТЕМА"]: row for row in load_profile_rows()}
    assert {"GlobalFiler", "PanGlobal Plus", "VeriFiler Plus", "PP_Fusion6C", "PanGlobal Human"} <= profiles.keys()
    assert profiles["GlobalFiler"]["DyeSet"] == "J6"
    assert profiles["PanGlobal Human"]["GMIDX_Panel"] is None
