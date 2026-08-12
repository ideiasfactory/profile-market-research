from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.main import build_cloned_job, _clone_job_title


class CloneJobTitleTests(unittest.TestCase):
    def test_basic_copy_suffix(self):
        self.assertEqual(_clone_job_title("Arquiteto OIC", set()), "Arquiteto OIC (cópia)")

    def test_increments_when_title_exists(self):
        existing = {"Arquiteto OIC (cópia)"}
        self.assertEqual(_clone_job_title("Arquiteto OIC", existing), "Arquiteto OIC (cópia 2)")

    def test_strips_existing_copy_suffix(self):
        self.assertEqual(
            _clone_job_title("Arquiteto OIC (cópia)", {"Arquiteto OIC (cópia)"}),
            "Arquiteto OIC (cópia 2)",
        )


class BuildClonedJobTests(unittest.TestCase):
    def test_copies_fields_with_new_id_and_lineage(self):
        source = {
            "id": "src123",
            "title": "Arquiteto OIC - CPFL",
            "description": "desc",
            "profile": "Arquiteto",
            "seniority": "Senior",
            "job_description": "# JD",
            "ideal_candidate_context": "CPFL",
            "compensation_type": "pj_hour",
            "compensation_min": 100,
            "compensation_max": 200,
            "work_location": "Presencial",
            "analysis": {
                "must_have": [{"name": "OIC", "weight": 10, "tier": "MUST_HAVE"}],
                "llm_provider": "local",
                "weight_policy": "v2",
            },
        }
        cloned = build_cloned_job(
            source,
            now="2026-08-12T00:00:00+00:00",
            existing_titles={source["title"]},
        )
        self.assertNotEqual(cloned["id"], source["id"])
        self.assertEqual(cloned["cloned_from"], "src123")
        self.assertEqual(cloned["title"], "Arquiteto OIC - CPFL (cópia)")
        self.assertEqual(cloned["job_description"], "# JD")
        self.assertEqual(cloned["analysis"]["must_have"][0]["name"], "OIC")
        self.assertEqual(cloned["created_at"], "2026-08-12T00:00:00+00:00")
        # Deep copy: mutating clone must not alter source analysis.
        cloned["analysis"]["must_have"][0]["weight"] = 1
        self.assertEqual(source["analysis"]["must_have"][0]["weight"], 10)


class CloneJobRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import os

        os.environ.pop("PROFESSIONAL_PROFILE_API_KEY", None)
        from fastapi.testclient import TestClient
        from app.main import app

        cls.client = TestClient(app)

    def test_clone_route_persists_and_redirects_to_edit(self):
        jobs = self.client.get("/jobs").status_code
        self.assertEqual(jobs, 200)
        # Pick first job from GPT list API if available, else skip.
        listing = self.client.get("/api/gpt/jobs").json().get("jobs") or []
        if not listing:
            self.skipTest("no jobs fixtures")
        source_id = listing[0]["id"]
        source_title = listing[0]["title"]

        with tempfile.TemporaryDirectory() as tmp:
            # Route uses real jobs_store; just exercise HTTP + redirect.
            response = self.client.post(f"/jobs/{source_id}/clone", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        location = response.headers.get("location") or ""
        self.assertTrue(location.startswith("/jobs/"))
        self.assertTrue(location.endswith("/edit"))
        new_id = location.split("/")[2]
        self.assertNotEqual(new_id, source_id)

        detail = self.client.get(f"/jobs/{new_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertIn("(cópia)", detail.text)
        self.assertIn(source_id, detail.text)

        # Cleanup cloned job to avoid polluting shared data store.
        from app.storage import find_by_id, jobs_store

        jobs_data = jobs_store.read()
        cloned = find_by_id(jobs_data, new_id)
        self.assertIsNotNone(cloned)
        self.assertEqual(cloned.get("cloned_from"), source_id)
        self.assertTrue(str(cloned.get("title") or "").startswith(source_title.split(" (cópia)")[0]))
        jobs_store.write([job for job in jobs_data if job.get("id") != new_id])


if __name__ == "__main__":
    unittest.main()
