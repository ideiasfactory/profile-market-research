import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.prompt_store import (
    get_active_prompt_content,
    list_managed_prompts,
    revert_prompt_version,
    save_prompt_edit,
)
from app.prompts import clear_prompt_cache, load_prompt
from app.storage import JsonStore


class PromptStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = JsonStore(Path(self.tmp.name) / "prompt_store.json", {"prompts": {}, "updated_at": None})
        self.patcher = patch("app.prompt_store.prompt_store", self.store)
        self.patcher.start()
        clear_prompt_cache()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()
        clear_prompt_cache()

    def test_list_seeds_from_disk(self):
        items = list_managed_prompts()
        ids = {item["id"] for item in items}
        self.assertIn("analyse_job.system.txt", ids)
        self.assertGreaterEqual(len(items), 10)

    def test_save_creates_new_version(self):
        first = save_prompt_edit(
            "analyse_job.system.txt",
            content="Versão A do system prompt",
            title="Análise de vaga — system",
            description="desc",
            note="teste A",
        )
        self.assertEqual(first["content"], "Versão A do system prompt")
        self.assertEqual(first["version_count"], 2)  # baseline + edit

        second = save_prompt_edit(
            "analyse_job.system.txt",
            content="Versão B do system prompt",
            note="teste B",
        )
        self.assertEqual(second["content"], "Versão B do system prompt")
        self.assertEqual(second["version_count"], 3)

        history_id = next(v["id"] for v in second["versions"] if "teste A" in v["label"])
        reverted = revert_prompt_version("analyse_job.system.txt", history_id)
        self.assertEqual(reverted["content"], "Versão A do system prompt")
        self.assertEqual(reverted["version_count"], 4)
        self.assertTrue(any("revert" in v["label"] for v in reverted["versions"] if v["is_active"]))

    def test_load_prompt_uses_active_version(self):
        save_prompt_edit(
            "extract_candidate.system.txt",
            content="PROMPT_CUSTOM_FOR_TEST {resume_text}",
            note="custom",
        )
        clear_prompt_cache()
        rendered = load_prompt("extract_candidate.system.txt", resume_text="Joao")
        self.assertIn("PROMPT_CUSTOM_FOR_TEST", rendered)
        self.assertIn("Joao", rendered)
        self.assertEqual(get_active_prompt_content("extract_candidate.system.txt"), "PROMPT_CUSTOM_FOR_TEST {resume_text}")


if __name__ == "__main__":
    unittest.main()
