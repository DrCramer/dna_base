import copy
import math
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from app.schemas.protocols import ProtocolDilutionSettings


EPSILON = 1e-9
MAX_SINGLE_CANDIDATES = 32
MAX_PAIR_CANDIDATES = 64


@dataclass(frozen=True, slots=True)
class _Candidate:
    water: tuple[float, ...]
    concentration: float
    error: float
    volumes: tuple[float, ...] = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, "volumes", tuple(sorted(set(self.water))))

    @property
    def rank(self):
        return abs(self.error), self.water


def _actual_concentration(source: float, dna: Sequence[float], water: Sequence[float]) -> float:
    result = source
    for dna_volume, water_volume in zip(dna, water):
        if not math.isfinite(dna_volume + water_volume) or dna_volume <= 0 or water_volume < 0:
            raise ValueError("Недопустимый объём разведения")
        result *= dna_volume / (dna_volume + water_volume)
    return result


def calculate_actual_dilution_concentration(source: float, steps: Sequence[dict[str, Any]]) -> float:
    if not math.isfinite(source) or source <= 0:
        raise ValueError("Необходима положительная исходная концентрация Small")
    return _actual_concentration(source, [step["dna_volume"] for step in steps], [step["water_volume"] for step in steps])


def _error(actual: float, target: float) -> float:
    return 100 * (actual / target - 1)


def _limits(settings: ProtocolDilutionSettings) -> tuple[float, float]:
    return (
        settings.max_under_target_pct if settings.max_under_target_pct is not None else settings.allowed_concentration_error_percent,
        settings.max_over_target_pct if settings.max_over_target_pct is not None else settings.allowed_concentration_error_percent,
    )


def _accepted(error: float, settings: ProtocolDilutionSettings) -> bool:
    under, over = _limits(settings)
    return -under - EPSILON <= error <= over + EPSILON


def _preferred_step_penalty(water: Iterable[float], grid: float) -> int:
    return sum(not math.isclose(value / grid, round(value / grid), rel_tol=0, abs_tol=1e-7) for value in water)


def _candidate_rank(candidate: _Candidate, settings: ProtocolDilutionSettings):
    if settings.optimization_priority == "minimum_error":
        return candidate.rank
    return _preferred_step_penalty(candidate.volumes, settings.preferred_water_step_ul), *candidate.rank


def _measurable(value: float, lower: float | None, upper: float | None, increment: float | None) -> bool:
    if not math.isfinite(value) or (lower is not None and value < lower - EPSILON) or (upper is not None and value > upper + EPSILON):
        return False
    return increment is None or math.isclose(value / increment, round(value / increment), rel_tol=0, abs_tol=1e-7)


def _volume_reason(dna: Sequence[float], water: Sequence[float], settings: ProtocolDilutionSettings) -> str | None:
    policy = settings.pipetting
    if dna[0] > settings.source_available_volume + EPSILON:
        return "source_volume_limit"
    for d, w in zip(dna, water):
        if d <= 0 or w < 0 or not _measurable(d, policy.dna_min_ul, policy.dna_max_ul, policy.dna_increment_ul):
            return "dna_not_measurable"
        if not _measurable(w, policy.water_min_ul, policy.water_max_ul, policy.water_increment_ul or 1):
            return "water_not_measurable"
        if settings.minimum_final_volume_enabled and d + w < settings.minimum_final_volume - EPSILON:
            return "minimum_volume_limit"
    if len(dna) == 2 and dna[0] + water[0] < dna[1] + policy.first_dilution_reserve_ul - EPSILON:
        return "insufficient_first_dilution"
    return None


