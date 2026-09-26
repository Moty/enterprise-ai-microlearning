"""Adversarial and security hardening tests covering all audit findings."""

import concurrent.futures
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import requests

from src.core.config import settings
from src.core.models import VideoLayout, VideoRenderJob, VideoScript
from src.core.repositories import FirestoreJobRepository, LocalJsonJobRepository
from src.pipeline.analytics import AnalyticsEngine
from src.pipeline.ideation import ScriptGenerator
from src.pipeline.localization import LocalizationEngine
from src.pipeline.screen_recorder import ScreenRecorderEngine
from src.pipeline.topic_ingestion import TopicIngestionEngine
from src.publishers.linkedin_publisher import (
    LinkedInAuthError,
    LinkedInError,
    LinkedInPublisher,
    LinkedInRateLimitError,
    LinkedInUploadError,
)
from src.publishers.scorm_packager import ScormPackager


class TestAdversarialHardening(unittest.TestCase):
    """Verifies security controls, concurrency safety, and edge-case handling."""

    # C1: XML Entity Expansion (Billion Laughs) Attack
    @patch("requests.get")
    def test_rss_feed_blocks_xml_entity_expansion(self, mock_get):
        """Verify defusedxml blocks or safely handles XML with entity expansions."""
        xml_bomb = """<?xml version="1.0"?>
        <!DOCTYPE lolz [
         <!ENTITY lol "lol">
         <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
         <!ENTITY lol2 "&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;">
        ]>
        <rss version="2.0">
          <channel>
            <title>&lol2;</title>
            <item><title>&lol2;</title></item>
          </channel>
        </rss>"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = xml_bomb.encode("utf-8")
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        engine = TopicIngestionEngine()
        # defusedxml catches entities and crawl_rss_feed safely catches Exception returning []
        items = engine.crawl_rss_feed("https://test-bomb.com/rss", limit=5)
        self.assertEqual(items, [])

    # C2: XSS in Generated Fiori HTML
    def test_fiori_html_escapes_xss_injection(self):
        """Verify topic and error_code are escaped to prevent XSS in Fiori mock HTML."""
        recorder = ScreenRecorderEngine()
        xss_topic = "<script>alert('XSS_ATTACK')</script>"
        xss_error = "<img src=x onerror=alert(1)>"

        html_out = recorder.generate_fiori_html(topic=xss_topic, error_code=xss_error)

        # Raw payload should NOT be present
        self.assertNotIn("<script>alert('XSS_ATTACK')</script>", html_out)
        self.assertNotIn("<img src=x onerror=alert(1)>", html_out)

        # Escaped entities MUST be present
        self.assertIn("&lt;script&gt;alert(&#x27;XSS_ATTACK&#x27;)&lt;/script&gt;", html_out)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", html_out)

    # M3: Repository path traversal on job_id
    def test_local_repository_path_traversal_rejected(self):
        """Verify LocalJsonJobRepository rejects path traversal attempts in job_id."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = LocalJsonJobRepository(base_dir=Path(tmp_dir))
            traversal_ids = ["../../etc/passwd", "../job_01", "job/nested", "job;rm -rf", ""]
            for bad_id in traversal_ids:
                with self.assertRaises(ValueError):
                    repo.get_job(bad_id)

    def test_firestore_repository_invalid_job_id_rejected(self):
        """Verify FirestoreJobRepository rejects invalid job_ids."""
        mock_client = MagicMock()
        repo = FirestoreJobRepository(client=mock_client)
        traversal_ids = ["../../etc/passwd", "job/nested", ""]
        for bad_id in traversal_ids:
            with self.assertRaises(ValueError):
                repo.get_job(bad_id)

    # L1: Template path traversal in ideation.py
    def test_load_template_path_traversal_rejected(self):
        """Verify load_template rejects path traversal payloads in template_id."""
        generator = ScriptGenerator()
        traversal_templates = ["../../configs/personas/sap_architect", "../etc/passwd", "tpl/sub"]
        for bad_id in traversal_templates:
            with self.assertRaises(ValueError):
                generator.load_template(bad_id)

    # H1: Analytics concurrency and file locking
    def test_analytics_concurrent_writes(self):
        """Verify concurrent record_telemetry calls persist all entries without corrupting JSON."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_file = Path(tmp_dir) / "concurrent_analytics.json"
            engine = AnalyticsEngine(data_file=data_file)

            num_threads = 10
            def record_item(idx):
                engine.record_telemetry(
                    job_id=f"job_thread_{idx}",
                    views_count=100 * (idx + 1),
                    completions_count=80 * (idx + 1),
                    avg_watch_time_sec=45.0,
                    hook_dropoff_rate=0.10,
                )

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(record_item, i) for i in range(num_threads)]
                for f in concurrent.futures.as_completed(futures):
                    f.result()

            # Read back all data
            reloaded = engine._load_data()
            self.assertEqual(len(reloaded), num_threads)
            for idx in range(num_threads):
                self.assertIn(f"job_thread_{idx}", reloaded)

    # H2: Robust JSON extraction from LLM prose
    def test_llm_translation_prose_wrapped_json(self):
        """Verify LocalizationEngine safely parses JSON wrapped in explanation prose and markdown."""
        engine = LocalizationEngine()
        raw_llm_output = """Here is your localized SAP script in German:
