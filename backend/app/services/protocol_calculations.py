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


def aggregate_pcr_reagents(plates: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    per_plate = [calculate_pcr_reagents(plate["sample_count"], config) for plate in plates]
    labels = per_plate[0]["components"] if per_plate else calculate_pcr_reagents(0, config)["components"]
    components = []
    for component in labels:
        totals = [
            next(item["total"] for item in plate["components"] if item["key"] == component["key"])
            for plate in per_plate
        ]
        components.append(
            {
                **component,
                "total": round(sum(value for value in totals if value is not None), 1)
                if any(value is not None for value in totals)
                else None,
            }
        )
    return {
        "sample_count": sum(plate["sample_count"] for plate in plates),
        "reaction_count": sum(plate["reaction_count"] for plate in per_plate),
        "overage_percent": 10,
        "components": components,
    }


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
    loaded = int(math.ceil(max(0, sample_count) / capacity) * capacity) if sample_count else 0
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
    minimum_final_volume_enabled: bool = False,
    minimum_final_volume: float = 15,
    source_available_volume: float = 50,
) -> dict[str, Any]:
    result = {
        "source_concentration": source_concentration,
        "target_concentration": target_concentration,
        "total_factor": None,
        "steps": [],
        "available": source_concentration is not None and target_concentration > 0,
        "minimum_volume_available": True,
        "minimum_volume_warning": None,
    }
    if not result["available"]:
        return result
    factor = max(1.0, float(source_concentration) / target_concentration)
    result["total_factor"] = round(factor, 4)
    if factor <= 1:
        return result
    if factor <= threshold:
        steps = [
            {
                "factor": round(factor, 4),
                "dna_volume": source_dna_volume,
                "water_volume": math.ceil((factor - 1) * source_dna_volume),
            }
        ]
        step_factors = [factor]
    else:
        step_factor = math.sqrt(factor)
        steps = [
            {
                "factor": round(step_factor, 4),
                "dna_volume": source_dna_volume,
                "water_volume": math.ceil((step_factor - 1) * source_dna_volume),
            },
            {
                "factor": round(step_factor, 4),
                "dna_volume": dilution_one_volume,
                "water_volume": math.ceil((step_factor - 1) * dilution_one_volume),
            },
        ]
        step_factors = [step_factor, step_factor]

    if minimum_final_volume_enabled:
        original_steps = steps
        adjusted_steps = [
            _scale_dilution_step(step, step_factor, minimum_final_volume)
            for step, step_factor in zip(steps, step_factors)
        ]
        if len(adjusted_steps) == 2 and all(step is not None for step in adjusted_steps):
            adjusted_steps[0] = _scale_dilution_step(
                original_steps[0],
                step_factors[0],
                max(minimum_final_volume, adjusted_steps[1]["dna_volume"]),
            )

        first_step = adjusted_steps[0]
        if first_step is None or first_step["dna_volume"] > source_available_volume:
            result["minimum_volume_available"] = False
            result["minimum_volume_warning"] = (
                f"Для минимального объёма {minimum_final_volume:g} мкл требуется более "
                f"{source_available_volume:g} мкл исходной ДНК."
            )
        elif all(step is not None for step in adjusted_steps):
            steps = adjusted_steps

    result["steps"] = steps
    return result


def _scale_dilution_step(
    step: dict[str, Any], factor: float, required_volume: float
) -> dict[str, Any] | None:
    dna_volume = float(step["dna_volume"])
    water_volume = float(step["water_volume"])
    if dna_volume + water_volume >= required_volume:
        return step
    if factor <= 1:
        return None
    water_volume = math.ceil(required_volume * (factor - 1) / factor - 1e-12)
    dna_volume = water_volume / (factor - 1)
    while dna_volume + water_volume < required_volume:
        water_volume += 1
        dna_volume = water_volume / (factor - 1)
    return {**step, "dna_volume": dna_volume, "water_volume": water_volume}
