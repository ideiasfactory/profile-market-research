from __future__ import annotations

import json
import unittest
from pathlib import Path

from app.job_understanding import normalize_job_analysis
from app.scoring_v2 import (
    build_v2_score_result,
    classify_critical_gaps,
    compute_must_have_coverage,
    decide_verdict,
)
from app.services import _ground_skill_scores_to_resume, heuristic_skill_scores, normalize_text


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _job_cpfl() -> dict:
    jobs = _load_json(DATA / "jobs.json")
    job = next(j for j in jobs if "OIC" in j.get("title", "") or "CPFL" in j.get("title", ""))
    job = {**job, "analysis": normalize_job_analysis(job.get("analysis"))}
    return job


def _candidate(slug_part: str) -> dict:
    index = _load_json(DATA / "candidates.json")
    entry = next(c for c in index if slug_part in normalize_text(c.get("name", "")))
    profile = _load_json(DATA / entry["path"])
    return {**entry, **profile}


class BenchmarkFixtures(unittest.TestCase):
    """
    Conceptual regression cases (not hardcoded exact scores).
    CASE-001 Bruno × Arquiteto OIC CPFL
    CASE-002 Gabriela × Arquiteto OIC CPFL
    """

    def test_case_001_bruno_has_oic_and_cpfl_context(self):
        bruno = _candidate("bruno")
        text = normalize_text(bruno["resume_text"])
        collapsed = " ".join(text.split())
        self.assertTrue(
            "oracle integration cloud" in collapsed or "oic" in collapsed,
            "Bruno must show OIC evidence",
        )
        self.assertIn("cpfl", text)
        self.assertIn("api management", collapsed)
        self.assertIn("sap po", collapsed)

        skills = [
            {"name": "Oracle Integration Cloud", "tier": "MUST_HAVE", "category": "Must-have", "weight": 10},
            {"name": "API Management", "tier": "CORE", "category": "Core skill", "weight": 7},
            {"name": "SAP Process Orchestration", "tier": "CORE", "category": "Core skill", "weight": 7},
            {"name": "Kafka", "tier": "SUPPORTING", "category": "Supporting skill", "weight": 3},
            {"name": "Comunicação", "tier": "SOFT", "category": "Soft skill", "weight": 3},
        ]
        scored = heuristic_skill_scores(skills, bruno["resume_text"], model="v2")
        scored = _ground_skill_scores_to_resume(scored, bruno["resume_text"], soft_null=True)
        by_name = {s["name"]: s for s in scored}

        self.assertGreaterEqual(by_name["Oracle Integration Cloud"]["score"], 3)
        self.assertGreaterEqual(by_name["API Management"]["score"], 3)
        # Supporting absence must not force discard by itself.
        kafka = by_name["Kafka"]
        self.assertTrue(kafka["score"] in (0, None) or kafka["score"] <= 2)

        items = []
        for skill in skills:
            s = by_name[skill["name"]]
            items.append({**skill, **s})

        # Exceptional context fit for CPFL (professional context only).
        result = build_v2_score_result(
            job=_job_cpfl(),
            candidate=bruno,
            items=items,
            method="heuristic",
            role_fit=85,
            context_fit=95,
            strengths=["Oracle Integration Cloud", "API Management", "CPFL architecture"],
            interview_validation=["Validar profundidade de migração SAP PO → OIC"],
        )
        self.assertNotEqual(result["verdict_label"], "not_recommended")
        self.assertIn(result["verdict_label"], {"strong_fit", "recommended", "evaluate"})
        # Supporting Kafka absence should not dominate.
        gaps = classify_critical_gaps(items)
        self.assertFalse(any(g["name"] == "Kafka" and g["severity"] == "critical" for g in gaps))

    def test_case_002_gabriela_cpi_is_not_oic(self):
        gabriela = _candidate("gabriela")
        text = normalize_text(gabriela["resume_text"])
        self.assertTrue("cpi" in text or "integration suite" in text)
        self.assertNotIn("oracle integration cloud", text)
        # Avoid false positive: 'oic' as substring of other words is bounded in matcher,
        # but explicit OIC platform should not appear.
        self.assertFalse(" oracle integration cloud " in f" {text} ")

        skills = [
            {"name": "Oracle Integration Cloud", "tier": "MUST_HAVE", "category": "Must-have", "weight": 10},
            {"name": "SAP Process Orchestration", "tier": "CORE", "category": "Core skill", "weight": 7},
            {"name": "SAP BTP", "tier": "CORE", "category": "Core skill", "weight": 7},
            {"name": "API Management", "tier": "CORE", "category": "Core skill", "weight": 7},
            {"name": "OData", "tier": "SUPPORTING", "category": "Supporting skill", "weight": 3},
        ]
        scored = heuristic_skill_scores(skills, gabriela["resume_text"], model="v2")
        # Simulate LLM wrongly equating CPI→OIC; grounding must zero it without resume evidence.
        for item in scored:
            if item["name"] == "Oracle Integration Cloud":
                item["score"] = 5
                item["evidence_status"] = "explicit"
                item["evidence"] = [{"text": "Experiência em SAP CPI equivalente a OIC", "source": "hallucination"}]
        scored = _ground_skill_scores_to_resume(scored, gabriela["resume_text"], soft_null=True)
        by_name = {s["name"]: s for s in scored}

        self.assertEqual(by_name["Oracle Integration Cloud"]["score"], 0)
        self.assertEqual(by_name["Oracle Integration Cloud"]["evidence_status"], "not_found")
        # Strong SAP integration evidence should remain.
        self.assertGreaterEqual(by_name["SAP BTP"]["score"], 3)

        items = [{**skill, **by_name[skill["name"]]} for skill in skills]
        coverage = compute_must_have_coverage(items)
        self.assertEqual(coverage["missing_skills"], ["Oracle Integration Cloud"])
        gaps = classify_critical_gaps(items)
        self.assertTrue(
            any(g["name"] == "Oracle Integration Cloud" and g["severity"] == "critical" for g in gaps)
        )

        result = build_v2_score_result(
            job=_job_cpfl(),
            candidate=gabriela,
            items=items,
            method="heuristic",
            role_fit=70,
            context_fit=55,
            strengths=["SAP BTP", "SAP Integration"],
            interview_validation=["Validar se há exposição real a Oracle Integration Cloud (não CPI)"],
        )
        # Should suggest evaluate/validation — not discard all technical fit.
        self.assertEqual(result["verdict_label"], "evaluate")
        self.assertGreater(result["score_breakdown"]["core_technical_fit"], 0)
        # Explicit rule: critical gap present, auto-eliminate off → evaluate path.
        verdict = decide_verdict(
            final_score=result["final_score"],
            must_have_coverage=coverage,
            critical_gaps=gaps,
            role_fit=70,
            auto_eliminate=False,
        )
        self.assertEqual(verdict, "evaluate")


if __name__ == "__main__":
    unittest.main()
