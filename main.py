#!/usr/bin/env python3
"""Enterprise AI Microlearning Engine CLI Entrypoint."""

from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table

from src.core.config import settings
from src.core.models import VideoLayout, VideoRenderJob
from src.core.repositories import get_job_repository
from src.pipeline.analytics import AnalyticsEngine
from src.pipeline.asset_generator import AssetGenerator
from src.pipeline.avatar_engine import AvatarEngine
from src.pipeline.compositor import VideoCompositor
from src.pipeline.ideation import ScriptGenerator
from src.pipeline.localization import LocalizationEngine
from src.pipeline.screen_recorder import ScreenRecorderEngine
from src.pipeline.topic_ingestion import TopicIngestionEngine
from src.pipeline.voice_engine import VoiceEngine
from src.pipeline.ticket_deflection import TicketDeflectionEngine
from src.publishers import LinkedInPublisher, ScormPackager, WebhookPublisher




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
    error_code: Optional[str] = typer.Option(None, "--error-code", "-e", help="Specific SAP Error Code or T-Code (e.g. M7021, SM59)"),
    layout: str = typer.Option("linkedin_portrait", "--layout", "-l", help="Layout: linkedin_portrait (4:5), vertical (9:16), widescreen (16:9)"),
    export_scorm: bool = typer.Option(True, "--export-scorm/--no-export-scorm", help="Package for Enterprise LMS (SCORM 1.2)"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Run without calling paid external APIs"),
):
    """Generates a complete microlearning video package from a topic and persona."""
    console.print(f"[bold blue]🚀 Starting Microlearning Engine for topic:[/bold blue] {topic}")
    settings.init_directories()

    # 1. Ideation & Scripting
    console.print("[cyan]Step 1: Generating structured 60s enterprise script...[/cyan]")
    script_gen = ScriptGenerator()
    script = script_gen.generate_script(
        topic=topic,
        persona_id=persona,
        specific_error_or_tcode=error_code,
        dry_run=dry_run,
    )
    console.print(f"[green]✔ Script created with {len(script.sections)} sections (ID: {script.script_id}).[/green]")

    job_dir = settings.OUTPUT_DIR / script.script_id
    job_dir.mkdir(parents=True, exist_ok=True)
    persona_config = script_gen.load_persona(persona)

    # 2. Dynamic Asset & Slide Generation
    console.print("[cyan]Step 2: Generating high-contrast visual B-Roll slide...[/cyan]")
    asset_gen = AssetGenerator()
    slide_path = job_dir / "screen_overlay.png"
    asset_gen.generate_title_card(
        topic=topic,
        persona_name=persona_config.name,
        persona_title=persona_config.title,
        output_path=slide_path,
    )
    console.print(f"[green]✔ Visual overlay generated at: {slide_path}[/green]")

    # 3. Voice Synthesis
    console.print("[cyan]Step 3: Synthesizing voiceover with SAP phonetic normalization...[/cyan]")
    voice_engine = VoiceEngine()
    audio_path = job_dir / f"{script.script_id}_voice.wav"
    full_text = " ".join([s.voiceover_text for s in script.sections])
    audio_track = voice_engine.synthesize(
        text=full_text,
        voice_id=persona_config.voice_profile.voice_id,
        output_path=audio_path,
        dry_run=dry_run,
    )
    console.print(f"[green]✔ Audio track duration: {audio_track.duration_seconds}s ({len(audio_track.word_timestamps)} words timed).[/green]")

    # 4. Avatar Animation & Lip-Sync
    console.print("[cyan]Step 4: Animating AI-SME avatar with lip-sync...[/cyan]")
    avatar_engine = AvatarEngine()
    avatar_video_path = job_dir / f"{script.script_id}_avatar.mp4"
    avatar_engine.animate_avatar(
        seed_image_path=Path(persona_config.visual_profile.avatar_seed_image),
        audio_file_path=audio_path,
        output_video_path=avatar_video_path,
        dry_run=dry_run,
    )
    console.print("[green]✔ Avatar animation processed.[/green]")

    # 5. Multi-Layer Video Composition
    console.print("[cyan]Step 5: Compositing video with kinetic captions & layout...[/cyan]")
    compositor = VideoCompositor()
    layout_enum = VideoLayout.LINKEDIN_PORTRAIT_4_5
    if layout == "vertical":
        layout_enum = VideoLayout.VERTICAL_9_16
    elif layout == "widescreen":
        layout_enum = VideoLayout.WIDESCREEN_16_9

    job = VideoRenderJob(
        job_id=script.script_id,
        script=script,
        layout=layout_enum,
    )
    composited_job = compositor.composite(
        job=job,
        audio_track=audio_track,
        avatar_video_path=avatar_video_path,
        screen_asset_path=slide_path,
        dry_run=dry_run,
    )
    console.print(f"[green]✔ Subtitles generated at: {composited_job.subtitles_file_path}[/green]")
    console.print(f"[green]✔ Final video package rendered at: {composited_job.output_file_path}[/green]")
    console.print(f"[green]✔ FFmpeg render script ready at: {job_dir / 'render_ffmpeg.sh'}[/green]")

    # 6. LinkedIn Distribution Package
    console.print("[cyan]Step 6: Formatting LinkedIn distribution package...[/cyan]")
    publisher = LinkedInPublisher()
    pkg_file = publisher.publish_draft(composited_job, job_dir)
    console.print(f"[green]✔ LinkedIn distribution metadata saved to: {pkg_file}[/green]")

    # 7. Enterprise LMS Packaging (SCORM 1.2 & HTML5 Accessibility)
    if export_scorm:
        console.print("[cyan]Step 7: Packaging for Enterprise LMS (SCORM 1.2 / HTML5 Player)...[/cyan]")
        scorm_packager = ScormPackager()
        scorm_zip = scorm_packager.package(composited_job, job_dir)
        console.print(f"[green]✔ Enterprise SCORM 1.2 LMS package ready: {scorm_zip}[/green]")

    console.print("\n[bold green]🎉 Video production pipeline completed successfully![/bold green]")
    console.print(f"Post Preview:\n[italic]{script.post_caption[:250]}...[/italic]")


