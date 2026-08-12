import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app.compensation.core import CompensationSettings, get_settings
from app.compensation.domain.schemas import CompensationResearchRequest
from app.compensation.services.orchestrator import CompensationResearchOrchestrator
from app.business_settings import normalize_business_settings


def _minimal_cached_payload() -> dict:
    return {
        "research_id": "abc123",
        "profile": {"normalized_role": "Cloud Architect", "seniority": "senior"},
        "market": {"currency": "BRL", "unit": "hour", "contract_type": "PJ"},
        "sample": {"observations": 1, "sources": 1},
        "providers": {"search_engines_used": ["tavily"], "crawlers_used": []},
        "confidence": {"score": 0.5, "level": "MEDIUM"},
        "sources": [],
        "warnings": [],
        "observations": [],
        "created_at": "2026-01-01T00:00:00+00:00",
    }


class CacheTtlTest(unittest.TestCase):
    def test_required_seed_adds_cache_ttl_days(self):
        settings = normalize_business_settings(
            {
                "parameters": [
                    {
                        "id": "1",
                        "key": "clt_to_pj_factor",
                        "label": "Fator",
                        "value": 1.5,
                        "value_type": "number",
                        "category": "compensation",
                        "description": "",
                        "inject_in_prompts": True,
                    }
                ]
            }
        )
        self.assertEqual(settings["values"]["cache_ttl_days"], 30)

    def test_get_settings_prefers_business_cache_ttl(self):
        with patch(
            "app.compensation.core._business_pricing",
            return_value={"cache_ttl_days": 45, "clt_to_pj_factor": 1.5, "work_hours_month": 168},
        ):
            settings = get_settings()
        self.assertEqual(settings.cache_ttl_days, 45)

    def test_read_cache_returns_none_when_older_than_ttl(self):
        request = CompensationResearchRequest(profile="Arquiteto de Soluções Cloud")
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "compensation_cache"
            cache_dir.mkdir(parents=True)
            orch = CompensationResearchOrchestrator.__new__(CompensationResearchOrchestrator)
            orch.settings = CompensationSettings(
                ollama_base_url="http://localhost",
                ollama_model="x",
                search_engines=["tavily"],
                enabled_crawlers=["generic"],
                clt_to_pj_factor=1.5,
                work_hours_month=168,
                max_parallel_searches=1,
                max_parallel_crawls=1,
                cache_ttl_days=30,
                http_timeout_seconds=10,
                playwright_timeout_seconds=20,
                research_timeout_seconds=120,
                app_api_key="",
            )
            path = cache_dir / f"{orch._cache_key(request)}.json"
            path.write_text(json.dumps(_minimal_cached_payload()), encoding="utf-8")
            # Age the file beyond 30 days
            old = datetime.now(timezone.utc).timestamp() - (31 * 86400)
            os.utime(path, (old, old))

            with patch("app.compensation.services.orchestrator.DATA_DIR", Path(tmp)):
                result = orch._read_cache(request)
            self.assertIsNone(result)

    def test_read_cache_hit_within_ttl(self):
        request = CompensationResearchRequest(profile="Arquiteto de Soluções Cloud")
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "compensation_cache"
            cache_dir.mkdir(parents=True)
            orch = CompensationResearchOrchestrator.__new__(CompensationResearchOrchestrator)
            orch.settings = CompensationSettings(
                ollama_base_url="http://localhost",
                ollama_model="x",
                search_engines=["tavily"],
                enabled_crawlers=["generic"],
                clt_to_pj_factor=1.5,
                work_hours_month=168,
                max_parallel_searches=1,
                max_parallel_crawls=1,
                cache_ttl_days=30,
                http_timeout_seconds=10,
                playwright_timeout_seconds=20,
                research_timeout_seconds=120,
                app_api_key="",
            )
            path = cache_dir / f"{orch._cache_key(request)}.json"
            path.write_text(json.dumps(_minimal_cached_payload()), encoding="utf-8")

            with patch("app.compensation.services.orchestrator.DATA_DIR", Path(tmp)):
                result = orch._read_cache(request)
            self.assertIsNotNone(result)
            self.assertEqual(result.research_id, "abc123")


if __name__ == "__main__":
    unittest.main()