def generate_allowed_water_candidates(
    source_concentration: float,
    target_concentration: float,
    dna_volume: float,
    *,
    baseline_water_volume: float,
    settings: ProtocolDilutionSettings,
    common_volumes: Sequence[float] = (),
    minimum_water: float = 0,
) -> list[float]:
    """Проверяет фактическую концентрацию каждого кандидата при фиксированной ДНК."""
    if not math.isfinite(source_concentration) or source_concentration <= 0 or dna_volume <= 0:
        return []
    under, over = _limits(settings)
    policy = settings.pipetting
    low = max(0, minimum_water, policy.water_min_ul or 0, dna_volume * (source_concentration / (target_concentration * (1 + over / 100)) - 1))
    high = dna_volume * (source_concentration / (target_concentration * (1 - under / 100)) - 1)
    if settings.minimum_final_volume_enabled:
        low = max(low, settings.minimum_final_volume - dna_volume)
    if policy.water_max_ul is not None:
        high = min(high, policy.water_max_ul)
    if high < low - EPSILON:
        return []
    ideal = dna_volume * (source_concentration / target_concentration - 1)
    candidates = {float(baseline_water_volume)}
    # Широкие интервалы ограничены: не перечисляем миллионы целых объёмов.
    for grid in (float(settings.preferred_water_step_ul),):
        first, last = math.ceil((low - EPSILON) / grid), math.floor((high + EPSILON) / grid)
        if last - first <= MAX_SINGLE_CANDIDATES:
            indices = range(first, last + 1)
        else:
            center = round(ideal / grid)
            indices = {first, last, *range(center - 3, center + 4), *[round(first + (last - first) * fraction / 4) for fraction in range(1, 4)]}
        candidates.update(round(index * grid, 12) for index in indices if first <= index <= last)
    baseline_error = _error(source_concentration * dna_volume / (dna_volume + baseline_water_volume), target_concentration)
    if not _accepted(baseline_error, settings):
        precision = policy.water_increment_ul or 1
        candidates.update(round(index * precision, 12) for index in (math.floor(ideal / precision), math.ceil(ideal / precision)))
    begin, end = bisect_left(common_volumes, low - EPSILON), bisect_right(common_volumes, high + EPSILON)
    candidates.update(common_volumes[begin:end])
    allowed = [water for water in candidates if low - EPSILON <= water <= high + EPSILON
               and _measurable(water, policy.water_min_ul, policy.water_max_ul, policy.water_increment_ul or 1)
               and _accepted(_error(source_concentration * dna_volume / (dna_volume + water), target_concentration), settings)]
    allowed.sort(key=lambda water: (
        _preferred_step_penalty((water,), settings.preferred_water_step_ul) if settings.optimization_priority == "fewest_volumes" else 0,
        abs(source_concentration * dna_volume / (dna_volume + water) / target_concentration - 1), water,
    ))
    chosen = allowed[:MAX_SINGLE_CANDIDATES]
    if baseline_water_volume in allowed and baseline_water_volume not in chosen:
        chosen[-1] = float(baseline_water_volume)
    return sorted(chosen)


def _row_candidates(row: dict[str, Any], settings: ProtocolDilutionSettings, common: Sequence[float]) -> list[_Candidate]:
    steps = row["steps"]
    dna = tuple(float(step["dna_volume"]) for step in steps)
    baseline = tuple(float(step["water_volume"]) for step in steps)
    source, target = float(row["source_concentration"]), float(row["target_concentration"])
    candidates: dict[tuple[float, ...], _Candidate] = {}

    def add(water: tuple[float, ...]):
        if _volume_reason(dna, water, settings):
            return
        actual = _actual_concentration(source, dna, water)
        error = _error(actual, target)
        if _accepted(error, settings):
            candidates[water] = _Candidate(tuple(float(value) for value in water), actual, error)

    add(baseline)
    if len(steps) == 1:
        for water in generate_allowed_water_candidates(source, target, dna[0], baseline_water_volume=baseline[0], settings=settings, common_volumes=common):
            add((water,))
    elif len(steps) == 2:
        first_target = math.sqrt(source * target)
        reserve_water = max(0, dna[1] + settings.pipetting.first_dilution_reserve_ul - dna[0])
        first = generate_allowed_water_candidates(source, first_target, dna[0], baseline_water_volume=baseline[0], settings=settings, common_volumes=common, minimum_water=reserve_water)
        first = sorted(first, key=lambda water: (abs(water - baseline[0]), water))[:12]
        grid = settings.preferred_water_step_ul
        first = sorted({*first, baseline[0], *[max(0, (round(baseline[0] / grid) + offset) * grid) for offset in range(-2, 3)]})
        for water_one in first:
            if dna[0] + water_one < dna[1] + settings.pipetting.first_dilution_reserve_ul - EPSILON:
                continue
            intermediate = source * dna[0] / (dna[0] + water_one)
            # II этап рассчитывается заново от реальной концентрации после I этапа.
            for water_two in generate_allowed_water_candidates(intermediate, target, dna[1], baseline_water_volume=baseline[1], settings=settings, common_volumes=common):
                add((water_one, water_two))
    ordered = sorted(candidates.values(), key=lambda candidate: _candidate_rank(candidate, settings))
    limit = MAX_SINGLE_CANDIDATES if len(steps) == 1 else MAX_PAIR_CANDIDATES
    chosen = ordered[:limit]
    if baseline in candidates and candidates[baseline] not in chosen:
        chosen[-1] = candidates[baseline]
    return sorted(chosen, key=lambda item: _candidate_rank(item, settings))


