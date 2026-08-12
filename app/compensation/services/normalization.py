from __future__ import annotations

from app.compensation.core import get_settings
from app.compensation.domain.schemas import CompensationObservation, ContractType, SalaryPeriod


def normalize_observations(
    observations: list[CompensationObservation],
    target_contract: ContractType,
) -> list[CompensationObservation]:
    settings = get_settings()
    normalized = []
    for observation in observations:
        observed = observation.salary.model_dump()
        monthly = salary_to_monthly(observation)
        if monthly is None:
            continue
        employment_type = observation.employment_type or ContractType.CLT
        if target_contract == ContractType.PJ:
            if employment_type == ContractType.CLT:
                target_monthly = monthly * settings.clt_to_pj_factor
            else:
                target_monthly = monthly
            target_hour = target_monthly / settings.work_hours_month
            normalized_salary = {
                "currency": "BRL",
                "contract_type": "PJ",
                "period": "hour",
                "value": round(target_hour, 2),
                "monthly_equivalent": round(target_monthly, 2),
            }
        else:
            if employment_type == ContractType.PJ:
                target_monthly = monthly / settings.clt_to_pj_factor
            else:
                target_monthly = monthly
            normalized_salary = {
                "currency": "BRL",
                "contract_type": "CLT",
                "period": "month",
                "value": round(target_monthly, 2),
                "monthly_equivalent": round(target_monthly, 2),
            }
        normalized.append(
            observation.model_copy(
                update={
                    "observed_salary": observed,
                    "normalized_salary": normalized_salary,
                }
            )
        )
    return normalized


def salary_to_monthly(observation: CompensationObservation) -> float | None:
    salary = observation.salary
    values = [value for value in [salary.average, salary.min, salary.max] if value is not None and value > 0]
    if not values:
        return None
    value = sum(values) / len(values) if salary.average is None else salary.average
    if salary.period == SalaryPeriod.hour:
        return value * get_settings().work_hours_month
    if salary.period == SalaryPeriod.year:
        return value / 12
    return value
