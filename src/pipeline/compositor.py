"""Multi-Track Video Compositor for Enterprise Layouts (FFmpeg Engine)."""

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

from src.core.config import settings
from src.core.models import AudioTrack, VideoLayout, VideoRenderJob, WordTimestamp
from src.core.repositories import JobRepository, get_job_repository

logger = logging.getLogger(__name__)


class VideoCompositor:
    """Composites talking avatar, screencast b-roll, and kinetic subtitles into final video."""

    def __init__(self, repository: Optional[JobRepository] = None):
        self.repository = repository or get_job_repository()

    @staticmethod
    def generate_srt_subtitles(word_timestamps: List[WordTimestamp], output_srt_path: Path) -> Path:
        """
        Groups word timestamps into readable caption blocks (3-5 words per block)
        and formats them into standard SubRip (.srt) format.
        """
        output_srt_path = Path(output_srt_path)
        output_srt_path.parent.mkdir(parents=True, exist_ok=True)

        if not word_timestamps:
            output_srt_path.touch()
            return output_srt_path

        def format_time(seconds: float) -> str:
            millis = int((seconds % 1) * 1000)
            seconds_int = int(seconds)
            mins, secs = divmod(seconds_int, 60)
            hours, mins = divmod(mins, 60)
            return f"{hours:02d}:{mins:02d}:{secs:02d},{millis:03d}"

        blocks = []
        chunk_size = 4
        for i in range(0, len(word_timestamps), chunk_size):
            chunk = word_timestamps[i : i + chunk_size]
            if not chunk:
                continue
            start_str = format_time(chunk[0].start_time)
            end_str = format_time(chunk[-1].end_time)
            text = " ".join([w.word for w in chunk])
            blocks.append((start_str, end_str, text))

        with open(output_srt_path, "w", encoding="utf-8") as f:
            for idx, (start, end, text) in enumerate(blocks, 1):
                f.write(f"{idx}\n{start} --> {end}\n{text}\n\n")

        return output_srt_path

    @staticmethod
    def generate_vtt_subtitles(word_timestamps: List[WordTimestamp], output_vtt_path: Path) -> Path:
        """
        Groups word timestamps into readable caption blocks (3-5 words per block)
        and formats them into standard WebVTT (.vtt) format for HTML5 video players and LMS.
        """
        output_vtt_path = Path(output_vtt_path)
        output_vtt_path.parent.mkdir(parents=True, exist_ok=True)

        if not word_timestamps:
            output_vtt_path.write_text("WEBVTT\n\n", encoding="utf-8")
            return output_vtt_path

        def format_time_vtt(seconds: float) -> str:
            millis = int((seconds % 1) * 1000)
            seconds_int = int(seconds)
            mins, secs = divmod(seconds_int, 60)
            hours, mins = divmod(mins, 60)
            return f"{hours:02d}:{mins:02d}:{secs:02d}.{millis:03d}"

        blocks = []
        chunk_size = 4
        for i in range(0, len(word_timestamps), chunk_size):
            chunk = word_timestamps[i : i + chunk_size]
            if not chunk:
                continue
            start_str = format_time_vtt(chunk[0].start_time)
            end_str = format_time_vtt(chunk[-1].end_time)
            text = " ".join([w.word for w in chunk])
            blocks.append((start_str, end_str, text))

        with open(output_vtt_path, "w", encoding="utf-8") as f:
            f.write("WEBVTT\n\n")
            for idx, (start, end, text) in enumerate(blocks, 1):
                f.write(f"{idx}\n{start} --> {end}\n{text}\n\n")

        return output_vtt_path

    @classmethod
    def supports_subtitles_filter(cls) -> bool:
        """Checks if ffmpeg binary supports the 'subtitles' filter (libass)."""
        try:
            res = subprocess.run(
                ["ffmpeg", "-filters"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in res.stdout.splitlines():
                if " subtitles " in line or line.strip().startswith("subtitles "):
                    return True
            return False
        except Exception:
            return False

    def build_ffmpeg_command(
        self,
        job: VideoRenderJob,
        audio_path: Path,
        avatar_video_path: Optional[Path],
        screen_asset_path: Optional[Path],
        srt_path: Path,
        output_mp4_path: Path,
        burn_subtitles: bool = True,
    ) -> List[str]:
        """
        Constructs the FFmpeg command line arguments based on layout specifications.
        """
        layout = job.layout
        fps = job.fps or 30

        # Subtitle styling with SAP brand colors
        escaped_srt = str(srt_path).replace(":", "\\:").replace("\\", "/")
        if burn_subtitles:
            sub_filter = (
                f",subtitles='{escaped_srt}':force_style="
                f"'Fontname=Arial,Fontsize=18,Bold=1,PrimaryColour=&H0000ABF0,OutlineColour=&H00000000,MarginV=30'"
            )
        else:
            sub_filter = ""

        inputs = []
        filter_complex = []

        if layout == VideoLayout.LINKEDIN_PORTRAIT_4_5:
            # 1080x1350: Top 45% (1080x608) screen asset, Bottom 55% (1080x742) avatar
            w, h = 1080, 1350
            h_top = 608
            h_bottom = 742

            # Input 0: Screen asset (fallback to solid canvas if absent or empty)
            if screen_asset_path and screen_asset_path.exists() and screen_asset_path.stat().st_size > 0:
                inputs.extend(["-loop", "1", "-i", str(screen_asset_path)])
            else:
                inputs.extend(["-f", "lavfi", "-i", f"color=c=0x12161C:s={w}x{h_top}:r={fps}"])

            # Input 1: Avatar video (fallback to solid avatar canvas if absent or empty)
            if avatar_video_path and avatar_video_path.exists() and avatar_video_path.stat().st_size > 0:
                inputs.extend(["-stream_loop", "-1", "-i", str(avatar_video_path)])
            else:
                inputs.extend(["-f", "lavfi", "-i", f"color=c=0x1C222C:s={w}x{h_bottom}:r={fps}"])

            filter_complex = [
                f"[0:v]scale={w}:{h_top}:force_original_aspect_ratio=increase,crop={w}:{h_top}[top]",
                f"[1:v]scale={w}:{h_bottom}:force_original_aspect_ratio=increase,crop={w}:{h_bottom}[bottom]",
                f"[top][bottom]vstack=inputs=2{sub_filter}[outv]",
            ]

        elif layout == VideoLayout.WIDESCREEN_16_9:
            # 1920x1080: Fullscreen UI with PIP avatar in bottom right
            w, h = 1920, 1080
            pip_w, pip_h = 420, 420

            if screen_asset_path and screen_asset_path.exists() and screen_asset_path.stat().st_size > 0:
                inputs.extend(["-loop", "1", "-i", str(screen_asset_path)])
            else:
                inputs.extend(["-f", "lavfi", "-i", f"color=c=0x12161C:s={w}x{h}:r={fps}"])

            if avatar_video_path and avatar_video_path.exists() and avatar_video_path.stat().st_size > 0:
                inputs.extend(["-stream_loop", "-1", "-i", str(avatar_video_path)])
            else:
                inputs.extend(["-f", "lavfi", "-i", f"color=c=0x1C222C:s={pip_w}x{pip_h}:r={fps}"])

            filter_complex = [
                f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}[bg]",
                f"[1:v]scale={pip_w}:{pip_h}:force_original_aspect_ratio=increase,crop={pip_w}:{pip_h}[pip]",
                f"[bg][pip]overlay=W-w-50:H-h-50{sub_filter}[outv]",
            ]

        else:  # VERTICAL_9_16 (1080x1920)
            w, h = 1080, 1920
            h_half = 960

            if screen_asset_path and screen_asset_path.exists() and screen_asset_path.stat().st_size > 0:
                inputs.extend(["-loop", "1", "-i", str(screen_asset_path)])
            else:
                inputs.extend(["-f", "lavfi", "-i", f"color=c=0x12161C:s={w}x{h_half}:r={fps}"])

            if avatar_video_path and avatar_video_path.exists() and avatar_video_path.stat().st_size > 0:
                inputs.extend(["-stream_loop", "-1", "-i", str(avatar_video_path)])
            else:
                inputs.extend(["-f", "lavfi", "-i", f"color=c=0x1C222C:s={w}x{h_half}:r={fps}"])

            filter_complex = [
                f"[0:v]scale={w}:{h_half}:force_original_aspect_ratio=increase,crop={w}:{h_half}[top]",
                f"[1:v]scale={w}:{h_half}:force_original_aspect_ratio=increase,crop={w}:{h_half}[bottom]",
                f"[top][bottom]vstack=inputs=2{sub_filter}[outv]",
            ]

        # Audio Input
        inputs.extend(["-i", str(audio_path)])
        audio_idx = inputs.count("-i") - 1

        subtitle_maps = []
        if not burn_subtitles and srt_path and srt_path.exists() and srt_path.stat().st_size > 0:
            inputs.extend(["-i", str(srt_path)])
            sub_idx = inputs.count("-i") - 1
            subtitle_maps = [
                "-map", f"{sub_idx}:s",
                "-c:s", "mov_text",
                "-metadata:s:s:0", f"language={job.script.language or 'eng'}"
            ]

        cmd = [
            "ffmpeg",
            "-y",
            *inputs,
            "-filter_complex",
            ";".join(filter_complex),
            "-map",
            "[outv]",
            "-map",
            f"{audio_idx}:a",
            *subtitle_maps,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-pix_fmt",
            "yuv420p",
            str(output_mp4_path),
        ]
        return cmd

    def composite(
        self,
        job: VideoRenderJob,
        audio_track: AudioTrack,
        avatar_video_path: Optional[Path] = None,
        screen_asset_path: Optional[Path] = None,
        dry_run: bool = True,
    ) -> VideoRenderJob:
        """
        Executes the video composition step.
        Generates .srt subtitles, constructs the FFmpeg render script, and executes composition.
        """
        output_dir = settings.OUTPUT_DIR / job.job_id
        output_dir.mkdir(parents=True, exist_ok=True)

        # 1. Generate subtitle tracks (SRT for FFmpeg, VTT for HTML5/LMS)
        srt_path = output_dir / f"{job.job_id}_captions.srt"
        vtt_path = output_dir / f"{job.job_id}_captions.vtt"
        self.generate_srt_subtitles(audio_track.word_timestamps, srt_path)
        self.generate_vtt_subtitles(audio_track.word_timestamps, vtt_path)
        job.subtitles_file_path = str(srt_path)
        job.vtt_subtitles_file_path = str(vtt_path)

        # 2. Composition paths
        final_mp4_path = output_dir / f"{job.job_id}_final.mp4"
        audio_path = Path(audio_track.audio_file_path)

        # 3. Build FFmpeg command and save script
        burn_subtitles = self.supports_subtitles_filter() if not dry_run else True
        ffmpeg_cmd = self.build_ffmpeg_command(
            job=job,
            audio_path=audio_path,
            avatar_video_path=avatar_video_path,
            screen_asset_path=screen_asset_path,
            srt_path=srt_path,
            output_mp4_path=final_mp4_path,
            burn_subtitles=burn_subtitles,
        )

        render_script = output_dir / "render_ffmpeg.sh"
        with open(render_script, "w", encoding="utf-8") as f:
            f.write("#!/bin/bash\nset -e\n")
            f.write("echo 'Rendering enterprise microlearning video composition...'\n")
            f.write(" ".join([f'"{arg}"' if " " in arg or ";" in arg else arg for arg in ffmpeg_cmd]) + "\n")
            f.write("echo 'Render complete: " + str(final_mp4_path) + "'\n")

        render_script.chmod(0o755)

        if dry_run:
            if not final_mp4_path.exists():
                final_mp4_path.touch()
            job.output_file_path = str(final_mp4_path)
            job.status = "composited"
            self.repository.save_job(job)
            return job

        # Live FFmpeg rendering
        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            logger.warning(
                "FFmpeg binary not detected on system path. "
                "Generated render script at: %s", render_script
            )
            job.error_message = (
                "FFmpeg is not installed on system path. "
                f"Run the generated script manually: {render_script}"
            )
            job.status = "failed"
            self.repository.save_job(job)
            return job

        try:
            job.status = "compositing"
            self.repository.save_job(job)

            result = subprocess.run(
                ffmpeg_cmd,
                capture_output=True,
                text=True,
                check=True,
            )
            job.output_file_path = str(final_mp4_path)
            job.status = "completed"
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg render failed: {e.stderr}")
            job.error_message = f"FFmpeg render failed: {e.stderr[:300]}"
            job.status = "failed"
        except Exception as e:
            logger.error(f"Unexpected compositor error: {e}")
            job.error_message = str(e)
            job.status = "failed"

        self.repository.save_job(job)
        return job
