from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock

from app.services import analyse_job


class AnalyseJobProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_openai_provider_uses_openai_prompts_and_v3_policy(self):
        llm = MagicMock()
        llm.provider_name = "openai"
        llm.model = "gpt-4.1"
        llm.temperature = 0.1
        llm.json_completion_with_audit = AsyncMock(
            return_value={
                "parsed": {
                    "role_intent": "Arquiteto OIC",
                    "must_have": [
                        {"name": "Oracle Integration Cloud", "weight": 10, "tier": "MUST_HAVE", "group": "OIC"}
                    ],
                    "core_skills": [
                        {"name": "Arquitetura de Integração", "weight": 8, "tier": "CORE", "group": "Architecture"}
                    ],
                    "supporting_skills": [],
                    "differentials": [],
                    "soft_skills": [{"name": "Comunicação", "weight": 4, "tier": "SOFT"}],
                    "skill_groups": [],
                },
                "prompt_tokens": 200,
                "completion_tokens": 80,
                "total_tokens": 280,
                "estimated_cost_usd": 0.0012,
                "attempts": 1,
                "error": None,
            }
        )
        result = await analyse_job(
            {
                "id": "job-1",
                "title": "Arquiteto OIC",
                "profile": "Arquiteto",
                "seniority": "Senior",
                "description": "OIC",
                "job_description": "Requisitos: Oracle Integration Cloud, arquitetura de integração.",
            },
            llm,
        )
        self.assertEqual(result["prompt_set"], "openai")
        self.assertEqual(result["weight_policy"], "v3")
        self.assertEqual(result["llm_provider"], "openai")
        self.assertEqual(result["core_skills"][0]["weight"], 8)
        self.assertIn("usage", result["audit"])
        self.assertAlmostEqual(result["audit"]["usage"]["estimated_cost_usd"], 0.0012)
        called_system = llm.json_completion_with_audit.await_args.args[0]
        self.assertIn("calibração", called_system.lower())

    async def test_local_provider_uses_legacy_prompts(self):
        llm = MagicMock()
        llm.provider_name = "local"
        llm.model = "qwen2.5:14b"
        llm.temperature = 0.1
        llm.json_completion_with_audit = AsyncMock(
            return_value={
                "parsed": {
                    "must_have": [{"name": "OIC", "weight": 10, "tier": "MUST_HAVE"}],
                    "core_skills": [{"name": "REST", "weight": 7, "tier": "CORE"}],
                    "supporting_skills": [],
                    "differentials": [],
                    "soft_skills": [],
                },
                "attempts": 1,
                "error": None,
            }
        )
        result = await analyse_job(
            {
                "id": "job-2",
                "title": "OIC",
                "profile": "Arquiteto",
                "seniority": "Senior",
                "description": "x",
                "job_description": "OIC e REST",
            },
            llm,
        )
        self.assertEqual(result["prompt_set"], "local")
        self.assertEqual(result["weight_policy"], "v2")
        self.assertEqual(result["audit"]["prompt_files"][0], "analyse_job.system.txt")


if __name__ == "__main__":
    unittest.main()
