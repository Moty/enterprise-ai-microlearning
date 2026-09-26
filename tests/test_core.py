"""Unit tests for core schemas, models, and configuration."""

import tempfile
import unittest
from datetime import timezone
from pathlib import Path
from pydantic import ValidationError

from src.core.config import AppSettings
from src.core.models import (
    PersonaConfig,
    ScriptSection,
    SectionType,
    VideoLayout,
    VideoRenderJob,
    VideoScript,
)
from src.pipeline.ideation import ScriptGenerator


class TestCore(unittest.TestCase):
    def test_api_key_whitespace_stripping(self):
        """Verify that leading and trailing whitespace is stripped from API keys."""
        settings_obj = AppSettings(
            ELEVENLABS_API_KEY="  test_key_123  ",
            ANTHROPIC_API_KEY="\tsecret_key\n",
        )
        self.assertEqual(settings_obj.ELEVENLABS_API_KEY, "test_key_123")
        self.assertEqual(settings_obj.ANTHROPIC_API_KEY, "secret_key")

    def test_models_utc_datetime(self):
        """Verify VideoScript created_at is timezone-aware UTC datetime."""
        script = VideoScript(
            script_id="test_id",
            topic="SAP M7021",
            persona_id="sap_architect",
            duration_target_seconds=60,
            sections=[],
            hashtags=["#SAP"],
            post_caption="Preview caption",
        )
        self.assertIsNotNone(script.created_at.tzinfo)
        self.assertEqual(script.created_at.tzinfo, timezone.utc)

    def test_video_render_job_statuses(self):
        """Verify VideoRenderJob accepts all documented transition and final statuses."""
        valid_statuses = [
            "pending",
            "generating_audio",
            "audio_generated",
            "animating",
            "avatar_rendered",
            "compositing",
            "composited",
            "completed",
            "failed",
        ]
        script = VideoScript(
            script_id="test_job_script",
            topic="Clean Core",
            persona_id="sap_architect",
            sections=[],
            post_caption="Caption",
        )
        for st in valid_statuses:
            job = VideoRenderJob(job_id="job_1", script=script, status=st)
            self.assertEqual(job.status, st)

        with self.assertRaises(ValidationError):
            VideoRenderJob(job_id="job_1", script=script, status="invalid_status")

    def test_load_persona_valid(self):
        """Verify all 3 repository personas load and deserialize cleanly."""
        generator = ScriptGenerator()
        personas = ["sap_architect", "fiori_dev", "erp_functional_consultant"]
        for pid in personas:
            persona = generator.load_persona(pid)
            self.assertEqual(persona.id, pid)
            self.assertTrue(bool(persona.name))
            self.assertTrue(bool(persona.voice_profile.voice_id))
            self.assertTrue(bool(persona.visual_profile.avatar_seed_image))

    def test_load_persona_invalid_id(self):
        """Verify loading a nonexistent persona raises FileNotFoundError."""
        generator = ScriptGenerator()
        with self.assertRaises(FileNotFoundError):
            generator.load_persona("non_existent_persona_999")

    def test_load_persona_path_traversal(self):
        """Verify path traversal attempts are rejected with ValueError."""
        generator = ScriptGenerator()
        traversal_payloads = [
            "../../.env",
            "../personas/sap_architect",
            "../../../../etc/passwd",
            "persona/nested",
            "sap architect; rm -rf",
        ]
        for payload in traversal_payloads:
            with self.assertRaises(ValueError):
                generator.load_persona(payload)

    def test_load_persona_malformed_yaml(self):
        """Verify malformed persona YAML missing required fields raises ValidationError."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            malformed_file = tmp_path / "bad_persona.yaml"
            malformed_file.write_text("id: bad\nname: Incomplete\n", encoding="utf-8")
            generator = ScriptGenerator(personas_dir=tmp_path)
            with self.assertRaises(ValidationError):
                generator.load_persona("bad_persona")


if __name__ == "__main__":
    unittest.main()
