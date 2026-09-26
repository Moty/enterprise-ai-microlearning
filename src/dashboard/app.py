"""FastAPI-based Enterprise SME Review & Approval Dashboard."""

import html
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

from src.core.config import settings
from src.core.models import VideoRenderJob
from src.core.repositories import get_job_repository
from src.pipeline.analytics import AnalyticsEngine
from src.pipeline.ideation import ScriptGenerator
from src.pipeline.localization import LocalizationEngine
from src.publishers.linkedin_publisher import LinkedInPublisher
from src.publishers.scorm_packager import ScormPackager
from src.publishers.webhook_publisher import WebhookPublisher
from src.pipeline.ticket_deflection import TicketDeflectionEngine

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Enterprise AI-SME Review & Approval Portal",
    description="Human-in-the-loop review portal for AI-generated enterprise microlearning modules.",
    version="1.0.0",
)


class ApproveRequest(BaseModel):
    publish_linkedin: bool = False
    first_comment_link: Optional[str] = None
    notify_channel: Optional[str] = None  # 'teams' or 'slack'
    dry_run: bool = True


class LocalizeRequest(BaseModel):
    languages: List[str] = ["de", "ja", "es", "fr"]
    export_scorm: bool = True
    dry_run: bool = True


@app.get("/api/jobs", response_model=List[Dict[str, Any]])
def list_jobs(status_filter: Optional[str] = Query(None, alias="status"), limit: int = 50):
    """Retrieves all video render jobs from the configured repository."""
    repo = get_job_repository()
    jobs = repo.list_jobs(status=status_filter, limit=limit)
    return [j.model_dump(mode="json") for j in jobs]


@app.get("/api/jobs/{job_id}", response_model=Dict[str, Any])
def get_job(job_id: str):
    """Retrieves a specific video render job."""
    repo = get_job_repository()
    job = repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return job.model_dump(mode="json")


@app.get("/api/jobs/{job_id}/video")
def get_job_video(job_id: str):
    """Streams or serves the composed MP4 video file for a job."""
    repo = get_job_repository()
    job = repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    candidates = [
        Path(job.output_file_path or ""),
        settings.OUTPUT_DIR / job_id / f"{job_id}_final.mp4",
        settings.OUTPUT_DIR / job_id / "test_render.mp4",
        settings.OUTPUT_DIR / job_id / "test_subtitled.mp4",
    ]

    for p in candidates:
        if p.exists() and p.is_file() and p.stat().st_size > 0:
            return FileResponse(path=p, media_type="video/mp4", filename=f"{job_id}.mp4")

    raise HTTPException(status_code=404, detail="Video file not found or render has not been completed.")


@app.get("/api/jobs/{job_id}/overlay")
def get_job_overlay(job_id: str):
    """Serves the generated screen overlay PNG for a job."""
    path = settings.OUTPUT_DIR / job_id / "screen_overlay.png"
    if path.exists() and path.is_file():
        return FileResponse(path=path, media_type="image/png")
    raise HTTPException(status_code=404, detail="Overlay image not found.")


@app.get("/api/jobs/{job_id}/scorm")
def download_scorm_package(job_id: str):
    """Downloads the SCORM 1.2 zip archive for a job."""
    path = settings.OUTPUT_DIR / job_id / f"{job_id}_scorm_package.zip"
    if path.exists() and path.is_file():
        return FileResponse(
            path=path,
            media_type="application/zip",
            filename=f"{job_id}_scorm_package.zip",
        )
    raise HTTPException(status_code=404, detail="SCORM package not found. Run packaging first.")


@app.post("/api/jobs/{job_id}/approve")
def approve_job(job_id: str, req: ApproveRequest):
    """Approves a microlearning module and dispatches it to LinkedIn or internal LMS."""
    repo = get_job_repository()
    job = repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    # 1. Update job status to approved
    job.status = "completed"
    repo.save_job(job)

    results: Dict[str, Any] = {"status": "approved", "job_id": job_id}

    # 2. Optional LinkedIn publishing
    if req.publish_linkedin:
        publisher = LinkedInPublisher()
        li_res = publisher.publish_live(
            job=job,
            first_comment_link=req.first_comment_link,
            dry_run=req.dry_run,
        )
        results["linkedin"] = li_res

    # 3. Optional channel notification
    if req.notify_channel:
        notifier = WebhookPublisher()
        ch_res = notifier.send_notification(
            job=job,
            channel=req.notify_channel,
            dry_run=req.dry_run,
        )
        results["notification"] = ch_res

    return results


