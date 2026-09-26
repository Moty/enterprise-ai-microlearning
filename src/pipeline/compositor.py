"""Multi-Track Video Compositor for Enterprise Layouts."""

from pathlib import Path
from typing import List, Optional
from src.core.models import AudioTrack, VideoLayout, VideoRenderJob, WordTimestamp


class VideoCompositor:
    """Composites talking avatar, screencast b-roll, and kinetic subtitles into final video."""

    @staticmethod
    def generate_srt_subtitles(word_timestamps: List[WordTimestamp], output_srt_path: Path) -> Path:
        """
        Groups word timestamps into readable caption blocks (3-5 words per block)
        and formats them into standard SubRip (.srt) format.
        """
        output_srt_path.parent.mkdir(parents=True, exist_ok=True)
        
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

    def composite(
        self,
        job: VideoRenderJob,
        audio_track: AudioTrack,
        avatar_video_path: Optional[Path] = None,
        screen_asset_path: Optional[Path] = None,
        dry_run: bool = True
    ) -> VideoRenderJob:
        """
        Executes the video composition step.
        In dry_run mode, produces the .srt subtitle track and updates job state.
        """
        output_dir = Path("output") / job.job_id
        output_dir.mkdir(parents=True, exist_ok=True)

        # 1. Generate subtitle track
        srt_path = output_dir / f"{job.job_id}_captions.srt"
        self.generate_srt_subtitles(audio_track.word_timestamps, srt_path)
        job.subtitles_file_path = str(srt_path)

        # 2. Composition (simulated or FFmpeg execution)
        final_mp4_path = output_dir / f"{job.job_id}_final.mp4"
        
        if dry_run:
            job.output_file_path = str(final_mp4_path)
            job.status = "composited"
            # Write a job manifest
            with open(output_dir / "manifest.json", "w", encoding="utf-8") as f:
                f.write(job.model_dump_json(indent=2))
            return job

        # Full FFmpeg multi-layer command execution would occur here
        return job
