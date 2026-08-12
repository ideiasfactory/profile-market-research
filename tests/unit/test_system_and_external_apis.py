import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.external_api_usage import (
    _next_month_start,
    _pct,
    fetch_firecrawl_usage,
    fetch_openai_usage,
    fetch_tavily_usage,
)
from app.storage import JsonStore
from app.system_settings import mask_secret, save_system_settings


class SystemSettingsTest(unittest.TestCase):
    def test_mask_secret(self):
        self.assertEqual(mask_secret(""), "")
        self.assertTrue(mask_secret("tvly-abcdefghijklmnop").endswith("mnop"))

    def test_save_keeps_secret_when_blank(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonStore(
                Path(tmp) / "system_settings.json",
                {"values": {"TAVILY_API_KEY": "tvly-secret-key"}, "updated_at": None},
            )
            with patch("app.system_settings.system_settings_store", store):
                save_system_settings({"TAVILY_API_KEY": "", "OLLAMA_MODEL": "qwen2.5:14b"})
                saved = store.read()
            self.assertEqual(saved["values"]["TAVILY_API_KEY"], "tvly-secret-key")
            self.assertEqual(saved["values"]["OLLAMA_MODEL"], "qwen2.5:14b")


class ExternalApiUsageTest(unittest.IsolatedAsyncioTestCase):
    def test_next_month_start(self):
        self.assertTrue(_next_month_start(date(2026, 8, 12)).startswith("2026-09-01"))
        self.assertTrue(_next_month_start(date(2026, 12, 31)).startswith("2027-01-01"))

    def test_pct(self):
        self.assertEqual(_pct(250, 1000), 25.0)
        self.assertIsNone(_pct(10, None))

    async def test_tavily_usage_maps_plan(self):
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = lambda: None
        mock_response.json = lambda: {
            "key": {"usage": 10, "limit": 1000, "search_usage": 8},
            "account": {
                "current_plan": "Researcher",
                "plan_usage": 100,
                "plan_limit": 1000,
                "search_usage": 80,
            },
        }
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get.return_value = mock_response
        with patch(
            "app.external_api_usage.get_system_value",
            side_effect=lambda k, d="": "tvly-x" if "KEY" in k else (d or "https://api.tavily.com"),
        ):
            with patch("app.external_api_usage.httpx.AsyncClient", return_value=mock_client):
                result = await fetch_tavily_usage()
        self.assertTrue(result["ok"])
        self.assertEqual(result["plan_name"], "Researcher")
        self.assertEqual(result["limit"], 1000)
        self.assertEqual(result["used"], 100)
        self.assertEqual(result["remaining"], 900)
        self.assertIn("1º dia", result["reset_note"])

    async def test_firecrawl_usage_maps_credits(self):
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = lambda: None
        mock_response.json = lambda: {
            "success": True,
            "data": {
                "remaining_credits": 700,
                "plan_credits": 1000,
                "billing_period_start": "2026-08-01T00:00:00Z",
                "billing_period_end": "2026-08-31T23:59:59Z",
            },
        }
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get.return_value = mock_response
        with patch(
            "app.external_api_usage.get_system_value",
            side_effect=lambda k, d="": "fc-x" if "KEY" in k else (d or "https://api.firecrawl.dev"),
        ):
            with patch("app.external_api_usage.httpx.AsyncClient", return_value=mock_client):
                result = await fetch_firecrawl_usage()
        self.assertTrue(result["ok"])
        self.assertEqual(result["remaining"], 700)
        self.assertEqual(result["limit"], 1000)
        self.assertEqual(result["used"], 300)
        self.assertEqual(result["period_end"], "2026-08-31T23:59:59Z")

    def test_openai_usage_from_local_log(self):
        with patch.dict(
            "os.environ",
            {"OPENAI_API_KEY": "sk-test", "OPENAI_MODEL": "gpt-4.1", "LLM_PROVIDER": "openai"},
            clear=False,
        ), patch("app.external_api_usage.summarize_usage") as mocked:
            mocked.return_value = {
                "event_count": 1,
                "totals": {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "total_tokens": 120,
                    "estimated_cost_usd": 0.0004,
                    "calls": 1,
                    "ok_calls": 1,
                },
                "by_operation": {
                    "score_skills": {
                        "prompt_tokens": 100,
                        "completion_tokens": 20,
                        "total_tokens": 120,
                        "estimated_cost_usd": 0.0004,
                        "calls": 1,
                        "ok_calls": 1,
                    }
                },
                "by_model": {
                    "gpt-4.1": {
                        "prompt_tokens": 100,
                        "completion_tokens": 20,
                        "total_tokens": 120,
                        "estimated_cost_usd": 0.0004,
                        "calls": 1,
                        "ok_calls": 1,
                    }
                },
                "by_day": {
                    "2026-08-12": {
                        "prompt_tokens": 100,
                        "completion_tokens": 20,
                        "total_tokens": 120,
                        "estimated_cost_usd": 0.0004,
                        "calls": 1,
                        "ok_calls": 1,
                    }
                },
            }
            result = fetch_openai_usage()
        self.assertEqual(result["provider"], "openai")
        self.assertEqual(result["kind"], "llm_tokens")
        self.assertTrue(result["configured"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["totals"]["total_tokens"], 120)
        self.assertEqual(result["by_operation"][0]["name"], "score_skills")
        self.assertEqual(result["by_model"][0]["name"], "gpt-4.1")
        self.assertEqual(result["by_day"][0]["name"], "2026-08-12")

    def test_openai_usage_key_missing_still_ok(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=False), patch(
            "app.external_api_usage.summarize_usage",
            return_value={
                "event_count": 0,
                "totals": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "estimated_cost_usd": 0.0,
                    "calls": 0,
                    "ok_calls": 0,
                },
                "by_operation": {},
                "by_model": {},
                "by_day": {},
            },
        ):
            result = fetch_openai_usage()
        self.assertFalse(result["configured"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["event_count"], 0)


class ExternalApisHttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from fastapi.testclient import TestClient
        from app.main import app

        cls.client = TestClient(app)

    def test_external_apis_page_includes_openai(self):
        with patch(
            "app.main.fetch_all_external_api_usage",
            new_callable=AsyncMock,
            return_value={
                "fetched_at": "2026-08-12T12:00:00+00:00",
                "providers": [
                    {
                        "provider": "tavily",
                        "configured": False,
                        "ok": False,
                        "error": "API key não configurada",
                    },
                    {
                        "provider": "firecrawl",
                        "configured": False,
                        "ok": False,
                        "error": "API key não configurada",
                    },
                    {
                        "provider": "openai",
                        "kind": "llm_tokens",
                        "configured": True,
                        "ok": True,
                        "plan_name": "Chat Completions · modelo default gpt-4.1",
                        "includes": "Tokens e custo estimado",
                        "reset_note": "LLM_PROVIDER default: local.",
                        "docs_url": "/api/llm/usage",
                        "totals": {
                            "prompt_tokens": 10,
                            "completion_tokens": 5,
                            "total_tokens": 15,
                            "estimated_cost_usd": 0.0001,
                            "calls": 1,
                            "ok_calls": 1,
                        },
                        "by_operation": [
                            {
                                "name": "analyse_job",
                                "total_tokens": 15,
                                "estimated_cost_usd": 0.0001,
                                "calls": 1,
                            }
                        ],
                        "by_model": [
                            {
                                "name": "gpt-4.1",
                                "total_tokens": 15,
                                "estimated_cost_usd": 0.0001,
                                "calls": 1,
                            }
                        ],
                        "by_day": [
                            {
                                "name": "2026-08-12",
                                "total_tokens": 15,
                                "estimated_cost_usd": 0.0001,
                                "calls": 1,
                            }
                        ],
                        "event_count": 1,
                    },
                ],
            },
        ):
            response = self.client.get("/external-apis")
        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertIn("OpenAI", body)
        self.assertIn("Prompt tokens", body)
        self.assertIn("Por operação", body)
        self.assertIn("analyse_job", body)

    def test_external_apis_usage_json_includes_openai(self):
        with patch(
            "app.main.fetch_all_external_api_usage",
            new_callable=AsyncMock,
            return_value={
                "fetched_at": "2026-08-12T12:00:00+00:00",
                "providers": [
                    {"provider": "tavily", "ok": False, "configured": False},
                    {"provider": "firecrawl", "ok": False, "configured": False},
                    {
                        "provider": "openai",
                        "kind": "llm_tokens",
                        "ok": True,
                        "configured": True,
                        "totals": {"total_tokens": 15},
                    },
                ],
            },
        ):
            response = self.client.get("/api/v1/external-apis/usage")
        self.assertEqual(response.status_code, 200)
        providers = {p["provider"]: p for p in response.json()["providers"]}
        self.assertIn("openai", providers)
        self.assertEqual(providers["openai"]["kind"], "llm_tokens")


if __name__ == "__main__":
    unittest.main()