@app.post("/api/jobs/{job_id}/localize")
def localize_job(job_id: str, req: LocalizeRequest):
    """Translates a job's script and creates localized WebVTT and multilingual SCORM package."""
    repo = get_job_repository()
    job = repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    engine = LocalizationEngine()
    updated_job = engine.localize_job(job=job, target_languages=req.languages, dry_run=req.dry_run)

    if req.export_scorm:
        packager = ScormPackager()
        scorm_zip = packager.package(updated_job)
        updated_job.metadata["scorm_package"] = str(scorm_zip)

    repo.save_job(updated_job)
    return {
        "status": "localized",
        "job_id": job_id,
        "languages": req.languages,
        "tracks": updated_job.additional_vtt_tracks,
    }


@app.get("/api/analytics")
def get_analytics_report():
    """Retrieves executive retention telemetry report across all modules."""
    analytics = AnalyticsEngine()
    return analytics.get_summary_report()


@app.get("/api/tickets/clusters")
def list_ticket_clusters(min_frequency: int = 2):
    """Retrieves grouped enterprise support ticket clusters with deflection ROI metrics."""
    engine = TicketDeflectionEngine()
    tickets = engine.get_sample_tickets()
    clusters = engine.cluster_tickets(tickets, min_frequency=min_frequency)
    return [c.model_dump(mode="json") for c in clusters]


@app.post("/api/tickets/deflect/{cluster_id}")
def deflect_ticket_cluster(cluster_id: str, dry_run: bool = True, export_scorm: bool = True):
    """Triggers autonomous microlearning video, KB article, and deflection package generation."""
    engine = TicketDeflectionEngine()
    tickets = engine.get_sample_tickets()
    clusters = engine.cluster_tickets(tickets, min_frequency=1)
    target = next((c for c in clusters if c.cluster_id.lower() == cluster_id.lower()), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"Ticket cluster '{cluster_id}' not found.")

    result = engine.generate_deflection_tutorial(
        cluster=target,
        dry_run=dry_run,
        export_scorm=export_scorm,
    )
    return result


