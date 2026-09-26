"""Unit and integration tests for Enterprise Localization Engine and Multilingual SCORM."""

import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.core.config import settings
from src.core.models import ScriptSection, SectionType, VideoRenderJob, VideoScript
from src.pipeline.localization import LocalizationEngine
from src.publishers.scorm_packager import ScormPackager


class TestLocalization(unittest.TestCase):
    def setUp(self):
        self.engine = LocalizationEngine()
        self.sample_script = VideoScript(
            script_id="test_loc_001",
            topic="Clean Core Extensibility Tiers",
            persona_id="sap_architect",
            sections=[
                ScriptSection(
                    section_type=SectionType.HOOK,
                    voiceover_text="If your team is still modifying standard SAP tables, stop now.",
                    visual_cue="Red warning box over standard table",
                    estimated_duration_sec=8.0,
                ),
                ScriptSection(
                    section_type=SectionType.PROBLEM_CONTEXT,
                    voiceover_text="Core modifications make S/4HANA Cloud upgrades impossible.",
                    visual_cue="Upgrade failure message",
                    estimated_duration_sec=12.0,
                ),
                ScriptSection(
                    section_type=SectionType.STEP_BY_STEP_SOLUTION,
                    voiceover_text="Enforce Tier 1 ABAP Cloud and Tier 2 BTP wrappers.",
                    visual_cue="Architecture diagram of 3 tiers",
                    estimated_duration_sec=30.0,
                ),
                ScriptSection(
                    section_type=SectionType.CALL_TO_ACTION,
                    voiceover_text="Download our complete Clean Core roadmap.",
                    visual_cue="CTA banner with whitepaper link",
                    estimated_duration_sec=10.0,
                ),
            ],
            post_caption="Clean core guide for SAP architects.",
        )

    def test_supported_languages(self):
        """Verify the engine supports key enterprise languages."""
        self.assertIn("de", self.engine.SUPPORTED_LANGUAGES)
        self.assertIn("es", self.engine.SUPPORTED_LANGUAGES)
        self.assertIn("fr", self.engine.SUPPORTED_LANGUAGES)
        self.assertIn("ja", self.engine.SUPPORTED_LANGUAGES)

    def test_unsupported_language_raises_value_error(self):
        """Verify requesting an unsupported language code raises ValueError."""
        with self.assertRaises(ValueError):
            self.engine.translate_script(self.sample_script, target_lang="klingon")

    def test_deterministic_translation_german(self):
        """Verify deterministic German translation preserves section types and SAP terms."""
        de_script = self.engine.translate_script(self.sample_script, target_lang="de", dry_run=True)
        self.assertEqual(de_script.language, "de")
        self.assertEqual(len(de_script.sections), 4)
        self.assertTrue(de_script.topic.startswith("SAP Microlearning (DE):"))
        self.assertIn("Clean-Core", de_script.sections[2].voiceover_text)
        self.assertEqual(de_script.script_id, "test_loc_001_de")

    def test_deterministic_translation_japanese(self):
        """Verify deterministic Japanese translation produces proper Kanji/Katakana text."""
        ja_script = self.engine.translate_script(self.sample_script, target_lang="ja", dry_run=True)
        self.assertEqual(ja_script.language, "ja")
        self.assertIn("Clean Core", ja_script.sections[2].voiceover_text)
        self.assertEqual(ja_script.script_id, "test_loc_001_ja")

    def test_generate_localized_vtt(self):
        """Verify generation of synchronized WebVTT closed captions in target language."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            base_vtt = tmp_path / "base.vtt"
            base_vtt.write_text(
                "WEBVTT\n\n1\n00:00:00.000 --> 00:00:08.000\nIntro\n\n2\n00:00:08.000 --> 00:00:20.000\nProblem\n",
                encoding="utf-8",
            )

            de_script = self.engine.translate_script(self.sample_script, "de", dry_run=True)
            output_vtt = tmp_path / "captions_de.vtt"

            res_vtt = self.engine.generate_localized_vtt(base_vtt, de_script, output_vtt)
            self.assertTrue(res_vtt.exists())
            content = res_vtt.read_text(encoding="utf-8")
            self.assertIn("WEBVTT - Language: de", content)
            self.assertIn("00:00:00.000 --> 00:00:08.000", content)

    def test_localize_job_end_to_end(self):
        """Verify localize_job updates job additional_vtt_tracks and writes disk artifacts."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            orig_output = settings.OUTPUT_DIR
            try:
                settings.OUTPUT_DIR = Path(tmp_dir)
                job_dir = settings.OUTPUT_DIR / self.sample_script.script_id
                job_dir.mkdir(parents=True, exist_ok=True)

                base_vtt = job_dir / f"{self.sample_script.script_id}_captions.vtt"
                base_vtt.write_text("WEBVTT\n\n1\n00:00:00.000 --> 00:00:10.000\nHello\n", encoding="utf-8")

                job = VideoRenderJob(
                    job_id=self.sample_script.script_id,
                    script=self.sample_script,
                    vtt_subtitles_file_path=str(base_vtt),
                )

                updated_job = self.engine.localize_job(job=job, target_languages=["de", "es", "fr"])
                self.assertIn("de", updated_job.additional_vtt_tracks)
                self.assertIn("es", updated_job.additional_vtt_tracks)
                self.assertIn("fr", updated_job.additional_vtt_tracks)

                self.assertTrue(Path(updated_job.additional_vtt_tracks["de"]).exists())
                self.assertTrue(Path(updated_job.additional_vtt_tracks["es"]).exists())
                self.assertTrue(Path(updated_job.additional_vtt_tracks["fr"]).exists())

                # Check localized script metadata files
                self.assertTrue((job_dir / f"{job.job_id}_script_de.json").exists())
                self.assertTrue((job_dir / f"{job.job_id}_script_es.json").exists())
            finally:
                settings.OUTPUT_DIR = orig_output

    def test_multilingual_scorm_packager_integration(self):
        """Verify ScormPackager creates manifest and player HTML with multi-language subtitle tracks."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            orig_output = settings.OUTPUT_DIR
            try:
                settings.OUTPUT_DIR = Path(tmp_dir)
                job_dir = settings.OUTPUT_DIR / self.sample_script.script_id
                job_dir.mkdir(parents=True, exist_ok=True)

                base_vtt = job_dir / f"{self.sample_script.script_id}_captions.vtt"
                base_vtt.write_text("WEBVTT\n\n1\n00:00:00.000 --> 00:00:10.000\nEN Text\n", encoding="utf-8")

                job = VideoRenderJob(
                    job_id=self.sample_script.script_id,
                    script=self.sample_script,
                    vtt_subtitles_file_path=str(base_vtt),
                )

                # Localize into German and Spanish
                localized_job = self.engine.localize_job(job, target_languages=["de", "es"])

                # Package into SCORM
                packager = ScormPackager()
                zip_path = packager.package(localized_job)
                self.assertTrue(zip_path.exists())

                # Inspect Zip Contents
                with zipfile.ZipFile(zip_path, "r") as zf:
                    names = zf.namelist()
                    self.assertIn("imsmanifest.xml", names)
                    self.assertIn("index.html", names)
                    self.assertIn("captions.vtt", names)
                    self.assertIn("captions_de.vtt", names)
                    self.assertIn("captions_es.vtt", names)

                    # Verify manifest references all languages
                    manifest_xml = zf.read("imsmanifest.xml").decode("utf-8")
                    self.assertIn('file href="captions_de.vtt"', manifest_xml)
                    self.assertIn('file href="captions_es.vtt"', manifest_xml)

                    # Verify HTML5 player has tracks for each language
                    player_html = zf.read("index.html").decode("utf-8")
                    self.assertIn('srclang="de"', player_html)
                    self.assertIn('label="Deutsch"', player_html)
                    self.assertIn('srclang="es"', player_html)
                    self.assertIn('label="Español"', player_html)
            finally:
                settings.OUTPUT_DIR = orig_output

    @patch("requests.post")
    def test_llm_translation_mocked(self, mock_post):
        """Verify LLM translation workflow when external API is configured."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "content": [
                {
                    "text": '{"topic": "Architektur des sauberen Kerns", "post_caption": "Leitfaden", "sections": [{"voiceover_text": "Hallo Welt", "visual_cue": "Demo"}]}'
                }
            ]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        orig_key = settings.ANTHROPIC_API_KEY
        orig_provider = settings.LLM_PROVIDER
        try:
            settings.ANTHROPIC_API_KEY = "mock_key_live"
            settings.LLM_PROVIDER = "anthropic"

            res = self.engine.translate_script(self.sample_script, target_lang="de", dry_run=False)
            self.assertEqual(res.language, "de")
            self.assertEqual(res.topic, "Architektur des sauberen Kerns")
            self.assertEqual(res.sections[0].voiceover_text, "Hallo Welt")
            mock_post.assert_called_once()
        finally:
            settings.ANTHROPIC_API_KEY = orig_key
            settings.LLM_PROVIDER = orig_provider


if __name__ == "__main__":
    unittest.main()
