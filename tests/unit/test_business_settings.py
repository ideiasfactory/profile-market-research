import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.business_settings import (
    DEFAULT_PARAMETERS,
    delete_business_parameter,
    format_business_context,
    normalize_business_settings,
    prompt_placeholders,
    save_business_settings,
    upsert_business_parameter,
)
from app.prompts import load_prompt
from app.storage import JsonStore


class BusinessSettingsTest(unittest.TestCase):
    def test_normalize_seed_parameters(self):
        settings = normalize_business_settings({})
        keys = {item["key"] for item in settings["parameters"]}
        self.assertIn("clt_to_pj_factor", keys)
        self.assertIn("target_margin_pct", keys)
        self.assertEqual(settings["values"]["work_hours_month"], 168)

    def test_migrate_legacy_pricing_dict(self):
        settings = normalize_business_settings(
            {
                "pricing": {
                    "clt_to_pj_factor": 1.6,
                    "work_hours_month": 160,
                    "iss_pct": 2,
                }
            }
        )
        self.assertEqual(settings["values"]["clt_to_pj_factor"], 1.6)
        self.assertEqual(settings["values"]["work_hours_month"], 160)
        self.assertEqual(settings["values"]["iss_pct"], 2)

    def test_prompt_placeholders_and_context(self):
        settings = normalize_business_settings({"parameters": DEFAULT_PARAMETERS})
        with patch("app.business_settings.get_business_settings", return_value=settings):
            placeholders = prompt_placeholders()
            self.assertIn("business_context", placeholders)
            self.assertIn("25.0", placeholders["target_margin_pct"])
            context = format_business_context(settings["parameters"])
            self.assertIn("target_margin_pct", context)
            self.assertIn("Margem alvo", context)

    def test_upsert_and_delete_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonStore(Path(tmp) / "business_settings.json", {"parameters": [], "updated_at": None})
            with patch("app.business_settings.business_settings_store", store):
                save_business_settings({"parameters": DEFAULT_PARAMETERS[:2]})
                upsert_business_parameter(
                    {
                        "key": "commercial_policy",
                        "label": "Política comercial",
                        "value": "margem mínima 20%",
                        "value_type": "text",
                        "category": "comercial",
                        "inject_in_prompts": True,
                    }
                )
                settings = normalize_business_settings(store.read())
                self.assertIn("commercial_policy", settings["values"])
                item_id = next(item["id"] for item in settings["parameters"] if item["key"] == "commercial_policy")
                delete_business_parameter(item_id)
                settings = normalize_business_settings(store.read())
                self.assertNotIn("commercial_policy", settings["values"])

    def test_load_prompt_injects_business_context(self):
        settings = normalize_business_settings(
            {
                "parameters": [
                    {
                        "id": "1",
                        "key": "target_margin_pct",
                        "label": "Margem",
                        "value": 22,
                        "value_type": "percent",
                        "category": "pricing",
                        "description": "",
                        "inject_in_prompts": True,
                    }
                ]
            }
        )
        with patch("app.business_settings.get_business_settings", return_value=settings):
            with patch("app.business_settings.prompt_placeholders", return_value=prompt_placeholders()):
                # Use a tiny inline template via monkeypatch of reader
                with patch(
                    "app.prompts._read_prompt_file",
                    return_value="Margem={target_margin_pct}\n{business_context}\nTitulo={title}",
                ):
                    rendered = load_prompt("dummy.txt", title="Vaga X")
        self.assertIn("Margem=22", rendered)
        self.assertIn("Vaga X", rendered)
        self.assertIn("target_margin_pct", rendered)


if __name__ == "__main__":
    unittest.main()
