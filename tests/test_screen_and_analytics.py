"""Unit tests for ScreenRecorderEngine and AnalyticsEngine."""

import tempfile
import unittest
from pathlib import Path
from PIL import Image

from src.core.config import settings
from src.pipeline.analytics import AnalyticsEngine
from src.pipeline.screen_recorder import ScreenRecorderEngine


class TestScreenRecorder(unittest.TestCase):
    def setUp(self):
        self.recorder = ScreenRecorderEngine()

    def test_generate_fiori_html_structure(self):
        """Verify generated SAP Fiori HTML contains required UI5 components."""
        html_code = self.recorder.generate_fiori_html(
            topic="Storage Location Stock Deficit",
            error_code="M7021",
            persona_id="erp_functional_consultant",
        )
        self.assertIn("SAP Fiori 3.0", html_code)
        self.assertIn("M7021", html_code)
        self.assertIn("smart-filterbar", html_code)
        self.assertIn("MAT-8842-X", html_code)
        self.assertIn("Industrial Sensor Unit X9", html_code)

    def test_capture_screen_simulated_creates_valid_image(self):
        """Verify simulated PIL renderer creates a valid PNG image with matching dimensions."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_png = Path(tmp_dir) / "fiori_overlay.png"
            res = self.recorder.capture_screen(
                html_content="<html></html>",
                output_path=out_png,
                width=1080,
                height=608,
                dry_run=True,
            )
            self.assertTrue(res.exists())

            # Verify image format and resolution
            with Image.open(res) as img:
                self.assertEqual(img.size, (1080, 608))
                self.assertEqual(img.format, "PNG")

    def test_create_broll_asset_creates_file(self):
        """Verify create_broll_asset orchestrates end-to-end asset generation."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            orig_output = settings.OUTPUT_DIR
            try:
                settings.OUTPUT_DIR = Path(tmp_dir)
                res_path = self.recorder.create_broll_asset(
                    job_id="test_broll_job",
                    topic="Clean Core Extensibility",
                    error_code="CLEAN_CORE",
                    dry_run=True,
                )
                self.assertTrue(res_path.exists())
            finally:
                settings.OUTPUT_DIR = orig_output


class TestAnalyticsEngine(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.telemetry_file = Path(self.tmp_dir.name) / "test_analytics.json"
        self.engine = AnalyticsEngine(data_file=self.telemetry_file)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_calculate_retention_score_bounds(self):
        """Verify retention score formula limits and accuracy."""
        # Worst case (0% completion, 0s watch time, 100% hook drop-off)
        score_min = AnalyticsEngine.calculate_retention_score(
            completion_rate=0.0,
            avg_watch_time_sec=0.0,
            target_duration_sec=60.0,
            hook_dropoff_rate=1.0,
        )
        self.assertEqual(score_min, 0.0)

        # Perfect case (100% completion, 60s watch time, 0% hook drop-off)
        score_max = AnalyticsEngine.calculate_retention_score(
            completion_rate=1.0,
            avg_watch_time_sec=60.0,
            target_duration_sec=60.0,
            hook_dropoff_rate=0.0,
        )
        self.assertEqual(score_max, 100.0)

        # Realistic high-performing video (75% completion, 50s watch time, 10% hook drop-off)
        score_real = AnalyticsEngine.calculate_retention_score(
            completion_rate=0.75,
            avg_watch_time_sec=50.0,
            target_duration_sec=60.0,
            hook_dropoff_rate=0.10,
        )
        self.assertGreater(score_real, 75.0)
        self.assertLess(score_real, 90.0)

    def test_record_telemetry_and_reload(self):
        """Verify telemetry recording persists correctly to disk."""
        metric = self.engine.record_telemetry(
            job_id="job_m7021",
            views_count=1200,
            completions_count=900,
            avg_watch_time_sec=52.4,
            hook_dropoff_rate=0.08,
            hook_style="warning_symptom",
        )
        self.assertEqual(metric.job_id, "job_m7021")
        self.assertTrue(self.telemetry_file.exists())

        # Reload
        reloaded = self.engine._load_data()
        self.assertIn("job_m7021", reloaded)
        self.assertEqual(reloaded["job_m7021"]["views_count"], 1200)

    def test_get_summary_report_and_recommendations(self):
        """Verify executive report aggregation and actionable hook recommendations."""
        # Empty state
        empty_rep = self.engine.get_summary_report()
        self.assertEqual(empty_rep["total_modules_tracked"], 0)

        # Record 2 modules with different hook styles
        self.engine.record_telemetry(
            job_id="job_01",
            views_count=1000,
            completions_count=800,
            avg_watch_time_sec=54.0,
            hook_dropoff_rate=0.05,
            hook_style="myth_buster",
        )
        self.engine.record_telemetry(
            job_id="job_02",
            views_count=500,
            completions_count=250,
            avg_watch_time_sec=30.0,
            hook_dropoff_rate=0.30,
            hook_style="generic_intro",
        )

        rep = self.engine.get_summary_report()
        self.assertEqual(rep["total_modules_tracked"], 2)
        self.assertGreater(rep["overall_retention_avg"], 50.0)
        self.assertEqual(rep["best_hook_style"], "myth_buster")

        recs = self.engine.recommend_hook_improvements("sap_architect")
        self.assertGreaterEqual(len(recs), 3)
        self.assertTrue(any("myth_buster" in r for r in recs))


if __name__ == "__main__":
    unittest.main()
