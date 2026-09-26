"""Unit and integration tests for TopicIngestionEngine."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.core.config import settings
from src.pipeline.topic_ingestion import TopicIngestionEngine


SAMPLE_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>SAP Community Blogs</title>
    <link>https://blogs.sap.com</link>
    <description>Latest SAP developer insights</description>
    <item>
      <title>Building Modern SAP Fiori Apps with ABAP RESTful Application Programming Model (RAP)</title>
      <link>https://blogs.sap.com/2026/fiori-rap-guide</link>
      <description><![CDATA[<p>Learn how to use <b>CDS views</b> and RAP annotations to build responsive Fiori elements apps.</p>]]></description>
      <pubDate>Mon, 23 Sep 2026 10:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Clean Core Architecture in S/4HANA Cloud and BTP Integration</title>
      <link>https://blogs.sap.com/2026/clean-core-btp</link>
      <description><![CDATA[<p>Strategies for decoupling custom code and keeping the ERP core clean.</p>]]></description>
      <pubDate>Tue, 24 Sep 2026 14:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Troubleshooting MIGO Goods Receipt Stock Shortages</title>
      <link>https://blogs.sap.com/2026/migo-inventory</link>
      <description><![CDATA[<p>Resolving storage location unrestricted stock discrepancies during procurement.</p>]]></description>
      <pubDate>Wed, 25 Sep 2026 09:30:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


class TestTopicIngestion(unittest.TestCase):
    def setUp(self):
        self.engine = TopicIngestionEngine()

    def test_curated_topics_catalog_structure(self):
        """Verify the curated SAP catalog has valid structure and required fields."""
        topics = self.engine.get_curated_topics(limit=5)
        self.assertEqual(len(topics), 5)
        for t in topics:
            self.assertIn("id", t)
            self.assertIn("topic", t)
            self.assertIn("persona_id", t)
            self.assertIn("category", t)
            self.assertIn("impact_score", t)
            self.assertGreaterEqual(t["impact_score"], 8.0)

    def test_curated_topics_limit(self):
        """Verify get_curated_topics respects the limit parameter."""
        topics_2 = self.engine.get_curated_topics(limit=2)
        self.assertEqual(len(topics_2), 2)

    def test_match_persona_for_topic(self):
        """Verify heuristic persona routing based on SAP domain terminology."""
        # Fiori / Dev
        self.assertEqual(
            TopicIngestionEngine.match_persona_for_topic("Building Fiori Elements with CDS Annotations"),
            "fiori_dev",
        )
        self.assertEqual(
            TopicIngestionEngine.match_persona_for_topic("RAP Business Object Extensibility via BAdI"),
            "fiori_dev",
        )

        # Architecture / Clean Core
        self.assertEqual(
            TopicIngestionEngine.match_persona_for_topic("SAP Clean Core Strategy: Greenfield S/4HANA Migration"),
            "sap_architect",
        )
        self.assertEqual(
            TopicIngestionEngine.match_persona_for_topic("Event-Driven Architecture using SAP BTP Event Mesh"),
            "sap_architect",
        )

        # Functional / MM / Inventory
        self.assertEqual(
            TopicIngestionEngine.match_persona_for_topic("SAP Error M7021: Storage Location Deficit"),
            "erp_functional_consultant",
        )
        self.assertEqual(
            TopicIngestionEngine.match_persona_for_topic("Purchase Order Commitment Error in ME21N MIGO"),
            "erp_functional_consultant",
        )

        # Default fallback
        self.assertEqual(
            TopicIngestionEngine.match_persona_for_topic("General Enterprise Technology Overview"),
            "sap_architect",
        )

    @patch("requests.get")
    def test_crawl_rss_feed_mocked_success(self, mock_get):
        """Verify RSS feed parsing, HTML tag stripping, and persona assignment."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = SAMPLE_RSS_XML.encode("utf-8")
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        items = self.engine.crawl_rss_feed("https://blogs.sap.com/feed/", limit=3)
        self.assertEqual(len(items), 3)

        # Item 1: Fiori Dev
        self.assertIn("Fiori", items[0]["topic"])
        self.assertEqual(items[0]["persona_id"], "fiori_dev")
        self.assertNotIn("<p>", items[0]["description"])
        self.assertIn("CDS views", items[0]["description"])

        # Item 2: Architect
        self.assertIn("Clean Core", items[1]["topic"])
        self.assertEqual(items[1]["persona_id"], "sap_architect")

        # Item 3: Functional
        self.assertIn("MIGO", items[2]["topic"])
        self.assertEqual(items[2]["persona_id"], "erp_functional_consultant")

    @patch("requests.get")
    def test_crawl_rss_feed_failure_graceful(self, mock_get):
        """Verify crawl_rss_feed returns an empty list on HTTP/network error."""
        mock_get.side_effect = Exception("Connection timed out")

        items = self.engine.crawl_rss_feed("https://invalid-sap-feed.com/rss", limit=5)
        self.assertEqual(items, [])

    def test_execute_batch_production_dry_run(self):
        """Verify end-to-end autonomous batch production for multiple topics."""
        topics = [
            {
                "id": "test_topic_01",
                "topic": "SAP Error M7021: Deficit of SL Unrestricted-Use Stock",
                "persona_id": "erp_functional_consultant",
                "error_code": "M7021",
            },
            {
                "id": "test_topic_02",
                "topic": "SAP Clean Core Extensibility: Tier 1 vs Tier 2",
                "persona_id": "sap_architect",
                "error_code": None,
            },
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            orig_output = settings.OUTPUT_DIR
            try:
                settings.OUTPUT_DIR = Path(tmp_dir)
                jobs = self.engine.execute_batch_production(
                    topics=topics,
                    dry_run=True,
                    export_scorm=True,
                )

                self.assertEqual(len(jobs), 2)
                for job in jobs:
                    self.assertEqual(job.status, "composited")
                    job_dir = settings.OUTPUT_DIR / job.job_id
                    self.assertTrue(job_dir.exists())

                    # Check artifacts
                    self.assertTrue((job_dir / f"{job.job_id}_voice.wav").exists())
                    self.assertTrue((job_dir / f"{job.job_id}_avatar.mp4").exists())
                    self.assertTrue((job_dir / f"{job.job_id}_final.mp4").exists())
                    self.assertTrue((job_dir / f"{job.job_id}_captions.srt").exists())
                    self.assertTrue((job_dir / f"{job.job_id}_captions.vtt").exists())
                    self.assertTrue((job_dir / f"{job.job_id}_scorm_package.zip").exists())
                    self.assertTrue((job_dir / f"{job.job_id}_linkedin_package.json").exists())
            finally:
                settings.OUTPUT_DIR = orig_output


if __name__ == "__main__":
    unittest.main()
