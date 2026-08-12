from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.job_understanding import (
    flatten_skills_v2,
    normalize_job_analysis,
    normalize_weight_policy,
)
from app.prompts import load_prompt
from app.scoring_config import active_scoring_model, clamp_tier_weight
from app.services import recalibrate_skill_weights, score_candidate


BASELINE = {
    "role_intent": "Arquiteto OIC",
    "must_have": [{"name": "Oracle Integration Cloud", "weight": 10, "tier": "MUST_HAVE", "group": "OIC"}],
    "core_skills": [
        {"name": "Arquitetura de Integração", "weight": 7, "tier": "CORE", "group": "Architecture"},
        {"name": "API Management", "weight": 7, "tier": "CORE", "group": "API"},
    ],
    "supporting_skills": [{"name": "Observabilidade", "weight": 3, "tier": "SUPPORTING", "group": "Ops"}],
    "differentials": [{"name": "Kafka", "weight": 2, "tier": "DIFFERENTIAL", "group": "Messaging"}],
    "soft_skills": [{"name": "Comunicação", "weight": 3, "tier": "SOFT", "group": "Behavioral"}],
    "skill_groups": [{"name": "OIC", "skills": ["Oracle Integration Cloud"]}],
}


class WeightPolicyV3Tests(unittest.TestCase):
    def test_openai_prompts_load_from_subdir(self):
        system = load_prompt("openai/score_weights.system.txt")
        user = load_prompt("openai/score_weights.user.txt", current_skills_json="[]", title="t")
        self.assertIn("RECALIBRAR", system.upper())
        self.assertIn("current_skills", user)
        analyse_system = load_prompt("openai/analyse_job.system.txt")
        self.assertIn("pesos", analyse_system.lower())

    def test_normalize_preserves_openai_discriminative_weights(self):
        analysis = normalize_job_analysis(
            {
                "must_have": [{"name": "OIC", "weight": 10}],
                "core_skills": [{"name": "Arquitetura", "weight": 8}],
                "supporting_skills": [],
                "differentials": [],
                "soft_skills": [],
            },
            policy="v3",
        )
        self.assertEqual(analysis["core_skills"][0]["weight"], 8)
        crushed = normalize_job_analysis(analysis, policy="v2")
        self.assertEqual(crushed["core_skills"][0]["weight"], 7)

    def test_clamp_v3_allows_discriminative_core(self):
        self.assertEqual(clamp_tier_weight("CORE", 8, policy="v3"), 8)
        self.assertEqual(clamp_tier_weight("CORE", 8, policy="v2"), 7)
        self.assertEqual(clamp_tier_weight("MUST_HAVE", 7, policy="v3"), 7)
        self.assertEqual(clamp_tier_weight("MUST_HAVE", 7, policy="v2"), 8)

    def test_normalize_weight_policy_rejects_invented_skills(self):
        baseline = normalize_job_analysis(BASELINE)
        result = normalize_weight_policy(
            {
                "must_have": [
                    {"name": "Oracle Integration Cloud", "weight": 10, "tier": "MUST_HAVE"},
                    {"name": "Skill Inventada", "weight": 10, "tier": "MUST_HAVE"},
                ],
                "core_skills": [
                    {"name": "Arquitetura de Integração", "weight": 8, "tier": "CORE"},
                    {"name": "API Management", "weight": 5, "tier": "CORE"},
                ],
                "supporting_skills": [{"name": "Observabilidade", "weight": 4, "tier": "SUPPORTING"}],
                "differentials": [{"name": "Kafka", "weight": 2, "tier": "DIFFERENTIAL"}],
                "soft_skills": [{"name": "Comunicação", "weight": 5, "tier": "SOFT"}],
            },
            baseline=baseline,
            policy="v3",
        )
        names = {s["name"] for s in flatten_skills_v2(result)}
        self.assertNotIn("Skill Inventada", names)
        self.assertIn("Oracle Integration Cloud", names)
        self.assertIn("API Management", names)
        arch = next(s for s in flatten_skills_v2(result) if s["name"] == "Arquitetura de Integração")
        self.assertEqual(arch["weight"], 8)

    def test_normalize_weight_policy_keeps_omitted_baseline_skills(self):
        baseline = normalize_job_analysis(BASELINE)
        result = normalize_weight_policy(
            {
                "must_have": [{"name": "Oracle Integration Cloud", "weight": 9, "tier": "MUST_HAVE"}],
                "core_skills": [],
                "supporting_skills": [],
                "differentials": [],
                "soft_skills": [],
            },
            baseline=baseline,
            policy="v3",
        )
        names = {s["name"] for s in flatten_skills_v2(result)}
        self.assertIn("Kafka", names)
        self.assertIn("Comunicação", names)
        oic = next(s for s in flatten_skills_v2(result) if s["name"] == "Oracle Integration Cloud")
        self.assertEqual(oic["weight"], 9)

    def test_normalize_weight_policy_allows_tier_move(self):
        baseline = normalize_job_analysis(BASELINE)
        result = normalize_weight_policy(
            {
                "must_have": [
                    {"name": "Oracle Integration Cloud", "weight": 10, "tier": "MUST_HAVE"},
                    {"name": "Arquitetura de Integração", "weight": 9, "tier": "MUST_HAVE"},
                ],
                "core_skills": [{"name": "API Management", "weight": 6, "tier": "CORE"}],
                "supporting_skills": [{"name": "Observabilidade", "weight": 3, "tier": "SUPPORTING"}],
                "differentials": [{"name": "Kafka", "weight": 2, "tier": "DIFFERENTIAL"}],
                "soft_skills": [{"name": "Comunicação", "weight": 4, "tier": "SOFT"}],
            },
            baseline=baseline,
            policy="v3",
        )
        arch = next(s for s in flatten_skills_v2(result) if s["name"] == "Arquitetura de Integração")
        self.assertEqual(arch["tier"], "MUST_HAVE")
        self.assertEqual(arch["weight"], 9)

    def test_active_scoring_model_accepts_v3(self):
        self.assertEqual(active_scoring_model("v3"), "v3")
        self.assertEqual(active_scoring_model("V3"), "v3")