@app.get("/", response_class=HTMLResponse)
def dashboard_ui():
    """Serves the full single-page SME Review and Approval UI."""
    return HTMLResponse(content=DASHBOARD_HTML)


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Enterprise AI-SME Review & Approval Portal</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link href="https://fonts.googleapis.com/css2?family=72:wght@400;600;700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --sap-blue: #0070F2;
      --sap-dark-blue: #0040B0;
      --sap-gold: #E76500;
      --sap-green: #2B7C2B;
      --sap-red: #BB0000;
      --bg-dark: #12161F;
      --card-bg: #1B222D;
      --card-border: #2C3545;
      --text-main: #F5F7FA;
      --text-muted: #9BA7B9;
      --accent: #00B4D8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background-color: var(--bg-dark);
      color: var(--text-main);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    header {
      background: #18202C;
      border-bottom: 1px solid var(--card-border);
      padding: 16px 32px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .brand-logo {
      background: linear-gradient(135deg, var(--sap-blue), var(--accent));
      color: #fff;
      font-weight: 700;
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 14px;
      letter-spacing: 0.5px;
    }
    .brand-title {
      font-size: 18px;
      font-weight: 600;
      color: #fff;
    }
    .brand-sub {
      font-size: 12px;
      color: var(--text-muted);
    }
    .container {
      max-width: 1400px;
      margin: 0 auto;
      padding: 32px 24px;
      width: 100%;
      flex: 1;
    }
    .metrics-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 20px;
      margin-bottom: 32px;
    }
    .metric-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 10px;
      padding: 20px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .metric-title {
      font-size: 13px;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .metric-value {
      font-size: 28px;
      font-weight: 700;
      color: #fff;
    }
    .metric-subtitle {
      font-size: 12px;
      color: var(--accent);
    }
    .toolbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
      gap: 16px;
      flex-wrap: wrap;
    }
    .search-input {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      color: #fff;
      padding: 10px 16px;
      border-radius: 8px;
      font-size: 14px;
      min-width: 320px;
    }
    .filter-tabs {
      display: flex;
      gap: 8px;
    }
    .tab-btn {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      color: var(--text-muted);
      padding: 8px 16px;
      border-radius: 8px;
      cursor: pointer;
      font-size: 13px;
      font-weight: 500;
      transition: all 0.2s;
    }
    .tab-btn.active, .tab-btn:hover {
      background: var(--sap-blue);
      border-color: var(--sap-blue);
      color: #fff;
    }
    .jobs-table-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      overflow: hidden;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 14px;
    }
    th {
      background: #151A24;
      padding: 14px 20px;
      color: var(--text-muted);
      font-weight: 600;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      border-bottom: 1px solid var(--card-border);
    }
    td {
      padding: 16px 20px;
      border-bottom: 1px solid var(--card-border);
      vertical-align: middle;
    }
    tr:hover td {
      background: rgba(255, 255, 255, 0.02);
    }
    .badge {
      display: inline-block;
      padding: 4px 10px;
      border-radius: 12px;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
    }
    .badge-completed { background: rgba(43, 124, 43, 0.2); color: #4ade80; border: 1px solid rgba(43, 124, 43, 0.4); }
    .badge-composited { background: rgba(0, 112, 242, 0.2); color: #38bdf8; border: 1px solid rgba(0, 112, 242, 0.4); }
    .badge-pending { background: rgba(231, 101, 0, 0.2); color: #fb923c; border: 1px solid rgba(231, 101, 0, 0.4); }
    .badge-failed { background: rgba(187, 0, 0, 0.2); color: #f87171; border: 1px solid rgba(187, 0, 0, 0.4); }
    .persona-tag {
      font-weight: 600;
      color: #E2E8F0;
    }
    .btn {
      padding: 8px 14px;
      border-radius: 6px;
      border: none;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s;
    }
    .btn-primary { background: var(--sap-blue); color: #fff; }
    .btn-primary:hover { background: var(--sap-dark-blue); }
    .btn-outline { background: transparent; border: 1px solid var(--card-border); color: var(--text-main); }
    .btn-outline:hover { background: rgba(255,255,255,0.05); border-color: var(--accent); }
    .btn-success { background: var(--sap-green); color: #fff; }
    .modal-backdrop {
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.75);
      backdrop-filter: blur(4px);
      z-index: 1000;
      align-items: center;
      justify-content: center;
      padding: 20px;
    }
    .modal {
      background: #18202C;
      border: 1px solid var(--card-border);
      border-radius: 14px;
      width: 100%;
      max-width: 900px;
      max-height: 90vh;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      box-shadow: 0 20px 40px rgba(0,0,0,0.5);
    }
    .modal-header {
      padding: 20px 24px;
      border-bottom: 1px solid var(--card-border);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .modal-body {
      padding: 24px;
      display: flex;
      flex-direction: column;
      gap: 20px;
    }
    .modal-footer {
      padding: 16px 24px;
      border-top: 1px solid var(--card-border);
      display: flex;
      justify-content: flex-end;
      gap: 12px;
      background: #151A24;
    }
    .script-section-card {
      background: #1F2837;
      border: 1px solid #2D3A4E;
      border-radius: 8px;
      padding: 14px 18px;
    }
    .section-type {
      font-size: 11px;
      color: var(--accent);
      text-transform: uppercase;
      font-weight: 700;
      margin-bottom: 6px;
    }
    .section-text {
      font-size: 14px;
      line-height: 1.5;
      color: #E2E8F0;
    }
    .section-cue {
      font-size: 12px;
      color: var(--text-muted);
      margin-top: 6px;
      font-style: italic;
    }
    video {
      width: 100%;
      max-height: 400px;
      border-radius: 8px;
      background: #000;
      border: 1px solid var(--card-border);
    }
  </style>
</head>
<body>

<header>
  <div class="brand">
    <div class="brand-logo">SAP AI-SME</div>
    <div>
      <div class="brand-title">Enterprise Microlearning SME Review Portal</div>
      <div class="brand-sub">Human-in-the-Loop Quality Gate & Multi-Channel Distribution Hub</div>
    </div>
  </div>
  <div>
    <button class="btn btn-outline" onclick="loadJobs()">⟳ Refresh Queue</button>
  </div>
</header>

<div class="container">
  <div class="metrics-grid">
    <div class="metric-card">
      <div class="metric-title">Modules in Queue</div>
      <div class="metric-value" id="stat-total">--</div>
      <div class="metric-subtitle">Across 3 Persona Archetypes</div>
    </div>
    <div class="metric-card">
      <div class="metric-title">Published / Approved</div>
      <div class="metric-value" id="stat-approved" style="color: #4ade80;">--</div>
      <div class="metric-subtitle">Ready for LMS & LinkedIn</div>
    </div>
    <div class="metric-card">
      <div class="metric-title">Avg Retention Score</div>
      <div class="metric-value" id="stat-retention" style="color: #38bdf8;">--</div>
      <div class="metric-subtitle">Benchmark / 100 Index</div>
    </div>
    <div class="metric-card">
      <div class="metric-title">Active AI-SME Personas</div>
      <div class="metric-value">3</div>
      <div class="metric-subtitle">Architect, Dev, Functional</div>
    </div>
  </div>

  <div class="toolbar">
    <input type="text" id="search-box" class="search-input" placeholder="Search by topic, error code (M7021), or ID..." oninput="filterJobs()">
    <div class="filter-tabs">
      <button class="tab-btn active" onclick="setFilter('all', this)">All</button>
      <button class="tab-btn" onclick="setFilter('composited', this)">Composited</button>
      <button class="tab-btn" onclick="setFilter('completed', this)">Approved</button>
      <button class="tab-btn" onclick="setFilter('failed', this)">Failed</button>
    </div>
  </div>

  <div class="jobs-table-card">
    <table>
      <thead>
        <tr>
          <th>Topic & Error Code</th>
          <th>AI-SME Persona</th>
          <th>Layout</th>
          <th>Status</th>
          <th>Created</th>
          <th style="text-align: right;">Review Action</th>
        </tr>
      </thead>
      <tbody id="jobs-table-body">
        <tr><td colspan="6" style="text-align: center; color: var(--text-muted);">Loading enterprise microlearning modules...</td></tr>
      </tbody>
    </table>
  </div>
</div>

<!-- Modal View -->
<div class="modal-backdrop" id="review-modal">
  <div class="modal">
    <div class="modal-header">
      <div style="font-weight: 700; font-size: 18px;" id="modal-title">Review Module</div>
      <button class="btn btn-outline" style="padding: 4px 8px;" onclick="closeModal()">✕</button>
    </div>
    <div class="modal-body" id="modal-content">
      <!-- Dynamic Content -->
    </div>
    <div class="modal-footer" id="modal-actions">
      <!-- Action buttons -->
    </div>
  </div>
</div>

<script>
let allJobs = [];
let currentFilter = 'all';

async function loadJobs() {
  try {
    const res = await fetch('/api/jobs');
    allJobs = await res.json();
    renderJobs();
    updateMetrics();
  } catch (err) {
    console.error('Failed to load jobs', err);
  }
}

async function updateMetrics() {
  document.getElementById('stat-total').innerText = allJobs.length;
  const approved = allJobs.filter(j => j.status === 'completed').length;
  document.getElementById('stat-approved').innerText = approved;

  try {
    const aRes = await fetch('/api/analytics');
    const analytics = await aRes.json();
    document.getElementById('stat-retention').innerText = (analytics.overall_retention_avg || '84.5') + ' %';
  } catch (e) {
    document.getElementById('stat-retention').innerText = '84.5 %';
  }
}

function setFilter(filt, el) {
  currentFilter = filt;
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  el.classList.add('active');
  renderJobs();
}

function filterJobs() {
  renderJobs();
}

function renderJobs() {
  const tbody = document.getElementById('jobs-table-body');
  const q = document.getElementById('search-box').value.toLowerCase();

  const filtered = allJobs.filter(j => {
    if (currentFilter !== 'all' && j.status !== currentFilter) return false;
    if (!q) return true;
    const t = (j.script?.topic || '').toLowerCase();
    const jid = (j.job_id || '').toLowerCase();
    const pid = (j.script?.persona_id || '').toLowerCase();
    return t.includes(q) || jid.includes(q) || pid.includes(q);
  });

  if (filtered.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 32px;">No microlearning modules matching filter.</td></tr>';
    return;
  }

  tbody.innerHTML = filtered.map(j => `
    <tr>
      <td>
        <div style="font-weight: 600; color: #fff;">${escapeHtml(j.script?.topic || 'Untitled')}</div>
        <div style="font-size: 12px; color: var(--text-muted);">${j.job_id}</div>
      </td>
      <td>
        <span class="persona-tag">${escapeHtml(j.script?.persona_id || 'N/A')}</span>
      </td>
      <td>
        <span style="font-size: 13px; color: var(--text-muted);">${j.layout || 'linkedin_portrait'}</span>
      </td>
      <td>
        <span class="badge badge-${j.status}">${j.status}</span>
      </td>
      <td style="color: var(--text-muted); font-size: 13px;">
        ${j.created_at ? new Date(j.created_at).toLocaleDateString() : '--'}
      </td>
      <td style="text-align: right;">
        <button class="btn btn-primary" onclick="openReviewModal('${j.job_id}')">Review & Approve</button>
      </td>
    </tr>
  `).join('');
}

async function openReviewModal(jobId) {
  const job = allJobs.find(j => j.job_id === jobId);
  if (!job) return;

  document.getElementById('modal-title').innerText = 'SME Quality Review: ' + (job.script?.topic || jobId);
  const body = document.getElementById('modal-content');
  const actions = document.getElementById('modal-actions');

  const sectionsHtml = (job.script?.sections || []).map(s => `
    <div class="script-section-card">
      <div class="section-type">${s.section_type} • ~${s.estimated_duration_sec}s</div>
      <div class="section-text">${escapeHtml(s.voiceover_text)}</div>
      <div class="section-cue">🎬 Visual: ${escapeHtml(s.visual_cue)}</div>
    </div>
  `).join('');

  const hasVideo = job.output_file_path && job.status !== 'pending';

  body.innerHTML = `
    <div>
      <div style="font-size: 12px; color: var(--accent); text-transform: uppercase; font-weight: 700; margin-bottom: 6px;">Subject Matter Expert Persona</div>
      <div style="font-size: 16px; font-weight: 600; color: #fff;">${job.script?.persona_id}</div>
    </div>

    ${hasVideo ? `
      <div>
        <div style="font-size: 12px; color: var(--text-muted); margin-bottom: 8px; text-transform: uppercase; font-weight: 600;">Composed Video Preview</div>
        <video controls>
          <source src="/api/jobs/${job.job_id}/video" type="video/mp4">
          Your browser does not support HTML5 video preview.
        </video>
      </div>
    ` : `
      <div style="background: rgba(255,255,255,0.02); border: 1px dashed var(--card-border); padding: 24px; text-align: center; border-radius: 8px; color: var(--text-muted);">
        Video preview ready for composition on local/cloud runner.
      </div>
    `}

    <div>
      <div style="font-size: 12px; color: var(--text-muted); margin-bottom: 8px; text-transform: uppercase; font-weight: 600;">60-Second Hook & Solution Script</div>
      <div style="display: flex; flex-direction: column; gap: 10px;">
        ${sectionsHtml}
      </div>
    </div>

    <div>
      <div style="font-size: 12px; color: var(--text-muted); margin-bottom: 8px; text-transform: uppercase; font-weight: 600;">LinkedIn Thought Leadership Copy</div>
      <div style="background: #11151D; padding: 14px; border-radius: 6px; font-size: 13px; line-height: 1.5; color: #CBD5E1; white-space: pre-wrap;">${escapeHtml(job.script?.post_caption || '')}</div>
    </div>
  `;

  actions.innerHTML = `
    <button class="btn btn-outline" onclick="downloadScorm('${job.job_id}')">📦 Download SCORM Zip</button>
    <button class="btn btn-outline" onclick="triggerLocalize('${job.job_id}')">🌍 Localize (DE/JA/ES)</button>
    <button class="btn btn-success" onclick="approveAndPublish('${job.job_id}')">✔ Approve & Publish</button>
  `;

  document.getElementById('review-modal').style.display = 'flex';
}

function closeModal() {
  document.getElementById('review-modal').style.display = 'none';
}

async function approveAndPublish(jobId) {
  if (!confirm('Approve this microlearning module and prepare for distribution?')) return;
  try {
    const res = await fetch(`/api/jobs/${jobId}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ publish_linkedin: true, dry_run: true })
    });
    const data = await res.json();
    alert('Module approved successfully! Status: ' + data.status);
    closeModal();
    loadJobs();
  } catch (err) {
    alert('Approval error: ' + err);
  }
}

async function triggerLocalize(jobId) {
  try {
    const res = await fetch(`/api/jobs/${jobId}/localize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ languages: ['de', 'ja', 'es'], export_scorm: true, dry_run: true })
    });
    const data = await res.json();
    alert('Localization completed for: ' + data.languages.join(', '));
    loadJobs();
  } catch (err) {
    alert('Localization error: ' + err);
  }
}

function downloadScorm(jobId) {
  window.open(`/api/jobs/${jobId}/scorm`, '_blank');
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

window.onload = loadJobs;
</script>

</body>
</html>
"""
