"""Tests for distribution publishers and end-to-end pipeline execution."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.core.config import settings
from src.core.models import VideoLayout, VideoRenderJob, VideoScript
from src.pipeline.avatar_engine import AvatarEngine
from src.pipeline.compositor import VideoCompositor
from src.pipeline.ideation import ScriptGenerator
from src.pipeline.voice_engine import VoiceEngine
from src.publishers.linkedin_publisher import LinkedInPublisher


class TestPublishers(unittest.TestCase):
    def test_format_post_payload_structure(self):
        """Verify LinkedIn post payload adheres to required API schema keys."""
        publisher = LinkedInPublisher()
        script = VideoScript(
            script_id="test_post_01",
            topic="SAP Error M7021",
            persona_id="erp_functional_consultant",
            sections=[],
            hashtags=["#SAP", "#Logistics"],
            post_caption="Check out this solution.",
        )
        job = VideoRenderJob(job_id=script.script_id, script=script)
        payload = publisher.format_post_payload(job)

        self.assertIn("author", payload)
        self.assertIn("commentary", payload)
        self.assertIn("#SAP #Logistics", payload["commentary"])
        self.assertEqual(payload["visibility"], "PUBLIC")
        self.assertIn("media", payload["content"])
        self.assertEqual(payload["content"]["media"]["title"], "SAP Error M7021")

    def test_format_post_payload_with_first_comment(self):
        """Verify first comment link inclusion in payload."""
        publisher = LinkedInPublisher()
        script = VideoScript(
            script_id="test_post_02",
            topic="Clean Core",
            persona_id="sap_architect",
            sections=[],
            post_caption="Clean Core Architecture",
        )
        job = VideoRenderJob(job_id=script.script_id, script=script)
        payload = publisher.format_post_payload(job, first_comment_link="https://example.com/guide.pdf")

        self.assertIn("first_comment", payload)
        self.assertIn("https://example.com/guide.pdf", payload["first_comment"])

    def test_publish_draft_creates_file_and_directory(self):
        """Verify publish_draft creates destination directory if absent and writes valid json."""
        publisher = LinkedInPublisher()
        script = VideoScript(
            script_id="test_draft_03",
            topic="Fiori Elements",
            persona_id="fiori_dev",
            sections=[],
            post_caption="Fiori post",
        )
        job = VideoRenderJob(job_id=script.script_id, script=script)
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            non_existent_subfolder = tmp_path / "deep" / "nested" / "publish_dir"

            pkg_path = publisher.publish_draft(job, non_existent_subfolder)
            self.assertTrue(pkg_path.exists())
            content = json.loads(pkg_path.read_text(encoding="utf-8"))
            self.assertEqual(content["visibility"], "PUBLIC")

    def test_end_to_end_dry_run_pipeline(self):
        """Verify complete end-to-end execution of all 5 pipeline steps in dry-run mode."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            original_output = settings.OUTPUT_DIR
            try:
                settings.OUTPUT_DIR = tmp_path

                # 1. Ideation
                generator = ScriptGenerator()
                script = generator.generate_script(topic="Inventory Blocks M7021", persona_id="erp_functional_consultant")
                persona_cfg = generator.load_persona(script.persona_id)
                self.assertEqual(len(script.sections), 4)

                job_dir = tmp_path / script.script_id
                job_dir.mkdir(parents=True, exist_ok=True)

                # 2. Voice
                voice_engine = VoiceEngine()
                audio_path = job_dir / f"{script.script_id}_voice.wav"
                audio_track = voice_engine.synthesize(
                    text=" ".join([s.voiceover_text for s in script.sections]),
                    voice_id=persona_cfg.voice_profile.voice_id,
                    output_path=audio_path,
                    dry_run=True,
                )
                self.assertTrue(audio_path.exists())
                self.assertGreater(audio_track.duration_seconds, 0)

                # 3. Avatar
                avatar_engine = AvatarEngine()
                avatar_video_path = job_dir / f"{script.script_id}_avatar.mp4"
                avatar_engine.animate_avatar(
                    seed_image_path=Path(persona_cfg.visual_profile.avatar_seed_image),
                    audio_file_path=audio_path,
                    output_video_path=avatar_video_path,
                    dry_run=True,
                )
                self.assertTrue(avatar_video_path.exists())

                # 4. Compositor
                compositor = VideoCompositor()
                job = VideoRenderJob(
                    job_id=script.script_id,
                    script=script,
                    layout=VideoLayout.LINKEDIN_PORTRAIT_4_5,
                )
                composited_job = compositor.composite(
                    job=job,
                    audio_track=audio_track,
                    avatar_video_path=avatar_video_path,
                    dry_run=True,
                )
                self.assertEqual(composited_job.status, "composited")
                self.assertTrue(Path(composited_job.output_file_path).exists())
                self.assertTrue(Path(composited_job.subtitles_file_path).exists())

                # 5. Publisher
                publisher = LinkedInPublisher()
                pkg_file = publisher.publish_draft(composited_job, job_dir)
                self.assertTrue(pkg_file.exists())
            finally:
                settings.OUTPUT_DIR = original_output

    def test_all_personas_generate_successfully(self):
        """Verify that every configured persona generates a valid script without error."""
        generator = ScriptGenerator()
        personas = ["sap_architect", "fiori_dev", "erp_functional_consultant"]
        for pid in personas:
            script = generator.generate_script(topic="Enterprise Best Practice", persona_id=pid)
            self.assertEqual(script.persona_id, pid)
            self.assertGreater(len(script.sections), 0)
            self.assertTrue(bool(script.post_caption))

    def test_publish_live_dry_run_simulated(self):
        """Verify publish_live in dry_run mode returns simulated metadata without external calls."""
        publisher = LinkedInPublisher(access_token="test_token_123", author_urn="urn:li:person:TEST_AUTHOR")
        script = VideoScript(
            script_id="test_sim_01",
            topic="SAP Clean Core",
            persona_id="sap_architect",
            sections=[],
            post_caption="Clean Core Tip",
        )
        job = VideoRenderJob(job_id=script.script_id, script=script)
        res = publisher.publish_live(job=job, dry_run=True)

        self.assertEqual(res["status"], "simulated")
        self.assertEqual(res["post_urn"], f"urn:li:ugcPost:simulated_{job.job_id}")
        self.assertEqual(res["author"], "urn:li:person:TEST_AUTHOR")

    def test_publish_live_missing_video_raises(self):
        """Verify publish_live raises RuntimeError when target video does not exist."""
        publisher = LinkedInPublisher(access_token="test_token_123", author_urn="urn:li:person:TEST_AUTHOR")
        script = VideoScript(
            script_id="test_sim_02",
            topic="SAP Clean Core",
            persona_id="sap_architect",
            sections=[],
            post_caption="Clean Core Tip",
        )
        job = VideoRenderJob(job_id=script.script_id, script=script, output_file_path="/path/does/not/exist.mp4")

        with self.assertRaises(RuntimeError) as ctx:
            publisher.publish_live(job=job, dry_run=False)
        self.assertIn("Video file not found", str(ctx.exception))

    @patch("requests.post")
    def test_register_video_upload_mocked(self, mock_post):
        """Verify register_video_upload parses LinkedIn uploadMechanism and asset URN."""
        publisher = LinkedInPublisher(access_token="token_abc", author_urn="urn:li:person:AUTHOR_1")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "value": {
                "uploadMechanism": {
                    "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest": {
                        "uploadUrl": "https://media.licdn.com/upload/binary"
                    }
                },
                "asset": "urn:li:digitalmediaAsset:ASSET_999",
            }
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        upload_url, asset_urn = publisher.register_video_upload("Test Title")
        self.assertEqual(upload_url, "https://media.licdn.com/upload/binary")
        self.assertEqual(asset_urn, "urn:li:digitalmediaAsset:ASSET_999")
        mock_post.assert_called_once()

    @patch("requests.post")
    @patch("requests.put")
    def test_publish_live_end_to_end_mocked(self, mock_put, mock_post):
        """Verify full live LinkedIn upload: register, binary put, UGC post, and first comment."""
        publisher = LinkedInPublisher(access_token="token_live_123", author_urn="urn:li:person:AUTHOR_123")

        # Mock register response
        mock_register_resp = MagicMock()
        mock_register_resp.json.return_value = {
            "value": {
                "uploadMechanism": {
                    "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest": {
                        "uploadUrl": "https://media.licdn.com/upload/stream"
                    }
                },
                "asset": "urn:li:digitalmediaAsset:ASSET_123",
            }
        }
        mock_register_resp.raise_for_status = MagicMock()

        # Mock UGC post response
        mock_ugc_resp = MagicMock()
        mock_ugc_resp.json.return_value = {"id": "urn:li:ugcPost:LIVE_POST_456"}
        mock_ugc_resp.raise_for_status = MagicMock()

        # Mock first comment response
        mock_comment_resp = MagicMock()
        mock_comment_resp.json.return_value = {"id": "urn:li:comment:789"}
        mock_comment_resp.raise_for_status = MagicMock()

        # requests.post is called for register, create UGC, and first comment
        mock_post.side_effect = [mock_register_resp, mock_ugc_resp, mock_comment_resp]

        # requests.put for binary upload
        mock_put_resp = MagicMock()
        mock_put_resp.raise_for_status = MagicMock()
        mock_put.return_value = mock_put_resp

        with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp_mp4:
            script = VideoScript(
                script_id="test_live_03",
                topic="S/4HANA Migration Strategy",
                persona_id="sap_architect",
                sections=[],
                post_caption="Migration guide",
            )
            job = VideoRenderJob(
                job_id=script.script_id,
                script=script,
                output_file_path=tmp_mp4.name,
            )

            res = publisher.publish_live(
                job=job,
                first_comment_link="https://enterprise.sap/guide.pdf",
                dry_run=False,
            )

            self.assertEqual(res["status"], "published")
            self.assertEqual(res["post_urn"], "urn:li:ugcPost:LIVE_POST_456")
            self.assertEqual(res["asset_urn"], "urn:li:digitalmediaAsset:ASSET_123")
            self.assertEqual(res["comment_urn"], "urn:li:comment:789")
            self.assertEqual(mock_post.call_count, 3)
            self.assertEqual(mock_put.call_count, 1)


if __name__ == "__main__":
    unittest.main()