def _batch_assignment(plans: dict[int, list[_Candidate]], fixed_water: set[float], preferred_step: float) -> dict[int, _Candidate]:
    selected = set(fixed_water)
    uncovered = set(plans)
    assignments: dict[int, _Candidate] = {}
    while uncovered:
        covers: dict[tuple[float, ...], dict[int, _Candidate]] = {}
        for index in sorted(uncovered):
            for candidate in plans[index]:
                needed = tuple(water for water in candidate.volumes if water not in selected)
                bucket = covers.setdefault(needed, {})
                if index not in bucket:
                    bucket[index] = candidate
        free = covers.get(())
        if free:
            assignments.update(free)
            uncovered.difference_update(free)
            continue
        chosen = min(covers, key=lambda water: (-len(covers[water]) / len(water), -len(covers[water]), _preferred_step_penalty(water, preferred_step), sum(abs(item.error) for item in covers[water].values()), water))
        selected.update(chosen)
    return assignments


REASONS = {
    "source_volume_limit": "Превышен доступный объём исходной ДНК.",
    "dna_not_measurable": "Объём ДНК не соответствует заданным диапазону или дискретности дозатора; ДНК не изменена.",
    "water_not_measurable": "Объём воды не соответствует заданным диапазону или дискретности дозатора.",
    "minimum_volume_limit": "Не соблюдён минимальный объём смеси; при фиксированном объёме ДНК допустимого варианта не найдено.",
    "insufficient_first_dilution": "Не хватает продукта I разведения для II этапа и заданного резерва.",
    "baseline_out_of_tolerance": "Базовый расчёт выходит за допуск конечной концентрации; допустимый объём при фиксированной ДНК не найден. Требуется решение сотрудника.",
}


