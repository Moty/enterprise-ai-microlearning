#!/usr/bin/env python3
"""Enterprise AI Microlearning Engine CLI Entrypoint."""

import sys
import uuid
from pathlib import Path
import typer
from rich.console import Console
from rich.table import Table

from src.core.config import settings
from src.core.models import VideoLayout, VideoRenderJob
from src.pipeline.avatar_engine import AvatarEngine
from src.pipeline.compositor import VideoCompositor
from src.pipeline.ideation import ScriptGenerator
from src.pipeline.voice_engine import VoiceEngine
from src.publishers.linkedin_publisher import LinkedInPublisher

app = typer.Typer(help="Enterprise AI Microlearning Engine for SAP & B2B Content")
console = Console()


@app.command()
def list_personas():
    """Lists all configured AI-SME personas."""
    generator = ScriptGenerator()
    personas_dir = settings.CONFIG_DIR / "personas"
    table = Table(title="Available AI-SME Personas")
    table.add_column("Persona ID", style="cyan", no_wrap=True)
    table.add_column("Name", style="magenta")
    table.add_column("Title", style="green")
    table.add_column("Focus Areas", style="white")

    for file in sorted(personas_dir.glob("*.yaml")):
        p = generator.load_persona(file.stem)
        table.add_row(p.id, p.name, p.title, ", ".join(p.content_focus[:2]) + "...")

    console.print(table)


@app.command()
def generate(
    topic: str = typer.Option(..., "--topic", "-t", help="Topic or SAP Error Code"),
    persona: str = typer.Option("sap_architect", "--persona", "-p", help="Persona ID"),
    dry_run: bool = typer.Option(True, "--dry-run", help="Run without calling paid external APIs"),
):
    """Generates a complete microlearning video package from a topic and persona."""
    console.print(f"[bold blue]🚀 Starting Microlearning Engine for topic:[/bold blue] {topic}")
    settings.init_directories()

    # 1. Ideation & Scripting
    console.print("[cyan]Step 1: Generating structured 60s enterprise script...[/cyan]")
    script_gen = ScriptGenerator()
    script = script_gen.generate_script(topic=topic, persona_id=persona)
    console.print(f"[green]✔ Script created with {len(script.sections)} sections.[/green]")

    # 2. Voice Synthesis
    console.print("[cyan]Step 2: Synthesizing voiceover with SAP phonetic normalization...[/cyan]")
    voice_engine = VoiceEngine()
    persona_config = script_gen.load_persona(persona)
    audio_path = settings.OUTPUT_DIR / f"{script.script_id}_voice.wav"
    full_text = " ".join([s.voiceover_text for s in script.sections])
    audio_track = voice_engine.synthesize(
        text=full_text,
        voice_id=persona_config.voice_profile.voice_id,
        output_path=audio_path,
        dry_run=dry_run
    )
    console.print(f"[green]✔ Audio track duration: {audio_track.duration_seconds}s ({len(audio_track.word_timestamps)} words timed).[/green]")

    # 3. Avatar Animation & Lip-Sync
    console.print("[cyan]Step 3: Animating AI-SME avatar with lip-sync...[/cyan]")
    avatar_engine = AvatarEngine()
    avatar_video_path = settings.OUTPUT_DIR / f"{script.script_id}_avatar.mp4"
    avatar_engine.animate_avatar(
        seed_image_path=Path(persona_config.visual_profile.avatar_seed_image),
        audio_file_path=audio_path,
        output_video_path=avatar_video_path,
        dry_run=dry_run
    )
    console.print("[green]✔ Avatar animation processed.[/green]")

    # 4. Multi-Layer Video Composition
    console.print("[cyan]Step 4: Compositing video with kinetic captions & layout...[/cyan]")
    compositor = VideoCompositor()
    job = VideoRenderJob(
        job_id=script.script_id,
        script=script,
        layout=VideoLayout.LINKEDIN_PORTRAIT_4_5
    )
    composited_job = compositor.composite(
        job=job,
        audio_track=audio_track,
        avatar_video_path=avatar_video_path,
        dry_run=dry_run
    )
    console.print(f"[green]✔ Subtitles generated at: {composited_job.subtitles_file_path}[/green]")
    console.print(f"[green]✔ Final video package rendered at: {composited_job.output_file_path}[/green]")

    # 5. LinkedIn Distribution Package
    console.print("[cyan]Step 5: Formatting LinkedIn distribution package...[/cyan]")
    publisher = LinkedInPublisher()
    pkg_file = publisher.publish_draft(composited_job, settings.OUTPUT_DIR / script.script_id)
    console.print(f"[green]✔ LinkedIn distribution metadata saved to: {pkg_file}[/green]")

    console.print("\n[bold green]🎉 Video production pipeline completed successfully![/bold green]")
    console.print(f"Post Preview:\n[italic]{script.post_caption[:250]}...[/italic]")


if __name__ == "__main__":
    app()
