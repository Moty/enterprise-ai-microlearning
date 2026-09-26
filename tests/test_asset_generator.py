"""Unit tests for the visual asset and code snippet generator."""

import tempfile
import unittest
from pathlib import Path
from PIL import Image

from src.pipeline.asset_generator import AssetGenerator


class TestAssetGenerator(unittest.TestCase):
    def test_generate_title_card(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            generator = AssetGenerator()
            out_card = Path(tmp_dir) / "title_card.png"
            res = generator.generate_title_card(
                topic="S/4HANA Clean Core Extensibility in 60s",
                persona_name="Marcus Vance",
                persona_title="Senior SAP Enterprise Architect",
                output_path=out_card,
                dimensions=(1080, 608),
            )
            self.assertTrue(out_card.exists())
            self.assertEqual(res, out_card)

            # Check image dimensions
            with Image.open(out_card) as img:
                self.assertEqual(img.size, (1080, 608))
                self.assertEqual(img.mode, "RGB")

    def test_generate_code_snippet(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            generator = AssetGenerator()
            out_code = Path(tmp_dir) / "code_slide.png"
            abap_code = """@AbapCatalog.sqlViewName: 'ZV_INVENTORY'
define view Z_InventoryStock as select from mard {
  key matnr as Material,
  key werks as Plant,
  labst as UnrestrictedStock
}"""
            res = generator.generate_code_snippet(
                code_text=abap_code,
                language="sql",
                output_path=out_code,
                dimensions=(1080, 608),
            )
            self.assertTrue(out_code.exists())
            with Image.open(out_code) as img:
                self.assertEqual(img.size, (1080, 608))

    def test_generate_solution_steps_card(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            generator = AssetGenerator()
            out_steps = Path(tmp_dir) / "solution_steps.png"
            steps = [
                "Verify movement type in MIGO",
                "Inspect valuation area settings in SPRO",
                "Execute consistency simulation check",
            ]
            res = generator.generate_solution_steps_card(
                steps=steps,
                output_path=out_steps,
                dimensions=(1080, 608),
            )
            self.assertTrue(out_steps.exists())
            with Image.open(out_steps) as img:
                self.assertEqual(img.size, (1080, 608))


if __name__ == "__main__":
    unittest.main()