@app.command()
def package_scorm(job_id: str = typer.Argument(..., help="Job ID to package into SCORM 1.2")):
    """Packages an existing render job into a SCORM 1.2 LMS zip archive."""
    repo = get_job_repository()
    job = repo.get_job(job_id)
    if not job:
        console.print(f"[bold red]Job not found:[/bold red] {job_id}")
        raise typer.Exit(code=1)

    packager = ScormPackager()
    zip_path = packager.package(job)
    console.print(f"[bold green]✔ SCORM 1.2 package created at:[/bold green] {zip_path}")


@app.command()
def notify_channel(
    job_id: str = typer.Argument(..., help="Job ID"),
    channel: str = typer.Option("teams", "--channel", "-c", help="'teams' or 'slack'"),
    webhook_url: Optional[str] = typer.Option(None, "--url", "-u", help="Webhook URL"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Preview payload without sending network request"),
):
    """Dispatches or previews an enterprise microlearning drop to Microsoft Teams or Slack."""
    repo = get_job_repository()
    job = repo.get_job(job_id)
    if not job:
        console.print(f"[bold red]Job not found:[/bold red] {job_id}")
        raise typer.Exit(code=1)

    publisher = WebhookPublisher()
    if channel.lower() == "teams":
        res = publisher.send_teams(webhook_url or "https://example.com/teams-webhook", job, dry_run=dry_run)
    else:
        res = publisher.send_slack(webhook_url or "https://example.com/slack-webhook", job, dry_run=dry_run)

    console.print(f"[bold green]✔ Notification result ({channel}):[/bold green]")
    console.print_json(data=res)


@app.command()
def list_jobs(
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by job status"),
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum jobs to list"),
):
    """Lists historical video production jobs from the active repository (Local or Firestore)."""
    repo = get_job_repository()
    jobs = repo.list_jobs(status=status, limit=limit)

    table = Table(title=f"Video Render Jobs (Backend: {settings.STORAGE_BACKEND})")
    table.add_column("Job ID", style="cyan", no_wrap=True)
    table.add_column("Topic", style="white")
    table.add_column("Persona", style="magenta")
    table.add_column("Status", style="green")
    table.add_column("Created", style="dim")

    for j in jobs:
        created_str = j.script.created_at.strftime("%Y-%m-%d %H:%M") if j.script.created_at else "N/A"
        table.add_row(
            j.job_id,
            j.script.topic,
            j.script.persona_id,
            j.status,
            created_str,
        )

    console.print(table)


@app.command()
def get_job(job_id: str = typer.Argument(..., help="Job ID")):
    """Fetches details for a specific video job."""
    repo = get_job_repository()
    job = repo.get_job(job_id)
    if not job:
        console.print(f"[bold red]Job not found:[/bold red] {job_id}")
        raise typer.Exit(code=1)

    console.print(f"[bold cyan]Job ID:[/bold cyan] {job.job_id}")
    console.print(f"[bold]Topic:[/bold] {job.script.topic}")
    console.print(f"[bold]Persona:[/bold] {job.script.persona_id}")
    console.print(f"[bold]Status:[/bold] {job.status}")
    console.print(f"[bold]Output MP4:[/bold] {job.output_file_path or 'N/A'}")
    console.print(f"[bold]Subtitles SRT:[/bold] {job.subtitles_file_path or 'N/A'}")
    if job.error_message:
        console.print(f"[bold red]Error:[/bold red] {job.error_message}")


@app.command()
def list_topics(
    limit: int = typer.Option(10, "--limit", "-n", help="Maximum topics to display"),
):
    """Lists curated high-impact SAP topics and error codes ready for microlearning."""
    engine = TopicIngestionEngine()
    topics = engine.get_curated_topics(limit=limit)
    table = Table(title="Curated Enterprise SAP Topic Catalog")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Topic Title", style="white")
    table.add_column("Error Code", style="yellow")
    table.add_column("Persona", style="magenta")
    table.add_column("Impact", style="green")

    for t in topics:
        table.add_row(
            t["id"],
            t["topic"],
            t.get("error_code") or "N/A",
            t["persona_id"],
            str(t.get("impact_score", "N/A")),
        )

    console.print(table)


@app.command()
def auto_ingest(
    source: str = typer.Option("catalog", "--source", "-s", help="Topic source: 'catalog' or 'rss'"),
    feed_url: str = typer.Option("https://blogs.sap.com/feed/", "--feed-url", help="RSS feed URL when source=rss"),
    limit: int = typer.Option(2, "--limit", "-n", help="Number of microlearning modules to generate"),
    export_scorm: bool = typer.Option(True, "--export-scorm/--no-export-scorm", help="Export SCORM 1.2 zip packages"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Run in dry-run mode without external API charges"),
):
    """Autonomously ingests SAP topics and batch-produces microlearning packages."""
    console.print(f"[bold blue]🤖 Initializing Autonomous SAP Microlearning Engine (Source: {source})[/bold blue]")
    settings.init_directories()

    engine = TopicIngestionEngine()
    if source.lower() == "rss":
        console.print(f"[cyan]Fetching and analyzing live RSS feed: {feed_url}...[/cyan]")
        topics = engine.crawl_rss_feed(feed_url=feed_url, limit=limit)
        if not topics:
            console.print("[bold red]No topics found in RSS feed or failed to reach URL.[/bold red]")
            raise typer.Exit(code=1)
    else:
        topics = engine.get_curated_topics(limit=limit)

    console.print(f"[green]✔ Ingested {len(topics)} topics for automated batch production.[/green]\n")

    jobs = engine.execute_batch_production(
        topics=topics,
        dry_run=dry_run,
        export_scorm=export_scorm,
    )

    console.print(f"\n[bold green]🎉 Batch production finished! Successfully generated {len(jobs)} modules:[/bold green]")
    for job in jobs:
        console.print(f" • [cyan]{job.job_id}[/cyan]: {job.script.topic} ([magenta]{job.script.persona_id}[/magenta])")


@app.command()
def publish_linkedin(
    job_id: str = typer.Argument(..., help="Job ID to publish to LinkedIn"),
    first_comment_link: Optional[str] = typer.Option(None, "--first-comment-link", "-c", help="Link for first comment"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Simulate without real API call"),
):
    """Publishes a completed video microlearning package directly to LinkedIn."""
    repo = get_job_repository()
    job = repo.get_job(job_id)
    if not job:
        console.print(f"[bold red]Job not found:[/bold red] {job_id}")
        raise typer.Exit(code=1)

    publisher = LinkedInPublisher()
    console.print(f"[cyan]Publishing video microlearning module '{job.job_id}' to LinkedIn...[/cyan]")
    res = publisher.publish_live(
        job=job,
        first_comment_link=first_comment_link,
        dry_run=dry_run,
    )
    console.print("[bold green]✔ LinkedIn Publish Result:[/bold green]")
    console.print_json(data=res)


@app.command()
def localize(
    job_id: str = typer.Argument(..., help="Job ID to localize"),
    languages: str = typer.Option("de,es,fr", "--languages", "-l", help="Comma-separated language codes: de, es, fr, ja"),
    export_scorm: bool = typer.Option(True, "--export-scorm/--no-export-scorm", help="Regenerate multilingual SCORM package"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Run without calling paid external translation APIs"),
):
    """Localizes an existing microlearning package into German, Spanish, French, or Japanese."""
    repo = get_job_repository()
    job = repo.get_job(job_id)
    if not job:
        console.print(f"[bold red]Job not found:[/bold red] {job_id}")
        raise typer.Exit(code=1)

    lang_list = [l.strip().lower() for l in languages.split(",") if l.strip()]
    console.print(f"[bold blue]🌍 Localizing module '{job.job_id}' into: {', '.join(lang_list)}[/bold blue]")

    engine = LocalizationEngine()
    updated_job = engine.localize_job(job=job, target_languages=lang_list, dry_run=dry_run)

    for lang in lang_list:
        if lang in updated_job.additional_vtt_tracks:
            vtt_p = updated_job.additional_vtt_tracks[lang]
            label = engine.SUPPORTED_LANGUAGES.get(lang, lang)
            console.print(f"  [green]✔ {label} ({lang}) subtitles:[/green] {vtt_p}")

    if export_scorm:
        console.print("[cyan]Re-bundling multilingual SCORM 1.2 package...[/cyan]")
        packager = ScormPackager()
        scorm_zip = packager.package(updated_job)
        console.print(f"[bold green]✔ Multilingual SCORM 1.2 package updated:[/bold green] {scorm_zip}")

    console.print("[bold green]🎉 Localization complete![/bold green]")


@app.command()
def record_demo(
    topic: str = typer.Option("SAP Error M7021: Stock Deficit", "--topic", "-t", help="Topic"),
    error_code: Optional[str] = typer.Option("M7021", "--error-code", "-e", help="SAP Error code"),
    output: Path = typer.Option(Path("output/fiori_demo.png"), "--output", "-o", help="Output file path"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Simulate screen capture"),
):
    """Captures an authentic SAP Fiori 3.0 UI demo screen overlay for video B-roll."""
    recorder = ScreenRecorderEngine()
    res_path = recorder.create_broll_asset(
        job_id="demo",
        topic=topic,
        error_code=error_code,
        output_path=output,
        dry_run=dry_run,
    )
    console.print(f"[bold green]✔ SAP Fiori screen asset captured:[/bold green] {res_path}")


@app.command()
def record_analytics(
    job_id: str = typer.Argument(..., help="Job ID"),
    views: int = typer.Option(1000, "--views", "-v", help="Total viewer impressions"),
    completions: int = typer.Option(720, "--completions", "-c", help="Viewers completing 60s"),
    avg_watch_time: float = typer.Option(49.2, "--watch-time", "-w", help="Average watch time in seconds"),
    hook_dropoff: float = typer.Option(0.12, "--hook-dropoff", "-d", help="Percentage dropping off in first 5s (0.0-1.0)"),
    hook_style: str = typer.Option("warning_symptom", "--hook-style", "-s", help="Hook style category"),
):
    """Records real or simulated viewer engagement telemetry to evaluate retention performance."""
    engine = AnalyticsEngine()
    metric = engine.record_telemetry(
        job_id=job_id,
        views_count=views,
        completions_count=completions,
        avg_watch_time_sec=avg_watch_time,
        hook_dropoff_rate=hook_dropoff,
        hook_style=hook_style,
    )
    console.print(f"[bold green]✔ Telemetry recorded for job:[/bold green] {job_id}")
    console.print(f"  • Completion Rate: [cyan]{metric.completions_count / max(metric.views_count, 1):.1%}[/cyan]")
    console.print(f"  • Retention Score: [bold green]{metric.retention_score} / 100[/bold green]")


@app.command()
def analytics_report(persona_id: str = typer.Option("sap_architect", "--persona", "-p", help="Persona ID")):
    """Displays executive retention benchmark report and AI-SME hook optimization recommendations."""
    engine = AnalyticsEngine()
    report = engine.get_summary_report()

    table = Table(title="Microlearning Retention Telemetry Benchmark")
    table.add_column("Job ID", style="cyan")
    table.add_column("Views", style="white")
    table.add_column("Completion", style="green")
    table.add_column("Avg Watch", style="yellow")
    table.add_column("Hook Dropoff", style="red")
    table.add_column("Retention Score", style="bold green")

    for mod in report["modules"]:
        comp_rate = mod["completions_count"] / max(mod["views_count"], 1)
        table.add_row(
            mod["job_id"],
            str(mod["views_count"]),
            f"{comp_rate:.1%}",
            f"{mod['avg_watch_time_sec']:.1f}s",
            f"{mod['hook_dropoff_rate']:.1%}",
            str(mod["retention_score"]),
        )

    console.print(table)
    console.print(f"\n[bold]Overall Retention Benchmark:[/bold] {report['overall_retention_avg']} / 100")
    console.print(f"[bold]Highest-Retaining Hook Formula:[/bold] [cyan]{report['best_hook_style']}[/cyan]\n")

    recs = engine.recommend_hook_improvements(persona_id)
    console.print("[bold magenta]🎯 Hook Optimization Recommendations:[/bold magenta]")
    for r in recs:
        console.print(f" • {r}")


@app.command()
def analyze_tickets(
    input_file: Optional[Path] = typer.Option(None, "--input-file", "-f", help="Path to support ticket export (.json or .csv)"),
    min_frequency: int = typer.Option(2, "--min-frequency", "-m", help="Minimum ticket count to form a deflection cluster"),
):
    """Analyzes enterprise support tickets, clusters repetitive issues, and computes deflection ROI."""
    engine = TicketDeflectionEngine()
    if input_file:
        console.print(f"[cyan]Ingesting enterprise tickets from {input_file}...[/cyan]")
        tickets = engine.ingest_from_file(input_file)
    else:
        console.print("[cyan]Loading built-in enterprise support ticket catalog (ServiceNow/Jira)...[/cyan]")
        tickets = engine.get_sample_tickets()

    clusters = engine.cluster_tickets(tickets, min_frequency=min_frequency)

    table = Table(title=f"Support Ticket Deflection Analysis ({len(tickets)} tickets -> {len(clusters)} clusters)")
    table.add_column("Cluster ID", style="cyan", no_wrap=True)
    table.add_column("Error / Pattern", style="yellow")
    table.add_column("Category", style="white")
    table.add_column("Count", style="magenta")
    table.add_column("Priority", style="bold red")
    table.add_column("Proj. Monthly Savings", style="bold green")
    table.add_column("Hours Saved", style="green")

    total_savings = 0.0
    total_hours = 0.0
    for c in clusters:
        total_savings += c.projected_monthly_savings_usd
        total_hours += c.projected_hours_saved_monthly
        table.add_row(
            c.cluster_id,
            c.primary_error_code or "N/A",
            c.category,
            str(c.ticket_count),
            c.deflection_priority,
            f"${c.projected_monthly_savings_usd:,.2f}",
            f"{c.projected_hours_saved_monthly:.1f} hrs",
        )

    console.print(table)
    console.print(f"\n[bold green]💰 Total Projected Monthly Deflection Savings:[/bold green] ${total_savings:,.2f}")
    console.print(f"[bold green]⏱️ Total Projected Support Time Saved:[/bold green] {total_hours:.1f} hours / month\n")
    console.print("[dim]Run 'python main.py deflect-ticket --cluster-id <cluster_id>' to generate a 60s microlearning solution.[/dim]")


@app.command()
def deflect_ticket(
    cluster_id: str = typer.Option("cluster_f5201", "--cluster-id", "-c", help="Cluster ID to deflect"),
    input_file: Optional[Path] = typer.Option(None, "--input-file", "-f", help="Path to support ticket export (.json or .csv)"),
    export_scorm: bool = typer.Option(True, "--export-scorm/--no-export-scorm", help="Package for Enterprise LMS (SCORM 1.2)"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Run in dry-run mode without external API charges"),
):
    """Autonomously synthesizes a 60-second microlearning tutorial and KB article to deflect a ticket cluster."""
    engine = TicketDeflectionEngine()
    if input_file:
        tickets = engine.ingest_from_file(input_file)
    else:
        tickets = engine.get_sample_tickets()

    clusters = engine.cluster_tickets(tickets, min_frequency=1)
    target_cluster = next((c for c in clusters if c.cluster_id.lower() == cluster_id.lower()), None)
    if not target_cluster:
        console.print(f"[bold red]Cluster not found:[/bold red] {cluster_id}")
        console.print(f"Available clusters: {', '.join(c.cluster_id for c in clusters)}")
        raise typer.Exit(code=1)

    console.print(f"[bold blue]🚀 Deflecting Support Ticket Cluster:[/bold blue] {target_cluster.title}")
    console.print(f"[cyan]Projected Monthly Savings: ${target_cluster.projected_monthly_savings_usd:,.2f} ({target_cluster.projected_hours_saved_monthly} hrs)[/cyan]\n")

    res = engine.generate_deflection_tutorial(
        cluster=target_cluster,
        dry_run=dry_run,
        export_scorm=export_scorm,
    )

    console.print("[bold green]✔ Ticket Deflection Package Created Successfully![/bold green]")
    console.print(f" • [cyan]Job ID:[/cyan] {res['job_id']}")
    console.print(f" • [green]Video Tutorial:[/green] {res['video_path']}")
    console.print(f" • [green]Subtitles:[/green] {res['subtitles_path']}")
    console.print(f" • [magenta]Knowledge Base Article:[/magenta] {res['kb_article_path']}")
    if res.get("scorm_package_path"):
        console.print(f" • [yellow]LMS SCORM Package:[/yellow] {res['scorm_package_path']}")
    console.print("\n[dim]IT Helpdesk Webhook notification ready for Teams/Slack.[/dim]")


@app.command()
def dashboard(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Bind address"),
    port: int = typer.Option(8000, "--port", "-p", help="Port number"),
    reload: bool = typer.Option(False, "--reload", help="Enable live auto-reload"),
):
    """Launches the Enterprise AI-SME Review & Approval Web Dashboard."""
    import uvicorn
    console.print(f"[bold blue]🚀 Starting SME Review Dashboard on http://{host}:{port}[/bold blue]")
    console.print("[cyan]Opening quality gate portal for human-in-the-loop approvals...[/cyan]")
    uvicorn.run("src.dashboard.app:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()



