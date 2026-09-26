"""Unit tests for the microlearning processing pipeline."""

import json
import tempfile
import unittest
from pathlib import Path

from src.core.config import settings
from src.core.models import (
    AudioTrack,
    ScriptSection,
    SectionType,
    VideoLayout,
    VideoRenderJob,
    VideoScript,
    WordTimestamp,
)
from src.pipeline.avatar_engine import AvatarEngine
from src.pipeline.compositor import VideoCompositor
from src.pipeline.ideation import ScriptGenerator
from src.pipeline.voice_engine import VoiceEngine


class TestPipeline(unittest.TestCase):
    def test_generate_script_section_count_and_types(self):
        """Verify script generation produces 4 sections in correct sequence."""
        generator = ScriptGenerator()
        script = generator.generate_script(topic="SAP Clean Core", persona_id="sap_architect")

        self.assertEqual(len(script.sections), 4)
        expected_types = [
            SectionType.HOOK,
            SectionType.PROBLEM_CONTEXT,
            SectionType.STEP_BY_STEP_SOLUTION,
            SectionType.CALL_TO_ACTION,
        ]
        actual_types = [s.section_type for s in script.sections]
        self.assertEqual(actual_types, expected_types)

    def test_generate_script_duration_sum(self):
        """Verify sum of section durations targets ~60 seconds."""
        generator = ScriptGenerator()
        script = generator.generate_script(topic="SAP Clean Core", persona_id="sap_architect")

        total_estimated = sum(s.estimated_duration_sec for s in script.sections)
        self.assertAlmostEqual(total_estimated, 60.0, delta=1.0)

    def test_normalize_sap_phonetics_basic(self):
        """Verify basic SAP acronym normalization."""
        raw = "SAP with S/4HANA and BTP using ABAP, Fiori, CDS, RAP, and BAPI"
        normalized = VoiceEngine.normalize_sap_phonetics(raw)
        self.assertIn("S-A-P", normalized)
        self.assertIn("S four HAH-nah", normalized)
        self.assertIn("B-T-P", normalized)
        self.assertIn("AH-bop", normalized)
        self.assertIn("Fee-OR-ee", normalized)
        self.assertIn("C-D-S", normalized)
        self.assertIn("R-A-P", normalized)
        self.assertIn("BAH-pee", normalized)

    def test_normalize_sap_phonetics_boundaries(self):
        """Verify regex boundary matching at start, end, and around punctuation."""
        # Sentence start
        self.assertTrue(VoiceEngine.normalize_sap_phonetics("SAP is an ERP.").startswith("S-A-P"))
        # Punctuation following
        self.assertIn("S-A-P,", VoiceEngine.normalize_sap_phonetics("Learn SAP, then apply."))
        # Possessive
        self.assertIn("S-A-P's", VoiceEngine.normalize_sap_phonetics("SAP's strategy is Clean Core."))
        # Substrings inside words should NOT be modified
        self.assertIn("sapling", VoiceEngine.normalize_sap_phonetics("A sapling was planted."))
        self.assertIn("disapprove", VoiceEngine.normalize_sap_phonetics("I disapprove of modifications."))

    def test_synthesize_empty_text_error(self):
        """Verify synthesizing empty string raises ValueError."""
        engine = VoiceEngine()
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with self.assertRaises(ValueError):
                engine.synthesize(text="   ", voice_id="test_voice", output_path=tmp_path / "test.wav")

    def test_synthesize_dry_run_timestamps(self):
        """Verify dry-run synthesis creates audio track and monotonically increasing timestamps."""
        engine = VoiceEngine()
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            out_audio = tmp_path / "test_audio.wav"
            track = engine.synthesize(
                text="Troubleshooting SAP error in S/4HANA",
                voice_id="sample_voice",
                output_path=out_audio,
                dry_run=True,
            )
            self.assertGreater(track.duration_seconds, 0)
            self.assertGreater(len(track.word_timestamps), 0)
            self.assertTrue(out_audio.exists())

            # Verify monotonicity
            last_end = 0.0
            for wt in track.word_timestamps:
                self.assertGreaterEqual(wt.start_time, last_end)
                self.assertGreater(wt.end_time, wt.start_time)
                last_end = wt.end_time

    def test_synthesize_dry_run_creates_metadata_file(self):
        """Verify .json metadata file is created alongside audio."""
        engine = VoiceEngine()
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            out_audio = tmp_path / "voice.wav"
            engine.synthesize(
                text="Quick SAP tip",
                voice_id="sample_voice",
                output_path=out_audio,
                dry_run=True,
            )
            meta_json = out_audio.with_suffix(".json")
            self.assertTrue(meta_json.exists())
            data = json.loads(meta_json.read_text(encoding="utf-8"))
            self.assertIsInstance(data, list)
            self.assertGreater(len(data), 0)

    def test_avatar_engine_dry_run_valid_json(self):
        """Verify avatar engine dry run writes valid JSON metadata without unescaped string injection."""
        engine = AvatarEngine()
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            seed_image = tmp_path / "avatars" / "marcus.png"
            audio_path = tmp_path / "audio with spaces & quotes.wav"
            output_video = tmp_path / "avatar_output.mp4"

            engine.animate_avatar(
                seed_image_path=seed_image,
                audio_file_path=audio_path,
                output_video_path=output_video,
                dry_run=True,
            )

            meta_file = output_video.with_suffix(".meta.json")
            self.assertTrue(meta_file.exists())
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            self.assertEqual(meta["seed_image"], str(seed_image))
            self.assertEqual(meta["audio"], str(audio_path))
            self.assertEqual(meta["status"], "simulated")
            self.assertTrue(output_video.exists())

    def test_generate_srt_subtitles_format(self):
        """Verify standard SubRip SRT block formatting."""
        timestamps = [
            WordTimestamp(word="Stop", start_time=0.0, end_time=0.3),
            WordTimestamp(word="modifying", start_time=0.3, end_time=0.7),
            WordTimestamp(word="standard", start_time=0.7, end_time=1.1),
            WordTimestamp(word="tables", start_time=1.1, end_time=1.5),
            WordTimestamp(word="immediately.", start_time=1.5, end_time=2.0),
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            srt_out = tmp_path / "captions.srt"
            VideoCompositor.generate_srt_subtitles(timestamps, srt_out)

            self.assertTrue(srt_out.exists())
            content = srt_out.read_text(encoding="utf-8")
            self.assertIn("1\n00:00:00,000 --> 00:00:01,500\nStop modifying standard tables", content)
            self.assertIn("2\n00:00:01,500 --> 00:00:02,000\nimmediately.", content)

    def test_generate_srt_subtitles_empty_input(self):
        """Verify empty timestamp list creates empty file without crashing."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            srt_out = tmp_path / "empty.srt"
            VideoCompositor.generate_srt_subtitles([], srt_out)
            self.assertTrue(srt_out.exists())

    def test_composite_dry_run_creates_manifest(self):
        """Verify composite creates manifest.json in settings.OUTPUT_DIR / job_id."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            original_output = settings.OUTPUT_DIR
            try:
                settings.OUTPUT_DIR = tmp_path
                compositor = VideoCompositor()
                script = VideoScript(
                    script_id="test_manifest_script",
                    topic="Clean Core",
                    persona_id="sap_architect",
                    sections=[],
                    post_caption="Post",
                )
                job = VideoRenderJob(job_id=script.script_id, script=script)
                audio_track = AudioTrack(
                    audio_file_path=str(tmp_path / "audio.wav"),
                    duration_seconds=5.0,
                    word_timestamps=[
                        WordTimestamp(word="Hello", start_time=0.0, end_time=0.5),
                        WordTimestamp(word="World", start_time=0.5, end_time=1.0),
                    ],
                )
                res = compositor.composite(job=job, audio_track=audio_track, dry_run=True)

                self.assertEqual(res.status, "composited")
                self.assertTrue((tmp_path / script.script_id / "manifest.json").exists())
                self.assertTrue((tmp_path / script.script_id / f"{script.script_id}_captions.srt").exists())
                self.assertTrue((tmp_path / script.script_id / f"{script.script_id}_final.mp4").exists())
                self.assertTrue((tmp_path / script.script_id / "render_ffmpeg.sh").exists())
            finally:
                settings.OUTPUT_DIR = original_output

    def test_persona_tailored_specialization(self):
        """Verify each persona receives tailored hooks and steps aligned with their domain."""
        generator = ScriptGenerator()

        # Architect
        arch_script = generator.generate_script(topic="Extensibility", persona_id="sap_architect")
        self.assertIn("Clean Core", arch_script.sections[0].voiceover_text + arch_script.sections[1].voiceover_text)

        # Fiori Dev
        fiori_script = generator.generate_script(topic="Smart Table", persona_id="fiori_dev")
        self.assertIn("CDS", fiori_script.sections[0].voiceover_text + fiori_script.sections[2].voiceover_text)

        # Functional Consultant with T-code
        func_script = generator.generate_script(
            topic="Stock Deficit",
            persona_id="erp_functional_consultant",
            specific_error_or_tcode="M7021",
        )
        self.assertIn("M7021", func_script.sections[0].voiceover_text)
        self.assertIn("MMBE", func_script.sections[2].voiceover_text)

    def test_build_ffmpeg_command_layouts(self):
        """Verify FFmpeg filtergraphs are constructed properly for all three layouts."""
        compositor = VideoCompositor()
        script = VideoScript(
            script_id="test_filter_script",
            topic="Clean Core",
            persona_id="sap_architect",
            sections=[],
            post_caption="Post",
        )

        for layout in [
            VideoLayout.LINKEDIN_PORTRAIT_4_5,
            VideoLayout.WIDESCREEN_16_9,
            VideoLayout.VERTICAL_9_16,
        ]:
            job = VideoRenderJob(job_id=script.script_id, script=script, layout=layout)
            cmd = compositor.build_ffmpeg_command(
                job=job,
                audio_path=Path("/tmp/audio.wav"),
                avatar_video_path=Path("/tmp/avatar.mp4"),
                screen_asset_path=Path("/tmp/screen.png"),
                srt_path=Path("/tmp/captions.srt"),
                output_mp4_path=Path("/tmp/out.mp4"),
            )
            self.assertEqual(cmd[0], "ffmpeg")
            cmd_str = " ".join(cmd)
            self.assertIn("subtitles=", cmd_str)
            if layout == VideoLayout.WIDESCREEN_16_9:
                self.assertIn("overlay=", cmd_str)
            else:
                self.assertIn("vstack=", cmd_str)


if __name__ == "__main__":
    unittest.main()
