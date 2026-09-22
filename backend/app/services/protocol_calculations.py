import math
from typing import Any


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "."))
        except ValueError:
            return None
    return None


def pcr_reaction_count(sample_count: int) -> int:
    base = max(0, sample_count) + 2
    return base + base // 32


def calculate_pcr_reagents(sample_count: int, config: dict[str, Any]) -> dict[str, Any]:
    reactions = pcr_reaction_count(sample_count)
    components = []
    labels = {
        "master_mix": "Master mix",
        "primer": "Primer",
        "h2o": "H₂O",
        "taq": "TAQ",
        "mix_sample": "Mix",
        "dna": "DNA",
    }
    for key, label in labels.items():
        per_reaction = _number(config.get(key))
        components.append(
            {
                "key": key,
                "label": label,
                "per_reaction": per_reaction,
                "total": round(1.1 * reactions * per_reaction, 1) if per_reaction is not None else None,
            }
        )
    return {"sample_count": sample_count, "reaction_count": reactions, "overage_percent": 10, "components": components}


def sequencer_capacity(sequencer: str | None) -> int:
    normalized = (sequencer or "").casefold().replace(" ", "")
    if "g16" in normalized:
        return 16
    if "g24" in normalized:
        return 24
    return 8


def calculate_electrophoresis_reagents(
    sample_count: int, config: dict[str, Any], sequencer: str | None
) -> dict[str, Any]:
    capacity = sequencer_capacity(sequencer)
    loaded = int(math.ceil((max(0, sample_count) + 8) / capacity) * capacity)
    reactions = loaded + loaded // 32
    components = []
    labels = {
        "hidi_formamide": "HiDi Formamide",
        "ils": "ILS",
        "mix_f_ils": "Mix",
        "pcr_products": "PCR-продукты",
    }
    for key, label in labels.items():
        per_reaction = _number(config.get(key))
        components.append(
            {
                "key": key,
                "label": label,
                "per_reaction": per_reaction,
                "total": round(1.1 * reactions * per_reaction, 1) if per_reaction is not None else None,
            }
        )
    return {
        "sample_count": sample_count,
        "sequencer_capacity": capacity,
        "loaded_wells": loaded,
        "reaction_count": reactions,
        "overage_percent": 10,
        "components": components,
    }


def calculate_dilution(
    source_concentration: float | None,
    *,
    target_concentration: float = 0.1,
    source_dna_volume: float = 3,
    dilution_one_volume: float = 10,
    threshold: float = 100,
) -> dict[str, Any]:
    result = {
        "source_concentration": source_concentration,
        "target_concentration": target_concentration,
        "total_factor": None,
        "steps": [],
        "available": source_concentration is not None and target_concentration > 0,
    }
    if not result["available"]:
        return result
    factor = max(1.0, float(source_concentration) / target_concentration)
    result["total_factor"] = round(factor, 4)
    if factor <= 1:
        return result
    if factor <= threshold:
        result["steps"] = [
            {
                "factor": round(factor, 4),
                "dna_volume": source_dna_volume,
                "water_volume": round((factor - 1) * source_dna_volume, 2),
            }
        ]
        return result
    step_factor = math.sqrt(factor)
    result["steps"] = [
        {
            "factor": round(step_factor, 4),
            "dna_volume": source_dna_volume,
            "water_volume": round((step_factor - 1) * source_dna_volume, 2),
        },
        {
            "factor": round(step_factor, 4),
            "dna_volume": dilution_one_volume,
            "water_volume": round((step_factor - 1) * dilution_one_volume, 2),
        },
    ]
    return result
