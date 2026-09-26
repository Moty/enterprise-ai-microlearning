"""Automated tests for the Enterprise SME Review & Approval Dashboard."""

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from src.core.config import settings
from src.core.models import VideoRenderJob, VideoScript
from src.core.repositories import LocalJsonJobRepository
from src.dashboard.app import app


class TestDashboard(unittest.TestCase):
    """Verifies all REST API endpoints and UI rendering of the SME Review Dashboard."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.orig_output = settings.OUTPUT_DIR
        settings.OUTPUT_DIR = Path(self.tmp_dir.name)

        # Create sample job
        self.repo = LocalJsonJobRepository(base_dir=settings.OUTPUT_DIR)
        self.sample_script = VideoScript(
            script_id="job_dash_001",
            topic="SAP Error M7021: Stock Deficit",
            persona_id="erp_functional_consultant",
            sections=[],
            post_caption="Clean Core Fix for Inventory Deficit",
        )
        self.sample_job = VideoRenderJob(
            job_id=self.sample_script.script_id,
            script=self.sample_script,
            status="composited",
        )
        self.repo.save_job(self.sample_job)

        self.client = TestClient(app)

    def tearDown(self):
        settings.OUTPUT_DIR = self.orig_output
        self.tmp_dir.cleanup()

    def test_dashboard_ui_html_renders(self):
        """Verify the root endpoint serves the single-page HTML review dashboard."""
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Enterprise Microlearning SME Review Portal", resp.text)
        self.assertIn("SAP AI-SME", resp.text)

    def test_list_jobs_endpoint(self):
        """Verify GET /api/jobs returns jobs with JSON metadata."""
        resp = self.client.get("/api/jobs")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["job_id"], "job_dash_001")

    def test_get_job_endpoint(self):
        """Verify GET /api/jobs/{id} returns full job details."""
        resp = self.client.get("/api/jobs/job_dash_001")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["script"]["topic"], "SAP Error M7021: Stock Deficit")

    def test_get_nonexistent_job_returns_404(self):
        """Verify GET /api/jobs/unknown returns HTTP 404."""
        resp = self.client.get("/api/jobs/unknown_job_999")
        self.assertEqual(resp.status_code, 404)

    def test_approve_job_endpoint(self):
        """Verify POST /api/jobs/{id}/approve updates status to completed."""
        req_body = {
            "publish_linkedin": False,
            "dry_run": True,
        }
        resp = self.client.post("/api/jobs/job_dash_001/approve", json=req_body)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "approved")

        # Verify persisted status
        updated = self.repo.get_job("job_dash_001")
        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, "completed")

    def test_localize_job_endpoint(self):
        """Verify POST /api/jobs/{id}/localize translates script into target languages."""
        req_body = {
            "languages": ["de", "ja"],
            "export_scorm": True,
            "dry_run": True,
        }
        resp = self.client.post("/api/jobs/job_dash_001/localize", json=req_body)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "localized")
        self.assertIn("de", data["tracks"])
        self.assertIn("ja", data["tracks"])

    def test_analytics_report_endpoint(self):
        """Verify GET /api/analytics returns valid retention summary metrics."""
        resp = self.client.get("/api/analytics")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("total_modules_tracked", data)
        self.assertIn("overall_retention_avg", data)


if __name__ == "__main__":
    unittest.main()
