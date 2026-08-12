from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.llm import LocalLLM, OpenAILLM, active_llm_provider, get_llm
from app.llm_usage import (
    aggregate_usage,
    estimate_cost_usd,
    record_usage_event,
    summarize_usage,
    summarize_usage_for_provider,
    usage_from_audit_payload,
)


class LlmFactoryTests(unittest.TestCase):
    def test_active_provider_override_and_default(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "local"}, clear=False):
            self.assertEqual(active_llm_provider(None), "local")
            self.assertEqual(active_llm_provider("openai"), "openai")
            self.assertEqual(active_llm_provider("LOCAL"), "local")
            self.assertEqual(active_llm_provider("bogus"), "local")

    def test_get_llm_resolves_classes(self):
        local = get_llm("local")
        openai = get_llm("openai")
        self.assertEqual(local.provider_name, "local")
        self.assertEqual(openai.provider_name, "openai")
        self.assertEqual(openai.model, os.getenv("OPENAI_MODEL") or "gpt-4.1")


class LlmUsageCostTests(unittest.TestCase):
    def test_estimate_cost_gpt_41(self):
        # 1M in + 1M out at 2.00 / 8.00
        cost = estimate_cost_usd("gpt-4.1", 1_000_000, 1_000_000)
        self.assertAlmostEqual(cost, 10.0, places=5)

    def test_estimate_cost_mini_table(self):
        with patch.dict(
            os.environ,
            {"OPENAI_PRICE_INPUT_PER_1M": "", "OPENAI_PRICE_OUTPUT_PER_1M": ""},
            clear=False,
        ):
            # Ensure empty env does not override table prices for known mini models.
            os.environ.pop("OPENAI_PRICE_INPUT_PER_1M", None)
            os.environ.pop("OPENAI_PRICE_OUTPUT_PER_1M", None)
            cost = estimate_cost_usd("gpt-4.1-mini", 1_000_000, 0)
            self.assertAlmostEqual(cost, 0.40, places=5)
            cost_out = estimate_cost_usd("gpt-4o-mini", 0, 1_000_000)
            self.assertAlmostEqual(cost_out, 0.60, places=5)

    def test_local_cost_defaults_to_zero(self):
        cost = estimate_cost_usd("qwen2.5:14b", 100_000, 50_000, provider="local")
        self.assertEqual(cost, 0.0)

    def test_summarize_filters_by_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "usage.jsonl"
            record_usage_event(
                provider="openai",
                model="gpt-4.1",
                operation="score_skills",
                prompt_tokens=100,
                completion_tokens=20,
                path=path,
            )
            record_usage_event(
                provider="local",
                model="qwen2.5:14b",
                operation="score_skills",
                prompt_tokens=200,
                completion_tokens=40,
                estimated_cost_usd=0.0,
                path=path,
            )
            local = summarize_usage_for_provider("local", path=path)
            openai = summarize_usage_for_provider("openai", path=path)
            self.assertEqual(local["event_count"], 1)
            self.assertEqual(local["totals"]["prompt_tokens"], 200)
            self.assertEqual(openai["event_count"], 1)
            self.assertEqual(openai["totals"]["prompt_tokens"], 100)
            all_summary = summarize_usage(path=path)
            self.assertIn("local", all_summary["by_provider"])
            self.assertIn("openai", all_summary["by_provider"])

    def test_aggregate_and_summarize(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "usage.jsonl"
            record_usage_event(
                provider="openai",
                model="gpt-4.1",
                operation="score_skills",
                prompt_tokens=1000,
                completion_tokens=200,
                path=path,
            )
            record_usage_event(
                provider="openai",
                model="gpt-4.1",
                operation="score_fit",
                prompt_tokens=500,
                completion_tokens=100,
                path=path,
            )
            summary = summarize_usage(path=path)
            self.assertEqual(summary["event_count"], 2)
            self.assertEqual(summary["totals"]["prompt_tokens"], 1500)
            self.assertEqual(summary["totals"]["completion_tokens"], 300)
            self.assertIn("score_skills", summary["by_operation"])
            self.assertIn("gpt-4.1", summary["by_model"])

    def test_usage_from_audit_and_aggregate(self):
        part = usage_from_audit_payload(
            {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "estimated_cost_usd": 0.001,
            }
        )
        total = aggregate_usage(part, part)
        self.assertEqual(total["calls"], 2)
        self.assertEqual(total["total_tokens"], 30)


class OpenAiClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_without_api_key_returns_none(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            client = OpenAILLM()
            self.assertFalse(client.configured)
            result = await client.json_completion_with_audit("sys", "user")
            self.assertIsNone(result)

    async def test_json_completion_captures_usage(self):
        payload = {
            "choices": [{"message": {"content": json.dumps({"ok": True})}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15},
        }
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = payload

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with tempfile.TemporaryDirectory() as tmp:
            usage_path = Path(tmp) / "usage.jsonl"
            with patch.dict(
                os.environ,
                {"OPENAI_API_KEY": "sk-test", "OPENAI_MODEL": "gpt-4.1"},
                clear=False,
            ), patch("httpx.AsyncClient", return_value=mock_client), patch(
                "app.llm_usage.USAGE_LOG_PATH", usage_path
            ):
                client = OpenAILLM()
                result = await client.json_completion_with_audit(
                    "sys",
                    "user",
                    operation="analyse_job",
                    job_id="job-1",
                )

            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["parsed"], {"ok": True})
            self.assertEqual(result["prompt_tokens"], 12)
            self.assertEqual(result["completion_tokens"], 3)
            self.assertEqual(result["provider"], "openai")
            self.assertGreater(result["estimated_cost_usd"], 0)
            self.assertTrue(usage_path.is_file())
            events = [
                json.loads(line)
                for line in usage_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["operation"], "analyse_job")
            self.assertEqual(events[0]["job_id"], "job-1")


class GptEvaluateProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.pop("PROFESSIONAL_PROFILE_API_KEY", None)
        from fastapi.testclient import TestClient
        from app.main import app

        cls.client = TestClient(app)

    def test_evaluate_accepts_llm_provider(self):
        jobs = self.client.get("/api/gpt/jobs", params={"q": "OIC"}).json()["jobs"]
        candidates = self.client.get("/api/gpt/candidates", params={"q": "Bruno"}).json()["candidates"]
        with patch("app.main.run_score_task", new_callable=AsyncMock) as mocked:
            response = self.client.post(
                "/api/gpt/evaluations",
                json={
                    "job_id": jobs[0]["id"],
                    "candidate_id": candidates[0]["id"],
                    "llm_provider": "local",
                    "scoring_model": "v2",
                },
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body.get("llm_provider"), "local")
        self.assertIn("default_llm_provider", body)
        self.assertIn("task_id", body)
        mocked.assert_called()
        kwargs = mocked.call_args.kwargs
        self.assertEqual(kwargs.get("llm_provider"), "local")
        self.assertEqual(kwargs.get("scoring_model"), "v2")

    def test_llm_usage_endpoint(self):
        response = self.client.get("/api/llm/usage")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("totals", body)
        self.assertIn("by_operation", body)


class LocalLlmClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_json_completion_meters_ollama_tokens(self):
        payload = {
            "response": json.dumps({"ok": True}),
            "prompt_eval_count": 111,
            "eval_count": 22,
        }
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = payload

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with tempfile.TemporaryDirectory() as tmp:
            usage_path = Path(tmp) / "usage.jsonl"
            with patch.dict(
                os.environ,
                {"LOCAL_LLM_URL": "http://gpu-server-01:11434", "LOCAL_LLM_MODEL": "qwen2.5:14b"},
                clear=False,
            ), patch("httpx.AsyncClient", return_value=mock_client), patch(
                "app.llm_usage.USAGE_LOG_PATH", usage_path
            ):
                client = LocalLLM()
                result = await client.json_completion_with_audit(
                    "sys",
                    "user",
                    operation="score_skills",
                    job_id="job-1",
                    candidate_id="cand-1",
                )

            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["parsed"], {"ok": True})
            self.assertEqual(result["prompt_tokens"], 111)
            self.assertEqual(result["completion_tokens"], 22)
            self.assertEqual(result["provider"], "local")
            self.assertEqual(result["estimated_cost_usd"], 0.0)
            events = [
                json.loads(line)
                for line in usage_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["provider"], "local")
            self.assertEqual(events[0]["operation"], "score_skills")
            self.assertEqual(events[0]["total_tokens"], 133)


if __name__ == "__main__":
    unittest.main()