class RecalibrateWeightsTests(unittest.IsolatedAsyncioTestCase):
    async def test_recalibrate_applies_mock_openai_weights(self):
        llm = MagicMock()
        llm.configured = True
        llm.provider_name = "openai"
        llm.model = "gpt-4.1"
        llm.temperature = 0.1
        llm.json_completion_with_audit = AsyncMock(
            return_value={
                "parsed": {
                    "must_have": [
                        {"name": "Oracle Integration Cloud", "weight": 10, "tier": "MUST_HAVE", "group": "OIC"}
                    ],
                    "core_skills": [
                        {"name": "Arquitetura de Integração", "weight": 8, "tier": "CORE", "group": "Architecture"},
                        {"name": "API Management", "weight": 5, "tier": "CORE", "group": "API"},
                    ],
                    "supporting_skills": [
                        {"name": "Observabilidade", "weight": 4, "tier": "SUPPORTING", "group": "Ops"}
                    ],
                    "differentials": [{"name": "Kafka", "weight": 2, "tier": "DIFFERENTIAL", "group": "Messaging"}],
                    "soft_skills": [{"name": "Comunicação", "weight": 5, "tier": "SOFT", "group": "Behavioral"}],
                },
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
                "estimated_cost_usd": 0.001,
                "attempts": 1,
                "error": None,
            }
        )
        job = {"id": "j1", "title": "Arquiteto OIC", "job_description": "OIC"}
        analysis, policy = await recalibrate_skill_weights(
            job, BASELINE, job_id="j1", candidate_id="c1", llm=llm
        )
        arch = next(s for s in flatten_skills_v2(analysis) if s["name"] == "Arquitetura de Integração")
        self.assertEqual(arch["weight"], 8)
        self.assertEqual(policy["source"], "openai")
        self.assertEqual(len(policy["items_before"]), len(policy["items_after"]))
        llm.json_completion_with_audit.assert_awaited()
        call_kwargs = llm.json_completion_with_audit.await_args.kwargs
        self.assertEqual(call_kwargs.get("operation"), "score_weights")

    async def test_recalibrate_fails_without_configured_llm(self):
        llm = MagicMock()
        llm.configured = False
        llm.provider_name = "openai"
        with self.assertRaises(ValueError) as ctx:
            await recalibrate_skill_weights({"id": "j1"}, BASELINE, llm=llm)
        self.assertIn("OPENAI_API_KEY", str(ctx.exception))

    async def test_recalibrate_uses_selected_local_provider(self):
        llm = MagicMock()
        llm.configured = True
        llm.provider_name = "local"
        llm.model = "qwen2.5:14b"
        llm.temperature = 0.1
        llm.json_completion_with_audit = AsyncMock(
            return_value={
                "parsed": {
                    "must_have": [
                        {"name": "Oracle Integration Cloud", "weight": 10, "tier": "MUST_HAVE", "group": "OIC"}
                    ],
                    "core_skills": [
                        {"name": "Arquitetura de Integração", "weight": 8, "tier": "CORE", "group": "Architecture"},
                        {"name": "API Management", "weight": 5, "tier": "CORE", "group": "API"},
                    ],
                    "supporting_skills": [
                        {"name": "Observabilidade", "weight": 4, "tier": "SUPPORTING", "group": "Ops"}
                    ],
                    "differentials": [{"name": "Kafka", "weight": 2, "tier": "DIFFERENTIAL", "group": "Messaging"}],
                    "soft_skills": [{"name": "Comunicação", "weight": 5, "tier": "SOFT", "group": "Behavioral"}],
                },
                "attempts": 1,
                "error": None,
            }
        )
        analysis, policy = await recalibrate_skill_weights(
            {"id": "j1", "title": "OIC"}, BASELINE, llm=llm
        )
        self.assertEqual(policy["source"], "local")
        self.assertEqual(policy["llm_provider"], "local")
        arch = next(s for s in flatten_skills_v2(analysis) if s["name"] == "Arquitetura de Integração")
        self.assertEqual(arch["weight"], 8)

    async def test_score_candidate_v3_uses_recalibrated_weights(self):
        baseline = normalize_job_analysis(BASELINE)
        job = {
            "id": "job-1",
            "title": "Arquiteto OIC",
            "analysis": baseline,
            "job_description": "Oracle Integration Cloud",
        }
        candidate = {
            "id": "cand-1",
            "name": "Maria",
            "resume_text": "Experiência forte em Oracle Integration Cloud e arquitetura de integração.",
        }

        scoring_llm = MagicMock()
        scoring_llm.provider_name = "local"
        scoring_llm.model = "qwen"
        scoring_llm.temperature = 0.1
        scoring_llm.configured = True

        async def fake_recalibrate(job_arg, analysis_arg, **kwargs):
            recalibrated = normalize_weight_policy(
                {
                    "must_have": [
                        {"name": "Oracle Integration Cloud", "weight": 10, "tier": "MUST_HAVE", "group": "OIC"}
                    ],
                    "core_skills": [
                        {
                            "name": "Arquitetura de Integração",
                            "weight": 8,
                            "tier": "CORE",
                            "group": "Architecture",
                        },
                        {"name": "API Management", "weight": 5, "tier": "CORE", "group": "API"},
                    ],
                    "supporting_skills": [
                        {"name": "Observabilidade", "weight": 4, "tier": "SUPPORTING", "group": "Ops"}
                    ],
                    "differentials": [
                        {"name": "Kafka", "weight": 2, "tier": "DIFFERENTIAL", "group": "Messaging"}
                    ],
                    "soft_skills": [
                        {"name": "Comunicação", "weight": 5, "tier": "SOFT", "group": "Behavioral"}
                    ],
                },
                baseline=analysis_arg,
                policy="v3",
            )
            return recalibrated, {
                "source": "openai",
                "prompt_version": "v1",
                "items_before": [],
                "items_after": [],
                "llm_model": "gpt-4.1",
            }

        with patch("app.services.recalibrate_skill_weights", side_effect=fake_recalibrate):
            with patch(
                "app.services._score_skills_with_llm",
                new=AsyncMock(
                    return_value=(
                        [
                            {
                                "name": s["name"],
                                "score": 4,
                                "confidence": 0.8,
                                "evidence_status": "explicit",
                                "evidence": [{"text": "cv", "source": "resume"}],
                            }
                            for s in flatten_skills_v2(baseline)
                        ],
                        "llm",
                        [],
                    )
                ),
            ):
                with patch(
                    "app.services._score_fit_with_llm",
                    new=AsyncMock(
                        return_value={
                            "role_fit": 70,
                            "context_fit": 60,
                            "strengths": [],
                            "gaps": [],
                            "interview_validation": [],
                            "audit": {},
                        }
                    ),
                ):
                    with patch(
                        "app.services._score_narrative_with_llm",
                        new=AsyncMock(return_value=({}, {})),
                    ):
                        result = await score_candidate(
                            job, candidate, scoring_llm, scoring_model="v3"
                        )

        self.assertEqual(result["scoring_model_version"], "v3")
        self.assertEqual(result["audit"]["scoring_model_version"], "v3")
        self.assertEqual(result["audit"]["weight_policy"]["source"], "openai")
        arch = next(i for i in result["items"] if i["name"] == "Arquitetura de Integração")
        self.assertEqual(arch["weight"], 8)
        # Job analysis on disk must remain untouched by score_candidate.
        self.assertEqual(
            next(s for s in job["analysis"]["core_skills"] if s["name"] == "Arquitetura de Integração")[
                "weight"
            ],
            7,
        )


class GptEvaluateV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import os

        os.environ.pop("PROFESSIONAL_PROFILE_API_KEY", None)
        from fastapi.testclient import TestClient
        from app.main import app

        cls.client = TestClient(app)

    def test_evaluate_accepts_scoring_model_v3(self):
        jobs = self.client.get("/api/gpt/jobs").json()["jobs"]
        candidates = self.client.get("/api/gpt/candidates").json()["candidates"]
        if not jobs or not candidates:
            self.skipTest("no jobs/candidates fixtures")
        with patch("app.main.run_score_task", new_callable=AsyncMock) as mocked:
            response = self.client.post(
                "/api/gpt/evaluations",
                json={
                    "job_id": jobs[0]["id"],
                    "candidate_id": candidates[0]["id"],
                    "scoring_model": "v3",
                    "llm_provider": "local",
                },
            )
        self.assertEqual(response.status_code, 200)
        kwargs = mocked.call_args.kwargs
        self.assertEqual(kwargs.get("scoring_model"), "v3")


if __name__ == "__main__":
    unittest.main()
