from __future__ import annotations

import os
import unittest

from fastapi.testclient import TestClient

# Ensure auth is off for default unit tests.
os.environ.pop("PROFESSIONAL_PROFILE_API_KEY", None)

from app.main import app  # noqa: E402


class GptApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_list_jobs(self):
        response = self.client.get("/api/gpt/jobs")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertGreaterEqual(body["count"], 1)
        self.assertTrue(any("OIC" in (j.get("title") or "") for j in body["jobs"]))

    def test_search_jobs(self):
        response = self.client.get("/api/gpt/jobs", params={"q": "CPFL"})
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.json()["count"], 1)

    def test_get_job(self):
        listing = self.client.get("/api/gpt/jobs", params={"q": "OIC"}).json()
        job_id = listing["jobs"][0]["id"]
        response = self.client.get(f"/api/gpt/jobs/{job_id}")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("analysis", body)
        self.assertIn("must_have", body["analysis"])

    def test_get_job_not_found(self):
        response = self.client.get("/api/gpt/jobs/does-not-exist")
        self.assertEqual(response.status_code, 404)

    def test_list_and_get_candidate_without_resume_by_default(self):
        listing = self.client.get("/api/gpt/candidates", params={"q": "Bruno"}).json()
        self.assertGreaterEqual(listing["count"], 1)
        candidate_id = listing["candidates"][0]["id"]
        response = self.client.get(f"/api/gpt/candidates/{candidate_id}")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertNotIn("resume_text", body)
        self.assertTrue(body.get("resume_available"))

        with_resume = self.client.get(
            f"/api/gpt/candidates/{candidate_id}",
            params={"include_resume": True},
        )
        self.assertEqual(with_resume.status_code, 200)
        self.assertIn("resume_text", with_resume.json())

    def test_list_evaluations_and_detail(self):
        jobs = self.client.get("/api/gpt/jobs", params={"q": "OIC"}).json()["jobs"]
        job_id = jobs[0]["id"]
        response = self.client.get(f"/api/gpt/jobs/{job_id}/evaluations")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertGreaterEqual(body["count"], 1)
        evaluation_id = body["evaluations"][0]["evaluation_id"]
        detail = self.client.get(f"/api/gpt/evaluations/{evaluation_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertIn("final_score", detail.json())
        self.assertNotIn("items", detail.json())

        with_items = self.client.get(
            f"/api/gpt/evaluations/{evaluation_id}",
            params={"include_items": True},
        )
        self.assertIn("items", with_items.json())

    def test_list_job_candidates(self):
        jobs = self.client.get("/api/gpt/jobs", params={"q": "OIC"}).json()["jobs"]
        job_id = jobs[0]["id"]
        response = self.client.get(f"/api/gpt/jobs/{job_id}/candidates")
        self.assertEqual(response.status_code, 200)
        names = [c.get("name") for c in response.json()["candidates"]]
        self.assertTrue(any(name and "Bruno" in name for name in names))

    def test_get_task_not_found(self):
        response = self.client.get("/api/gpt/tasks/does-not-exist")
        self.assertEqual(response.status_code, 404)

    def test_api_key_required_when_configured(self):
        os.environ["PROFESSIONAL_PROFILE_API_KEY"] = "test-secret-key"
        try:
            denied = self.client.get("/api/gpt/jobs")
            self.assertEqual(denied.status_code, 401)
            allowed = self.client.get(
                "/api/gpt/jobs",
                headers={"Authorization": "Bearer test-secret-key"},
            )
            self.assertEqual(allowed.status_code, 200)
            allowed_header = self.client.get(
                "/api/gpt/jobs",
                headers={"X-API-Key": "test-secret-key"},
            )
            self.assertEqual(allowed_header.status_code, 200)
            denied_comp = self.client.get("/api/gpt/compensation/history")
            self.assertEqual(denied_comp.status_code, 401)
            allowed_comp = self.client.get(
                "/api/gpt/compensation/history",
                headers={"X-API-Key": "test-secret-key"},
            )
            self.assertEqual(allowed_comp.status_code, 200)
        finally:
            os.environ.pop("PROFESSIONAL_PROFILE_API_KEY", None)

    def test_compensation_prefill_from_job(self):
        jobs = self.client.get("/api/gpt/jobs", params={"q": "OIC"}).json()["jobs"]
        job_id = jobs[0]["id"]
        response = self.client.get(f"/api/gpt/compensation/prefill/{job_id}")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body.get("profile"))
        self.assertEqual(body.get("source_job_id"), job_id)
        self.assertIn("skills", body)
        self.assertIn("location", body)
        self.assertIn(body.get("target_contract"), ("CLT", "PJ"))

    def test_compensation_prefill_not_found(self):
        response = self.client.get("/api/gpt/compensation/prefill/does-not-exist")
        self.assertEqual(response.status_code, 404)

    def test_compensation_history_list_and_item(self):
        listing = self.client.get("/api/gpt/compensation/history")
        self.assertEqual(listing.status_code, 200)
        body = listing.json()
        self.assertIn("count", body)
        self.assertIn("items", body)
        if body["count"] == 0:
            missing = self.client.get("/api/gpt/compensation/history/does-not-exist")
            self.assertEqual(missing.status_code, 404)
            return

        cache_key = body["items"][0]["cache_key"]
        compact = self.client.get(f"/api/gpt/compensation/history/{cache_key}")
        self.assertEqual(compact.status_code, 200)
        compact_body = compact.json()
        self.assertTrue(compact_body.get("observations_omitted"))
        self.assertEqual(compact_body.get("observations"), [])
        self.assertIn("market", compact_body)

        full = self.client.get(
            f"/api/gpt/compensation/history/{cache_key}",
            params={"include_observations": True},
        )
        self.assertEqual(full.status_code, 200)
        full_body = full.json()
        self.assertFalse(full_body.get("observations_omitted"))
        self.assertIsInstance(full_body.get("observations"), list)

    def _fake_compensation_response(self):
        from datetime import datetime, timezone

        from app.compensation.domain.schemas import (
            CompensationResearchResponse,
            ConfidenceSummary,
            MarketStats,
            NormalizedProfile,
            ProviderSummary,
            SampleSummary,
        )

        return CompensationResearchResponse(
            research_id="test-research",
            profile=NormalizedProfile(normalized_role="Test Role"),
            market=MarketStats(),
            sample=SampleSummary(),
            providers=ProviderSummary(),
            confidence=ConfidenceSummary(score=0.1, level="LOW"),
            sources=[],
            warnings=["unit-test"],
            observations=[],
            created_at=datetime.now(timezone.utc),
        )

    def test_compensation_research_request_force_refresh_defaults_false(self):
        from app.compensation.domain.schemas import CompensationResearchRequest

        req = CompensationResearchRequest(profile="Arquiteto de Soluções Senior Cloud")
        self.assertIs(req.force_refresh, False)

    def test_compensation_research_async_queues_task(self):
        from unittest.mock import AsyncMock, patch

        fake = self._fake_compensation_response()

        with patch(
            "app.compensation.services.orchestrator.CompensationResearchOrchestrator.research",
            new=AsyncMock(return_value=fake),
        ):
            response = self.client.post(
                "/api/gpt/compensation/research/async",
                json={
                    "profile": "Arquiteto de Soluções Senior Cloud",
                    "skills": ["Azure"],
                    "seniority": "senior",
                    "allocation_model": "hybrid",
                    "location": {"city": "Campinas", "state": "SP", "country": "BR"},
                    "target_contract": "PJ",
                },
            )
            self.assertEqual(response.status_code, 200)
            task = response.json()
            self.assertEqual(task["kind"], "compensation_research")
            self.assertIn(task["status"], ("queued", "running", "completed"))
            task_id = task["task_id"]

            # Background task should complete under TestClient.
            polled = self.client.get(f"/api/gpt/tasks/{task_id}")
            self.assertEqual(polled.status_code, 200)
            polled_body = polled.json()
            self.assertEqual(polled_body["status"], "completed")
            self.assertIsNotNone(polled_body.get("result"))
            self.assertEqual(polled_body["result"]["research_id"], "test-research")

    def test_compensation_research_wait_returns_result_with_cache_default(self):
        from unittest.mock import AsyncMock, patch

        fake = self._fake_compensation_response()

        with patch(
            "app.compensation.services.orchestrator.CompensationResearchOrchestrator.research",
            new=AsyncMock(return_value=fake),
        ) as mocked:
            response = self.client.post(
                "/api/gpt/compensation/research/wait",
                json={
                    "profile": "Arquiteto de Soluções Senior Cloud",
                    "skills": ["Azure"],
                    "seniority": "senior",
                    "allocation_model": "hybrid",
                    "location": {"city": "Campinas", "state": "SP", "country": "BR"},
                    "target_contract": "PJ",
                },
            )
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["research_id"], "test-research")
            mocked.assert_awaited_once()
            called_request = mocked.await_args.args[0]
            self.assertIs(called_request.force_refresh, False)


if __name__ == "__main__":
    unittest.main()
