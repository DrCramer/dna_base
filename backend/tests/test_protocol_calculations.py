from app.services.protocol_calculations import (
    calculate_dilution,
    calculate_electrophoresis_reagents,
    calculate_pcr_reagents,
    pcr_reaction_count,
)
from app.services.protocol_profile_seed import load_profile_rows


def test_dilution_is_not_required_below_target():
    result = calculate_dilution(0.05, target_concentration=0.1)
    assert result["total_factor"] == 1
    assert result["steps"] == []


def test_single_dilution():
    result = calculate_dilution(1, target_concentration=0.1, source_dna_volume=3, threshold=100)
    assert result["total_factor"] == 10
    assert result["steps"] == [{"factor": 10.0, "dna_volume": 3, "water_volume": 27.0}]


def test_two_sequential_dilutions_above_threshold():
    result = calculate_dilution(1000, target_concentration=0.1, source_dna_volume=3, dilution_one_volume=10, threshold=100)
    assert result["total_factor"] == 10000
    assert result["steps"][0] == {"factor": 100.0, "dna_volume": 3, "water_volume": 297.0}
    assert result["steps"][1] == {"factor": 100.0, "dna_volume": 10, "water_volume": 990.0}


def test_pcr_reagent_formula_matches_excel_overage():
    assert pcr_reaction_count(88) == 92
    result = calculate_pcr_reagents(88, {"master_mix": 5, "primer": 2.5, "taq": None})
    assert result["components"][0]["total"] == 506.0
    assert result["components"][1]["total"] == 253.0
    assert result["components"][2]["total"] is None


def test_electrophoresis_rounds_to_sequencer_capacity():
    result = calculate_electrophoresis_reagents(64, {"hidi_formamide": 9.5, "ils": 0.5}, "GTZ G16")
    assert result["loaded_wells"] == 80
    assert result["sequencer_capacity"] == 16
    assert result["reaction_count"] == 82


def test_v13_profiles_include_required_systems_and_unavailable_values():
    profiles = {row["СИСТЕМА"]: row for row in load_profile_rows()}
    assert {"GlobalFiler", "PanGlobal Plus", "VeriFiler Plus", "PP_Fusion6C", "PanGlobal Human"} <= profiles.keys()
    assert profiles["GlobalFiler"]["DyeSet"] == "J6"
    assert profiles["PanGlobal Human"]["GMIDX_Panel"] is None