def optimize_dilution_water_batches(rows: list[dict[str, Any]], settings: ProtocolDilutionSettings) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    result = copy.deepcopy(rows)
    active = {index: row for index, row in enumerate(result) if row.get("available") and row.get("steps") and row.get("source_concentration") is not None}
    common = sorted({float(step["water_volume"]) for row in active.values() for step in row["steps"]})
    plans = {index: _row_candidates(row, settings, common) for index, row in active.items()}
    fixed_water = {float(step["water_volume"]) for index, row in active.items() if not plans[index] for step in row["steps"]}
    ready = {index: candidates for index, candidates in plans.items() if candidates}
    incumbent = {}
    for index, candidates in ready.items():
        baseline = tuple(float(step["water_volume"]) for step in active[index]["steps"])
        incumbent[index] = next((candidate for candidate in candidates if candidate.water == baseline), min(candidates, key=lambda item: item.rank))

    def objective(assignment):
        volumes = fixed_water | {water for item in assignment.values() for water in item.water}
        error = sum(abs(item.error) for item in assignment.values())
        # При равном числе настроек выбираем удобный шаг в любую сторону, затем меньшую ошибку.
        return (error, len(volumes)) if settings.optimization_priority == "minimum_error" else (len(volumes), _preferred_step_penalty(volumes, settings.preferred_water_step_ul), error)

    if settings.optimization_priority == "minimum_error":
        assignments = {index: min(candidates, key=lambda item: item.rank) for index, candidates in ready.items()}
    else:
        greedy = _batch_assignment(ready, fixed_water, settings.preferred_water_step_ul)
        assignments = min((incumbent, greedy), key=objective)
        selected = fixed_water | {water for candidate in assignments.values() for water in candidate.water}
        assignments = {index: min((candidate for candidate in candidates if set(candidate.water).issubset(selected)), key=lambda item: _candidate_rank(item, settings)) for index, candidates in ready.items()}

    for index, row in active.items():
        baseline_steps = copy.deepcopy(row["steps"])
        dna = tuple(float(step["dna_volume"]) for step in baseline_steps)
        baseline_water = tuple(float(step["water_volume"]) for step in baseline_steps)
        baseline_actual = _actual_concentration(row["source_concentration"], dna, baseline_water)
        baseline_error = _error(baseline_actual, row["target_concentration"])
        candidate = assignments.get(index)
        reason_code = _volume_reason(dna, baseline_water, settings)
        if not reason_code and not _accepted(baseline_error, settings):
            reason_code = "baseline_out_of_tolerance"
        row["baseline_steps"] = baseline_steps
        if candidate:
            for step, water in zip(row["steps"], candidate.water):
                step["water_volume"] = int(water) if water.is_integer() else water
                step["actual_factor"] = (step["dna_volume"] + water) / step["dna_volume"]
            # Итоговая проверка использует именно сериализуемые рабочие шаги.
            actual = calculate_actual_dilution_concentration(row["source_concentration"], row["steps"])
            error = _error(actual, row["target_concentration"])
            if not _accepted(error, settings) or _volume_reason(dna, candidate.water, settings):
                raise ValueError("Рабочие объёмы не прошли итоговую проверку разведения")
            changed = candidate.water != baseline_water
            status = "optimized" if changed else "unchanged"
            off_preferred_step = _preferred_step_penalty(candidate.water, settings.preferred_water_step_ul) > 0
            reason = ("Для соблюдения допуска или объединения группы выбран объём вне предпочтительного шага." if off_preferred_step else None) if changed else "Базовые объёмы сохранены: выбранное округление не улучшает общий план в установленном допуске."
            row["minimum_volume_available"] = True
            row["minimum_volume_warning"] = None
        else:
            status, actual, error = "blocked", baseline_actual, baseline_error
            reason = REASONS.get(reason_code, "Допустимый вариант при фиксированных объёмах ДНК не найден. Требуется решение сотрудника.")
        row["optimization"] = {
            "enabled": True, "status": status, "needs_review": status == "blocked",
            "actual_final_concentration": actual, "relative_error_percent": error,
            "target_concentration": row["target_concentration"],
            "baseline_actual_final_concentration": baseline_actual, "baseline_relative_error_percent": baseline_error,
            "baseline_out_of_tolerance": not _accepted(baseline_error, settings),
            "reason": reason, "reason_code": reason_code if status == "blocked" else None,
            "first_dilution_remaining_volume": dna[0] + row["steps"][0]["water_volume"] - dna[1] if len(dna) == 2 else None,
        }

    def groups(step_index):
        batches: dict[float, list[dict[str, Any]]] = {}
        for row in active.values():
            if len(row["steps"]) <= step_index:
                continue
            water = row["steps"][step_index]["water_volume"]
            batches.setdefault(water, []).append({key: row.get(key) for key in ("object_id", "display_name", "plate_index", "well")} | {"needs_review": row["optimization"]["needs_review"]})
        return [{"water_volume": water, "object_count": len(objects), "objects": objects} for water, objects in sorted(batches.items())]

    before = {step["water_volume"] for row in active.values() for step in row["baseline_steps"]}
    after = {step["water_volume"] for row in active.values() for step in row["steps"]}
    summary = {
        "enabled": True, "object_count": len(rows), "active_object_count": len(active),
        "unique_water_volumes_before": len(before), "unique_water_volumes_after": len(after),
        "optimized_object_count": sum(row["optimization"]["status"] == "optimized" for row in active.values()),
        "unchanged_object_count": sum(row["optimization"]["status"] == "unchanged" for row in active.values()),
        "blocked_object_count": sum(row["optimization"]["status"] == "blocked" for row in active.values()),
        "excluded_object_count": len(rows) - len(active),
        "max_absolute_error_percent": max((abs(row["optimization"]["relative_error_percent"]) for row in active.values()), default=0),
        "batch_groups_first": groups(0), "batch_groups_second": groups(1),
    }
    return result, summary