```json
{
  "topic": "SAP Microlearning: Clean Core",
  "post_caption": "Leitfaden für Architekten",
  "sections": [
    {"voiceover_text": "Hallo Welt 1", "visual_cue": "Demo 1"},
    {"voiceover_text": "Hallo Welt 2", "visual_cue": "Demo 2"}
  ],
  "hashtags": ["#SAP", "#CleanCore"]
}
```
I hope this meets your enterprise requirements!"""

        extracted = engine._extract_json_payload(raw_llm_output)
        self.assertIsNotNone(extracted)
        self.assertEqual(extracted["topic"], "SAP Microlearning: Clean Core")
        self.assertEqual(len(extracted["sections"]), 2)

    # M4: Localization uses GOOGLE_API_KEY without AttributeError
    @patch("requests.post")
    def test_localization_google_api_key_used(self, mock_post):
        """Verify localization with Google LLM provider references GOOGLE_API_KEY properly."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": '{"topic": "Deutscher Titel", "post_caption": "Post", "sections": [{"voiceover_text": "Text", "visual_cue": "Cue"}]}'
                            }
                        ]
                    }
                }
            ]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        orig_provider = settings.LLM_PROVIDER
        orig_google_key = settings.GOOGLE_API_KEY
        orig_anthropic_key = settings.ANTHROPIC_API_KEY
        try:
            settings.LLM_PROVIDER = "google"
            settings.GOOGLE_API_KEY = "mock_google_key"
            settings.ANTHROPIC_API_KEY = ""

            engine = LocalizationEngine()
            sample_script = VideoScript(
                script_id="test_key_script",
                topic="Clean Core",
                persona_id="sap_architect",
                sections=[],
                post_caption="Post",
            )
            # Should not raise AttributeError: 'AppSettings' object has no attribute 'GEMINI_API_KEY'
            translated = engine.translate_script(sample_script, "de", dry_run=False)
            self.assertEqual(translated.topic, "Deutscher Titel")
            self.assertIn("key=mock_google_key", mock_post.call_args[0][0])
        finally:
            settings.LLM_PROVIDER = orig_provider
            settings.GOOGLE_API_KEY = orig_google_key
            settings.ANTHROPIC_API_KEY = orig_anthropic_key

    # H3: Typed LinkedIn exceptions
    @patch("requests.post")
    def test_linkedin_typed_exceptions_401_auth_error(self, mock_post):
        """Verify HTTP 401 raises LinkedInAuthError with clear context."""
        publisher = LinkedInPublisher(access_token="expired_token", author_urn="urn:li:person:TEST")
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        err = requests.HTTPError(response=mock_resp)
        mock_post.side_effect = err

        with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp_mp4:
            script = VideoScript(script_id="s1", topic="Topic", persona_id="sap_architect", sections=[], post_caption="C")
            job = VideoRenderJob(job_id="j1", script=script, output_file_path=tmp_mp4.name)

            with self.assertRaises(LinkedInAuthError):
                publisher.publish_live(job=job, dry_run=False)

    @patch("requests.post")
    def test_linkedin_typed_exceptions_429_rate_limit(self, mock_post):
        """Verify HTTP 429 raises LinkedInRateLimitError."""
        publisher = LinkedInPublisher(access_token="valid_token", author_urn="urn:li:person:TEST")
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        err = requests.HTTPError(response=mock_resp)
        mock_post.side_effect = err

        with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp_mp4:
            script = VideoScript(script_id="s2", topic="Topic", persona_id="sap_architect", sections=[], post_caption="C")
            job = VideoRenderJob(job_id="j2", script=script, output_file_path=tmp_mp4.name)

            with self.assertRaises(LinkedInRateLimitError):
                publisher.publish_live(job=job, dry_run=False)

    # M1: Large video SCORM warning
    def test_scorm_packager_large_video_warning(self):
        """Verify ScormPackager logs a warning when packaging video > 500MB."""
        packager = ScormPackager()
        with tempfile.TemporaryDirectory() as tmp_dir:
            target_dir = Path(tmp_dir)
            mock_video = target_dir / "large_video.mp4"
            mock_video.touch()

            script = VideoScript(script_id="s_large", topic="Topic", persona_id="sap_architect", sections=[], post_caption="C")
            job = VideoRenderJob(job_id="j_large", script=script, output_file_path=str(mock_video))

            with patch.object(Path, "stat") as mock_stat:
                mock_stat_res = MagicMock()
                mock_stat_res.st_size = 600 * 1024 * 1024  # 600 MB
                mock_stat.return_value = mock_stat_res

                with self.assertLogs("src.publishers.scorm_packager", level="WARNING") as log_cm:
                    packager.package(job, target_dir=target_dir)
                    self.assertTrue(any("exceeds 500MB SCORM limit" in msg for msg in log_cm.output))

    # L2: Batch error isolation
    def test_batch_production_isolates_errors(self):
        """Verify failure on one batch item does not crash remaining items in execute_batch_production."""
        engine = TopicIngestionEngine()
        topics = [
            {"id": "t1", "topic": "Valid Topic 1", "persona_id": "sap_architect"},
            {"id": "t2", "topic": "Faulty Topic", "persona_id": "nonexistent_persona_999"},
            {"id": "t3", "topic": "Valid Topic 2", "persona_id": "fiori_dev"},
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            orig_output = settings.OUTPUT_DIR
            try:
                settings.OUTPUT_DIR = Path(tmp_dir)
                jobs = engine.execute_batch_production(topics, dry_run=True, export_scorm=False)
                # Should have completed 2 valid jobs (skipping the faulty one)
                self.assertEqual(len(jobs), 2)
            finally:
                settings.OUTPUT_DIR = orig_output

    # M2: User-Agent in RSS crawl
    @patch("requests.get")
    def test_rss_crawler_includes_user_agent(self, mock_get):
        """Verify crawl_rss_feed includes proper User-Agent header in HTTP requests."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"<rss><channel></channel></rss>"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        engine = TopicIngestionEngine()
        engine.crawl_rss_feed("https://blogs.sap.com/feed/", limit=2)

        mock_get.assert_called_once()
        headers = mock_get.call_args[1].get("headers", {})
        self.assertIn("User-Agent", headers)
        self.assertEqual(headers["User-Agent"], TopicIngestionEngine.USER_AGENT)


if __name__ == "__main__":
    unittest.main()
