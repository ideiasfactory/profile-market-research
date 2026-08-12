from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app import storage
from app.storage import ScoreStore


def _score_payload(
    *,
    job_id: str = "job1",
    candidate_id: str = "cand1",
    final_score: float = 50.0,
    verdict_label: str = "evaluate",
    method: str = "llm",
    provider: str = "local",
    model: str = "qwen2.5:14b",
    created_at: str = "2026-08-12T18:00:00+00:00",
    cost: float | None = None,
) -> dict:
    audit: dict = {
        "llm_provider": provider,
        "llm_model": model,
        "scored_at": created_at,
    }
    if cost is not None:
        audit["usage"] = {
            "estimated_cost_usd": cost,
            "total_tokens": 13000,
            "calls": 4,
        }
    return {
        "id": f"{job_id}_{candidate_id}",
        "job_id": job_id,
        "candidate_id": candidate_id,
        "job_title": "Arquiteto OIC",
        "candidate_name": "Bruno Test",
        "final_score": final_score,
        "verdict_label": verdict_label,
        "method": method,
        "scoring_model_version": "v2",
        "llm_provider": provider,
        "created_at": created_at,
        "items": [{"name": "OIC", "score": 4}],
        "audit": audit,
    }


class ScoreHistoryStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.data_dir = self.root / "data"
        self.scores_dir = self.data_dir / "scores"
        self.history_dir = self.scores_dir / "history"
        self.index_path = self.data_dir / "scores.json"
        self.history_index = self.data_dir / "score_history.json"

        self._orig_data_dir = storage.DATA_DIR
        storage.DATA_DIR = self.data_dir

        self.store = ScoreStore(
            self.index_path,
            self.scores_dir,
            history_index_path=self.history_index,
            history_dir=self.history_dir,
        )

    def tearDown(self):
        storage.DATA_DIR = self._orig_data_dir
        self._tmp.cleanup()

    def test_first_save_has_no_history(self):
        saved = self.store.save(_score_payload(provider="openai", model="gpt-4.1", cost=0.038))
        self.assertEqual(saved["final_score"], 50.0)
        self.assertEqual(len(self.store.read()), 1)
        self.assertEqual(len(self.store.read_history()), 0)
        self.assertEqual(self.store.read()[0].get("llm_provider"), "openai")
        self.assertEqual(self.store.read()[0].get("llm_model"), "gpt-4.1")

    def test_rescore_archives_previous_and_keeps_latest_identity(self):
        self.store.save(
            _score_payload(
                final_score=54.9,
                verdict_label="evaluate",
                method="hybrid",
                provider="local",
                model="qwen2.5:14b",
                created_at="2026-08-12T18:34:48+00:00",
            )
        )
        latest = self.store.save(
            _score_payload(
                final_score=61.2,
                verdict_label="recommended",
                method="llm",
                provider="openai",
                model="gpt-4.1",
                created_at="2026-08-12T19:00:00+00:00",
                cost=0.04,
            )
        )

        self.assertEqual(latest["id"], "job1_cand1")
        self.assertEqual(latest["final_score"], 61.2)
        self.assertEqual(latest["llm_provider"], "openai")

        index = self.store.read()
        self.assertEqual(len(index), 1)
        self.assertEqual(index[0]["id"], "job1_cand1")
        self.assertEqual(index[0]["final_score"], 61.2)
        self.assertEqual(index[0]["llm_provider"], "openai")

        history = self.store.history_for("job1", "cand1")
        self.assertEqual(len(history), 1)
        archived = history[0]
        self.assertEqual(archived["final_score"], 54.9)
        self.assertEqual(archived["verdict_label"], "evaluate")
        self.assertEqual(archived["method"], "hybrid")
        self.assertEqual(archived["llm_provider"], "local")
        self.assertEqual(archived["llm_model"], "qwen2.5:14b")
        self.assertEqual(archived["score_id"], "job1_cand1")
        self.assertTrue(archived["id"].endswith("_local"))
        self.assertTrue((self.data_dir / archived["path"]).exists())

        detail = self.store.get_history(archived["id"])
        assert detail is not None
        self.assertTrue(detail["is_history"])
        self.assertEqual(detail["final_score"], 54.9)
        self.assertEqual(detail["items"][0]["name"], "OIC")

        # Latest path still the pair primary file.
        current = self.store.find("job1", "cand1")
        assert current is not None
        self.assertEqual(current["final_score"], 61.2)
        self.assertFalse(str(current.get("path") or "").startswith("scores/history/"))

    def test_multiple_rescores_accumulate_history(self):
        self.store.save(_score_payload(final_score=40, provider="local", created_at="2026-08-12T10:00:00+00:00"))
        self.store.save(
            _score_payload(
                final_score=55,
                provider="openai",
                model="gpt-4.1",
                created_at="2026-08-12T11:00:00+00:00",
                cost=0.038,
            )
        )
        self.store.save(
            _score_payload(
                final_score=52,
                provider="local",
                created_at="2026-08-12T12:00:00+00:00",
            )
        )
        history = self.store.history_for("job1", "cand1")
        self.assertEqual(len(history), 2)
        providers = {h["llm_provider"] for h in history}
        self.assertEqual(providers, {"local", "openai"})
        openai_run = next(h for h in history if h["llm_provider"] == "openai")
        self.assertEqual(openai_run["estimated_cost_usd"], 0.038)
        self.assertEqual(openai_run["total_tokens"], 13000)

    def test_get_any_resolves_history_id(self):
        self.store.save(_score_payload(final_score=40, provider="local", created_at="2026-08-12T10:00:00+00:00"))
        self.store.save(_score_payload(final_score=55, provider="openai", created_at="2026-08-12T11:00:00+00:00"))
        history_id = self.store.history_for("job1", "cand1")[0]["id"]
        resolved = self.store.get_any(history_id)
        assert resolved is not None
        self.assertEqual(resolved["final_score"], 40)
        self.assertTrue(resolved.get("is_history"))
        latest = self.store.get_any("job1_cand1")
        assert latest is not None
        self.assertEqual(latest["final_score"], 55)


class ScoreHistoryApiTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.data_dir = self.root / "data"
        self.scores_dir = self.data_dir / "scores"
        self.history_dir = self.scores_dir / "history"
        self.index_path = self.data_dir / "scores.json"
        self.history_index = self.data_dir / "score_history.json"

        self._orig_data_dir = storage.DATA_DIR
        self._orig_store = storage.scores_store
        storage.DATA_DIR = self.data_dir
        storage.scores_store = ScoreStore(
            self.index_path,
            self.scores_dir,
            history_index_path=self.history_index,
            history_dir=self.history_dir,
        )

        # gpt module imports scores_store at load time — patch both.
        import app.gpt as gpt_mod

        self._gpt_mod = gpt_mod
        self._orig_gpt_store = gpt_mod.scores_store
        gpt_mod.scores_store = storage.scores_store

        from fastapi.testclient import TestClient
        from app.main import app

        self.client = TestClient(app)

        store = storage.scores_store
        store.save(_score_payload(final_score=54.9, provider="local", created_at="2026-08-12T18:00:00+00:00"))
        store.save(
            _score_payload(
                final_score=61.0,
                provider="openai",
                model="gpt-4.1",
                created_at="2026-08-12T19:00:00+00:00",
                cost=0.04,
            )
        )

    def tearDown(self):
        self._gpt_mod.scores_store = self._orig_gpt_store
        storage.scores_store = self._orig_store
        storage.DATA_DIR = self._orig_data_dir
        self._tmp.cleanup()

    def test_list_evaluations_shows_latest_only(self):
        response = self.client.get(
            "/api/gpt/evaluations",
            params={"job_id": "job1", "candidate_id": "cand1"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["evaluations"][0]["final_score"], 61.0)
        self.assertEqual(body["evaluations"][0]["llm_provider"], "openai")

    def test_detail_include_history_and_history_id(self):
        detail = self.client.get(
            "/api/gpt/evaluations/job1_cand1",
            params={"include_history": True},
        )
        self.assertEqual(detail.status_code, 200)
        body = detail.json()
        self.assertEqual(body["final_score"], 61.0)
        self.assertEqual(len(body["history"]), 1)
        history_id = body["history"][0]["history_id"]
        historical = self.client.get(f"/api/gpt/evaluations/{history_id}")
        self.assertEqual(historical.status_code, 200)
        hist = historical.json()
        self.assertTrue(hist.get("is_history"))
        self.assertEqual(hist["final_score"], 54.9)
        self.assertEqual(hist["llm_provider"], "local")


if __name__ == "__main__":
    unittest.main()
