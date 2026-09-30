from app.services.protocol_calculations import (
    aggregate_pcr_reagents,
    calculate_dilution,
    calculate_electrophoresis_reagents,
    calculate_pcr_reagents,
    pcr_reaction_count,
)
from app.services.protocol_profile_seed import load_profile_rows
from app.schemas.protocols import ProtocolDilutionSettings


def test_dilution_is_not_required_below_target():
    result = calculate_dilution(0.05, target_concentration=0.1)
    assert result["total_factor"] == 1
    assert result["steps"] == []


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
        "target_concentration": 0.1,
        "source_dna_volume": 3,
        "dilution_one_volume": 10,
        "threshold": 100,
        "minimum_final_volume_enabled": True,
        "minimum_final_volume": 15,
        "source_available_volume": 50,
    }
    restored = ProtocolDilutionSettings.model_validate(snapshot_settings)
    assert restored.minimum_final_volume_enabled is True
    assert restored.minimum_final_volume == 15
    assert restored.source_available_volume == 50


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
