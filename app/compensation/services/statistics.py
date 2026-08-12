from __future__ import annotations

import statistics as py_stats

from app.compensation.domain.schemas import CompensationObservation, ContractType, MarketStats


def calculate_market_stats(
    observations: list[CompensationObservation],
    target_contract: ContractType,
) -> tuple[MarketStats, list[CompensationObservation], list[str]]:
    warnings: list[str] = []
    valid = [
        obs
        for obs in observations
        if not obs.excluded_from_statistics and isinstance(obs.normalized_salary.get("value"), (int, float))
    ]
    values = [float(obs.normalized_salary["value"]) for obs in valid]
    if not values:
        warnings.append("Nenhuma observação com evidência salarial válida foi encontrada.")
        empty_unit = "hour" if target_contract == ContractType.PJ else "month"
        return MarketStats(contract_type=target_contract, unit=empty_unit), observations, warnings

    filtered_observations = list(observations)
    filtered_values = list(values)
    # Mark IQR outliers when sample is large enough; keep previously excluded flags.
    if len(values) >= 5:
        q1, q3 = percentile(values, 25), percentile(values, 75)
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        rebuilt: list[CompensationObservation] = []
        filtered_values = []
        for observation in observations:
            if observation.excluded_from_statistics:
                rebuilt.append(observation)
                continue
            value = float(observation.normalized_salary["value"])
            excluded = value < lower or value > upper
            rebuilt.append(observation.model_copy(update={"excluded_from_statistics": excluded}))
            if not excluded:
                filtered_values.append(value)
        filtered_observations = rebuilt

    usable = [obs for obs in filtered_observations if not obs.excluded_from_statistics]
    filtered_values = [float(obs.normalized_salary["value"]) for obs in usable]
    if not filtered_values:
        warnings.append("Todas as observações foram excluídas por outlier/qualidade; amostra insuficiente.")
        empty_unit = "hour" if target_contract == ContractType.PJ else "month"
        return MarketStats(contract_type=target_contract, unit=empty_unit), filtered_observations, warnings

    if len(filtered_values) < 3:
        warnings.append("Amostra baixa; use a estimativa como referência preliminar.")

    p25, median, p75 = percentile(filtered_values, 25), percentile(filtered_values, 50), percentile(filtered_values, 75)
    monthly_values = [
        float(obs.normalized_salary.get("monthly_equivalent"))
        for obs in usable
        if isinstance(obs.normalized_salary.get("monthly_equivalent"), (int, float))
    ]
    market = MarketStats(
        contract_type=target_contract,
        unit="hour" if target_contract == ContractType.PJ else "month",
        minimum=round(min(filtered_values), 2),
        p25=round(float(p25), 2),
        median=round(float(median), 2),
        mean=round(float(py_stats.fmean(filtered_values)), 2),
        p75=round(float(p75), 2),
        maximum=round(max(filtered_values), 2),
        monthly_equivalent=round(float(py_stats.fmean(monthly_values)), 2) if monthly_values else None,
        recommended_range={"min": round(float(p25), 2), "max": round(float(p75), 2)},
    )
    return market, filtered_observations, warnings


def percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (percent / 100)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction
