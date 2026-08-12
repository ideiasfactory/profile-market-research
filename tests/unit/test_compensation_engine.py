import unittest

from app.compensation.domain.schemas import (
    AllocationModel,
    CompensationObservation,
    CompensationResearchRequest,
    ContractType,
    CrawledDocument,
    Location,
    Salary,
    SalaryPeriod,
)
from app.compensation.llm.extractor import regex_extract_observations
from app.compensation.services.normalization import normalize_observations
from app.compensation.services.quality import (
    filter_observations,
    infer_seniority,
    sanitize_salary_period,
    seniority_compatible,
)
from app.compensation.services.statistics import calculate_market_stats
from app.compensation.utils import extract_money_values


def observation(
    value: float,
    *,
    contract: ContractType = ContractType.CLT,
    period: SalaryPeriod = SalaryPeriod.month,
    role: str = "Arquiteto",
    seniority: str = "senior",
    evidence: str | None = None,
    source_url: str = "https://example.com/salary",
) -> CompensationObservation:
    return CompensationObservation(
        role=role,
        normalized_role="Cloud Solution Architect",
        seniority=seniority,
        location=Location(city="Campinas", state="SP"),
        allocation_model=AllocationModel.hybrid,
        employment_type=contract,
        salary=Salary(average=value, period=period),
        source="fixture",
        source_url=source_url,
        evidence=evidence or f"Salário R$ {value:,.2f}",
        retrieved_at="2026-08-11T00:00:00Z",
    )


class CompensationEngineTest(unittest.TestCase):
    def test_clt_month_to_pj_hour_normalization(self):
        normalized = normalize_observations([observation(16800)], ContractType.PJ)
        self.assertEqual(normalized[0].normalized_salary["value"], 150.0)
        self.assertEqual(normalized[0].normalized_salary["monthly_equivalent"], 25200.0)

    def test_statistics_uses_p25_p75_recommended_range(self):
        normalized = normalize_observations(
            [observation(10000), observation(12000), observation(14000), observation(16000)],
            ContractType.PJ,
        )
        market, _observations, warnings = calculate_market_stats(normalized, ContractType.PJ)
        self.assertIsNotNone(market.p25)
        self.assertIsNotNone(market.median)
        self.assertEqual(market.recommended_range["min"], market.p25)
        self.assertEqual(market.recommended_range["max"], market.p75)
        self.assertEqual(warnings, [])

    def test_no_salary_evidence_means_no_observation(self):
        request = CompensationResearchRequest(
            profile="Arquiteto de Soluções",
            seniority="senior",
            allocation_model="hybrid",
            location={"city": "Campinas", "state": "SP"},
            target_contract="PJ",
        )
        document = CrawledDocument(
            url="https://example.com",
            source="generic",
            title="Vaga",
            content="Vaga de arquiteto sem remuneração divulgada.",
            retrieved_at="2026-08-11T00:00:00Z",
            crawl_method="search_snippet",
            status="partial",
        )
        self.assertEqual(regex_extract_observations(document, request, "Solution Architect"), [])

    def test_seniority_mismatch_is_filtered(self):
        request = CompensationResearchRequest(
            profile="Arquiteto de Soluções Senior",
            seniority="senior",
            allocation_model="hybrid",
            location={"city": "Campinas", "state": "SP"},
            target_contract="PJ",
        )
        junior = observation(
            4120,
            period=SalaryPeriod.year,
            role="Arquiteto Cloud Junior",
            seniority="senior",
            evidence="A média salarial anual de Arquiteto Cloud Junior é de R$ 4.120 (São Paulo).",
            source_url="https://www.glassdoor.com.br/Salarios/sao-paulo-arquiteto-cloud-junior-salario.htm",
        )
        senior = observation(
            20000,
            role="Arquiteto Cloud Senior",
            seniority="senior",
            evidence="Salário R$ 20.000/mês para Arquiteto Cloud Senior",
        )
        kept, warnings = filter_observations([junior, senior], request)
        self.assertEqual(len(kept), 1)
        self.assertIn("Junior", junior.evidence)
        self.assertTrue(any("senioridade" in warning.lower() for warning in warnings))

    def test_mislabeled_low_annual_salary_is_rejected_or_corrected(self):
        salary = sanitize_salary_period(
            Salary(average=4120, period=SalaryPeriod.year),
            evidence="A média salarial anual de Arquiteto Cloud é de R$ 4.120",
        )
        self.assertIsNotNone(salary)
        self.assertEqual(salary.period, SalaryPeriod.month)

        absurd = sanitize_salary_period(
            Salary(average=500, period=SalaryPeriod.year),
            evidence="média salarial anual R$ 500",
        )
        self.assertIsNone(absurd)

    def test_regex_ignores_junior_when_request_is_senior(self):
        request = CompensationResearchRequest(
            profile="Arquiteto de Soluções Senior",
            seniority="senior",
            allocation_model="hybrid",
            location={"city": "Campinas", "state": "SP"},
            target_contract="PJ",
        )
        document = CrawledDocument(
            url="https://www.glassdoor.com.br/Salarios/arquiteto-cloud-junior.htm",
            source="glassdoor",
            title="Arquiteto Cloud Junior salários",
            content="A média salarial anual de Arquiteto Cloud Junior é de R$ 4.120 (São Paulo).",
            retrieved_at="2026-08-11T00:00:00Z",
            crawl_method="search_snippet",
            status="partial",
        )
        self.assertEqual(regex_extract_observations(document, request, "Cloud Architect"), [])

    def test_extract_money_values_supports_mil(self):
        self.assertEqual(extract_money_values("Salário R$ 18 mil a R$ 21 mil/mês"), [18000.0, 21000.0])

    def test_seniority_helpers(self):
        self.assertEqual(infer_seniority("Arquiteto Cloud Junior"), "junior")
        self.assertTrue(seniority_compatible("senior", "senior"))
        self.assertFalse(seniority_compatible("junior", "senior"))
        self.assertTrue(seniority_compatible("principal", "senior"))

    def test_job_prefill_maps_open_job(self):
        from app.compensation.services.job_prefill import map_job_to_compensation_prefill

        job = {
            "id": "671bb12e8d6c",
            "title": "Arquiteto OIC - CPFL",
            "profile": "Arquiteto",
            "seniority": "Especialista",
            "work_location": "Híbrido",
            "compensation_type": "pj_hour",
            "compensation_min": 120,
            "compensation_max": 150,
            "job_description": "Local: Campinas/SP",
            "analysis": {
                "must_have": [{"name": "Oracle Integration Cloud"}],
                "core_skills": [{"name": "API Management"}, {"name": "Oracle Integration Cloud"}],
            },
        }
        prefill = map_job_to_compensation_prefill(job)
        self.assertEqual(prefill["profile"], "Arquiteto OIC - CPFL")
        self.assertEqual(prefill["seniority"], "senior")
        self.assertEqual(prefill["allocation_model"], "hybrid")
        self.assertEqual(prefill["target_contract"], "PJ")
        self.assertEqual(prefill["location"]["city"], "Campinas")
        self.assertEqual(prefill["location"]["state"], "SP")
        self.assertEqual(prefill["skills"][0], "Oracle Integration Cloud")
        self.assertIn("API Management", prefill["skills"])
        self.assertEqual(prefill["source_job_id"], "671bb12e8d6c")


if __name__ == "__main__":
    unittest.main()
