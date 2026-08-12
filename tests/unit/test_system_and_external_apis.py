import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.external_api_usage import _next_month_start, _pct, fetch_firecrawl_usage, fetch_tavily_usage
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


if __name__ == "__main__":
    unittest.main()
