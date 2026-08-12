from __future__ import annotations

import unittest

from app.job_understanding import flatten_skills_v2, normalize_job_analysis
from app.scoring_v2 import (
    classify_critical_gaps,
    compute_must_have_coverage,
    compute_score_breakdown,
    decide_verdict,
    weighted_dimension_pct,
)
from app.services import (
    _ground_skill_scores_to_resume,
    build_score,
    heuristic_skill_scores,
    normalize_text,
)


class JobUnderstandingTests(unittest.TestCase):
    def test_migrates_flat_v1_to_tiers(self):
        analysis = normalize_job_analysis(
            {
                "hard_skills": [
                    {"name": "Oracle Integration Cloud", "weight": 5},
                    {"name": "REST", "weight": 4},
                    {"name": "Observabilidade", "weight": 2},
                ],
                "soft_skills": [{"name": "Comunicação", "weight": 3}],
                "desired_skills": [{"name": "Kafka", "weight": 2}],
            }
        )
        self.assertTrue(analysis["must_have"])
        self.assertEqual(analysis["must_have"][0]["name"], "Oracle Integration Cloud")
        self.assertEqual(analysis["must_have"][0]["tier"], "MUST_HAVE")
        self.assertTrue(any(s["name"] == "REST" for s in analysis["core_skills"]))
        self.assertTrue(any(s["name"] == "Kafka" for s in analysis["differentials"]))
        self.assertTrue(analysis["hard_skills"])  # backward compat
        self.assertTrue(analysis["desired_skills"])

    def test_preserves_tiered_input(self):
        analysis = normalize_job_analysis(
            {
                "role_intent": "Arquiteto de integração OIC",
                "must_have": [{"name": "OIC", "weight": 10}],
                "core_skills": [{"name": "API Management", "weight": 7, "group": "API"}],
                "supporting_skills": [],
                "differentials": [],
                "soft_skills": [{"name": "Autonomia", "weight": 3}],
                "context_signals": ["CPFL"],
                "skill_groups": [{"name": "API", "skills": ["API Management"]}],
            }
        )
        self.assertEqual(analysis["role_intent"], "Arquiteto de integração OIC")
        self.assertEqual(analysis["context_signals"], ["CPFL"])
        self.assertEqual(analysis["must_have"][0]["weight"], 10)
        skills = flatten_skills_v2(analysis)
        self.assertTrue(any(s["tier"] == "MUST_HAVE" for s in skills))


class EvidenceAndSoftSkillTests(unittest.TestCase):
    def test_soft_skills_null_not_zero_in_v2(self):
        skills = [{"name": "Comunicação", "tier": "SOFT", "category": "Soft skill", "weight": 3}]
        scored = heuristic_skill_scores(skills, "Currículo sem menção comportamental.", model="v2")
        self.assertIsNone(scored[0]["score"])
        self.assertEqual(scored[0]["evidence_status"], "needs_validation")

    def test_soft_null_excluded_from_denominator(self):
        items = [
            {"name": "OIC", "score": 5, "weight": 10},
            {"name": "Comunicação", "score": None, "weight": 3},
        ]
        pct = weighted_dimension_pct(items)
        self.assertEqual(pct, 100.0)

    def test_grounding_rejects_ungrounded_tech_claim(self):
        scores = [
            {
                "name": "Oracle Integration Cloud",
                "score": 5,
                "confidence": 0.9,
                "evidence_status": "explicit",
                "evidence": [{"text": "Experiência avançada em OIC", "source": "resume"}],
            }
        ]
        # Resume mentions CPI only — not OIC.
        grounded = _ground_skill_scores_to_resume(
            scores,
            "Especialista em SAP CPI / Integration Suite e iFlows.",
            soft_null=True,
        )
        self.assertEqual(grounded[0]["score"], 0)
        self.assertEqual(grounded[0]["evidence_status"], "not_found")


class CompositeScoringTests(unittest.TestCase):
    def test_weighted_breakdown_uses_config_weights(self):
        items = [
            {"name": "OIC", "tier": "MUST_HAVE", "category": "Must-have", "score": 5, "weight": 10},
            {"name": "API Mgmt", "tier": "CORE", "category": "Core skill", "score": 4, "weight": 7},
            {"name": "Kafka", "tier": "DIFFERENTIAL", "category": "Differential", "score": 0, "weight": 2},
            {"name": "Comunicação", "tier": "SOFT", "category": "Soft skill", "score": 4, "weight": 3},
        ]
        breakdown = compute_score_breakdown(items, role_fit=80, context_fit=90)
        self.assertIn("dimensions", breakdown)
        self.assertGreater(breakdown["final_score"], 50)
        self.assertAlmostEqual(
            sum(breakdown["weights"].values()),
            1.0,
            places=5,
        )

    def test_must_have_coverage_and_critical_gap(self):
        items = [
            {
                "name": "Oracle Integration Cloud",
                "tier": "MUST_HAVE",
                "score": 0,
                "evidence_status": "not_found",
                "weight": 10,
            },
            {
                "name": "SAP PO",
                "tier": "CORE",
                "score": 4,
                "evidence_status": "explicit",
                "weight": 7,
            },
        ]
        coverage = compute_must_have_coverage(items)
        self.assertEqual(coverage["covered"], 0)
        self.assertEqual(coverage["total"], 1)
        gaps = classify_critical_gaps(items)
        self.assertTrue(any(g["severity"] == "critical" and g["name"] == "Oracle Integration Cloud" for g in gaps))

    def test_critical_gap_does_not_auto_eliminate(self):
        coverage = {"covered": 0, "total": 1, "ratio": 0.0}
        gaps = [{"name": "OIC", "severity": "critical"}]
        # Strong role + mid score → evaluate, not auto discard.
        verdict = decide_verdict(
            final_score=55,
            must_have_coverage=coverage,
            critical_gaps=gaps,
            role_fit=75,
            auto_eliminate=False,
        )
        self.assertEqual(verdict, "evaluate")

    def test_auto_eliminate_when_configured(self):
        verdict = decide_verdict(
            final_score=80,
            must_have_coverage={"covered": 0, "total": 1, "ratio": 0.0},
            critical_gaps=[{"name": "OIC", "severity": "critical"}],
            role_fit=90,
            auto_eliminate=True,
        )
        self.assertEqual(verdict, "not_recommended")

    def test_v1_build_score_still_works(self):
        job = {"id": "j1", "title": "Dev"}
        candidate = {"id": "c1", "name": "Ana"}
        skills = [{"category": "Hard skill", "name": "Python", "weight": 4}]
        scores = [{"name": "Python", "score": 5, "evidence": "Python no CV"}]
        built = build_score(job, candidate, skills, scores, "heuristic")
        self.assertEqual(built["scoring_model_version"], "v1")
        self.assertEqual(built["final_score"], 100.0)


class AntiEquivalenceHints(unittest.TestCase):
    def test_normalize_keeps_distinct_platforms(self):
        # Sanity: names remain distinct after normalize helpers used in matching.
        self.assertNotEqual(normalize_text("Oracle Integration Cloud"), normalize_text("SAP CPI"))
        self.assertIn("oic", normalize_text("Oracle Integration Cloud (OIC)"))


if __name__ == "__main__":
    unittest.main()
