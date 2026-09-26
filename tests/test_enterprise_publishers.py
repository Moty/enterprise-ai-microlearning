"""Unit tests for enterprise LMS SCORM packaging, WebVTT captions, and Webhook distribution."""

import tempfile
import unittest
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

from src.core.models import VideoLayout, VideoRenderJob, VideoScript, WordTimestamp
from src.pipeline.compositor import VideoCompositor
from src.publishers.scorm_packager import ScormPackager
from src.publishers.webhook_publisher import WebhookPublisher


def _sample_job(job_id: str = "test_lms_001") -> VideoRenderJob:
    script = VideoScript(
        script_id=job_id,
        topic="S/4HANA Clean Core Migration",
        persona_id="sap_architect",
        duration_target_seconds=60,
        sections=[],
        hashtags=["#SAP", "#CleanCore"],
        post_caption="Clean Core Best Practices Breakdown",
    )
    return VideoRenderJob(
        job_id=job_id,
        script=script,
        layout=VideoLayout.LINKEDIN_PORTRAIT_4_5,
        status="composited",
    )


class TestVttCaptions(unittest.TestCase):
    def test_generate_vtt_format(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            vtt_path = Path(tmp_dir) / "captions.vtt"
            timestamps = [
                WordTimestamp(word="Welcome", start_time=0.0, end_time=0.4),
                WordTimestamp(word="to", start_time=0.4, end_time=0.6),
                WordTimestamp(word="Clean", start_time=0.6, end_time=1.0),
                WordTimestamp(word="Core.", start_time=1.0, end_time=1.5),
            ]
            VideoCompositor.generate_vtt_subtitles(timestamps, vtt_path)

            self.assertTrue(vtt_path.exists())
            content = vtt_path.read_text(encoding="utf-8")
            self.assertTrue(content.startswith("WEBVTT\n\n"))
            self.assertIn("00:00:00.000 --> 00:00:01.500", content)
            self.assertIn("Welcome to Clean Core.", content)

    def test_generate_vtt_empty(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            vtt_path = Path(tmp_dir) / "empty.vtt"
            VideoCompositor.generate_vtt_subtitles([], vtt_path)
            self.assertTrue(vtt_path.exists())
            self.assertEqual(vtt_path.read_text(encoding="utf-8").strip(), "WEBVTT")


class TestScormPackager(unittest.TestCase):
    def test_manifest_xml_structure(self):
        job = _sample_job("job_manifest_test")
        manifest_str = ScormPackager.generate_manifest_xml(job)

        self.assertIn("<schema>ADL SCORM</schema>", manifest_str)
        self.assertIn("<schemaversion>1.2</schemaversion>", manifest_str)
        self.assertIn('adlcp:scormtype="sco"', manifest_str)
        self.assertIn(job.script.topic, manifest_str)

        # Ensure valid XML parsing
        root = ET.fromstring(manifest_str)
        self.assertIn("manifest", root.tag.lower())

    def test_player_html_scorm_bridge(self):
        job = _sample_job("job_player_test")
        html_content = ScormPackager.generate_player_html(job)

        self.assertIn("<video id=\"player\"", html_content)
        self.assertIn("<track kind=\"subtitles\"", html_content)
        self.assertIn("LMSInitialize", html_content)
        self.assertIn("cmi.core.lesson_status", html_content)
        self.assertIn("LMSCommit", html_content)
        self.assertIn("LMSFinish", html_content)

    def test_package_creates_valid_zip(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target_dir = Path(tmp_dir)
            job = _sample_job("job_zip_test")
            job.output_file_path = str(target_dir / "job_zip_test_final.mp4")
            Path(job.output_file_path).touch()

            packager = ScormPackager()
            zip_path = packager.package(job, target_dir=target_dir)

            self.assertTrue(zip_path.exists())
            self.assertTrue(zipfile.is_zipfile(zip_path))

            # Verify files inside ZIP archive
            with zipfile.ZipFile(zip_path, "r") as zf:
                filenames = zf.namelist()
                self.assertIn("imsmanifest.xml", filenames)
                self.assertIn("index.html", filenames)
                self.assertIn("captions.vtt", filenames)
                self.assertIn("video.mp4", filenames)


class TestWebhookPublisher(unittest.TestCase):
    def test_format_teams_payload(self):
        job = _sample_job("job_teams")
        payload = WebhookPublisher.format_teams_payload(job, video_url="https://lms.corp.com/video1")

        self.assertEqual(payload["@type"], "MessageCard")
        self.assertEqual(payload["themeColor"], "0070F2")
        self.assertIn(job.script.topic, payload["summary"])
        self.assertTrue(len(payload["potentialAction"]) > 0)
        self.assertEqual(payload["potentialAction"][0]["name"], "▶ Watch Video")

    def test_format_slack_payload(self):
        job = _sample_job("job_slack")
        payload = WebhookPublisher.format_slack_payload(job, video_url="https://lms.corp.com/video1")

        self.assertIn("blocks", payload)
        self.assertGreater(len(payload["blocks"]), 2)
        header_text = payload["blocks"][0]["text"]["text"]
        self.assertIn(job.script.topic, header_text)

    def test_send_dry_run(self):
        publisher = WebhookPublisher()
        job = _sample_job("job_dry_run")

        teams_res = publisher.send_teams("https://webhook.teams.test", job, dry_run=True)
        self.assertEqual(teams_res["status"], "simulated")
        self.assertIn("payload", teams_res)

        slack_res = publisher.send_slack("https://webhook.slack.test", job, dry_run=True)
        self.assertEqual(slack_res["status"], "simulated")
        self.assertIn("payload", slack_res)


if __name__ == "__main__":
    unittest.main()
