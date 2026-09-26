"""Enterprise SCORM 1.2 & 2004 LMS Micro-Module Packager."""

import html
import logging
import shutil
import zipfile
from pathlib import Path
from typing import Optional

from src.core.models import VideoRenderJob

logger = logging.getLogger(__name__)


class ScormPackager:
    """Packages microlearning videos into compliant SCORM packages for Enterprise LMS/LXP."""

    @staticmethod
    def generate_manifest_xml(job: VideoRenderJob) -> str:
        """Generates standard ADL SCORM 1.2 imsmanifest.xml with multi-language subtitle tracks."""
        topic_escaped = html.escape(job.script.topic)
        job_id = job.job_id

        extra_vtt_files = ""
        for lang_code in sorted(job.additional_vtt_tracks.keys()):
            extra_vtt_files += f'      <file href="captions_{lang_code}.vtt"/>\n'

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="MANIFEST_{job_id}" version="1.0"
          xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2"
          xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://www.imsproject.org/xsd/imscp_rootv1p1p2 imscp_rootv1p1p2.xsd
                              http://www.adlnet.org/xsd/adlcp_rootv1p2 adlcp_rootv1p2.xsd">
  <metadata>
    <schema>ADL SCORM</schema>
    <schemaversion>1.2</schemaversion>
  </metadata>
  <organizations default="ORG_{job_id}">
    <organization identifier="ORG_{job_id}">
      <title>{topic_escaped}</title>
      <item identifier="ITEM_{job_id}" identifierref="RES_{job_id}">
        <title>{topic_escaped}</title>
        <adlcp:masteryscore>80</adlcp:masteryscore>
      </item>
    </organization>
  </organizations>
  <resources>
    <resource identifier="RES_{job_id}" type="webcontent" adlcp:scormtype="sco" href="index.html">
      <file href="index.html"/>
      <file href="captions.vtt"/>
{extra_vtt_files}      <file href="video.mp4"/>
      <file href="screen_overlay.png"/>
    </resource>
  </resources>
</manifest>
"""


    @staticmethod
    def generate_player_html(job: VideoRenderJob) -> str:
        """Generates accessible, mobile-responsive HTML5 enterprise video player with SCORM bridge."""
        topic = html.escape(job.script.topic)
        persona_id = html.escape(job.script.persona_id)

        # Build key takeaway list
        takeaways_html = ""
        for i, sec in enumerate(job.script.sections, 1):
            takeaways_html += (
                f"<li><strong>{sec.section_type.value.replace('_', ' ').title()}:</strong> "
                f"{html.escape(sec.voiceover_text[:140])}...</li>"
            )

        # Multi-language subtitle tracks
        lang_labels = {
            "de": "Deutsch",
            "es": "Español",
            "fr": "Français",
            "ja": "日本語",
        }
        tracks_html = '        <track kind="subtitles" src="captions.vtt" srclang="en" label="English" default>\n'
        for lang_code in sorted(job.additional_vtt_tracks.keys()):
            label = lang_labels.get(lang_code, lang_code.upper())
            tracks_html += f'        <track kind="subtitles" src="captions_{lang_code}.vtt" srclang="{lang_code}" label="{label}">\n'

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{topic} - Enterprise Microlearning</title>
  <style>
    :root {{
      --bg: #0d1117;
      --card: #161b22;
      --border: #30363d;
      --sap-blue: #0070F2;
      --gold: #F0AB00;
      --text: #c9d1d9;
      --text-bright: #ffffff;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      display: flex;
      justify-content: center;
      padding: 24px;
      min-height: 100vh;
    }}
    .container {{
      max-width: 820px;
      width: 100%;
    }}
    .header {{
      border-bottom: 2px solid var(--sap-blue);
      padding-bottom: 16px;
      margin-bottom: 20px;
    }}
    .badge {{
      display: inline-block;
      background: var(--sap-blue);
      color: #fff;
      font-size: 11px;
      font-weight: 700;
      padding: 4px 10px;
      border-radius: 4px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 8px;
    }}
    h1 {{
      font-size: 24px;
      color: var(--text-bright);
      margin-bottom: 6px;
    }}
    .presenter {{
      font-size: 13px;
      color: var(--gold);
    }}
    .video-wrapper {{
      position: relative;
      background: #000;
      border-radius: 12px;
      overflow: hidden;
      border: 1px solid var(--border);
      box-shadow: 0 10px 30px rgba(0,0,0,0.5);
      margin-bottom: 24px;
    }}
    video {{
      width: 100%;
      height: auto;
      max-height: 600px;
      display: block;
      outline: none;
    }}
    .card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 20px;
      margin-bottom: 20px;
    }}
    .card h2 {{
      font-size: 16px;
      color: var(--text-bright);
      margin-bottom: 12px;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    ul {{
      list-style-type: none;
      display: flex;
      flex-direction: column;
      gap: 10px;
      font-size: 14px;
      line-height: 1.5;
    }}
    li strong {{ color: var(--gold); }}
    .status-bar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 12px;
      color: #8b949e;
      padding: 8px 12px;
      background: #090d13;
      border-radius: 6px;
    }}
    .completed-tag {{
      display: none;
      color: #3fb950;
      font-weight: bold;
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="badge">SAP Enterprise Microlearning</div>
      <h1>{topic}</h1>
      <div class="presenter">AI-SME Presenter: {persona_id}</div>
    </div>

    <div class="video-wrapper">
      <video id="player" controls playsinline poster="screen_overlay.png">
        <source src="video.mp4" type="video/mp4">
{tracks_html}        Your browser does not support HTML5 video.
      </video>
    </div>


    <div class="card">
      <h2>📌 Lesson Blueprint & Action Items</h2>
      <ul>{takeaways_html}</ul>
    </div>

    <div class="status-bar">
      <span>LMS Status: <span id="lms-state">Connecting...</span></span>
      <span class="completed-tag" id="completed-tag">✔ Lesson Completed</span>
    </div>
  </div>

  <script>
    // Lightweight SCORM 1.2 Bridge
    let scormAPI = null;

    function findAPI(win) {{
      let attempts = 0;
      while (win && !win.API && win.parent && win.parent !== win && attempts < 10) {{
        attempts++;
        win = win.parent;
      }}
      return win ? win.API : null;
    }}

    try {{
      scormAPI = findAPI(window) || (window.opener ? findAPI(window.opener) : null);
      if (scormAPI) {{
        scormAPI.LMSInitialize("");
        scormAPI.LMSSetValue("cmi.core.lesson_status", "incomplete");
        scormAPI.LMSCommit("");
        document.getElementById("lms-state").textContent = "Connected (In Progress)";
      }} else {{
        document.getElementById("lms-state").textContent = "Standalone / Preview Mode";
      }}
    }} catch (e) {{
      document.getElementById("lms-state").textContent = "Standalone Mode";
    }}

    const video = document.getElementById("player");
    let markedComplete = false;

    function recordCompletion() {{
      if (markedComplete) return;
      markedComplete = true;
      document.getElementById("completed-tag").style.display = "inline";
      document.getElementById("lms-state").textContent = "Completed";

      if (scormAPI) {{
        try {{
          scormAPI.LMSSetValue("cmi.core.lesson_status", "completed");
          scormAPI.LMSSetValue("cmi.core.score.raw", "100");
          scormAPI.LMSCommit("");
        }} catch(e) {{}}
      }}
    }}

    // Complete on video finished or 80% viewed
    video.addEventListener("ended", recordCompletion);
    video.addEventListener("timeupdate", () => {{
      if (video.duration && (video.currentTime / video.duration) >= 0.85) {{
        recordCompletion();
      }}
    }});

    window.addEventListener("beforeunload", () => {{
      if (scormAPI) {{
        try {{
          scormAPI.LMSFinish("");
        }} catch(e) {{}}
      }}
    }});
  </script>
</body>
</html>
"""

    def package(self, job: VideoRenderJob, target_dir: Optional[Path] = None) -> Path:
        """
        Creates a compliant SCORM 1.2 zip archive for the given VideoRenderJob.
        """
        job_dir = Path(job.output_file_path).parent if job.output_file_path else (Path("output") / job.job_id)
        target_dir = Path(target_dir) if target_dir else job_dir

        staging_dir = target_dir / f"scorm_staging_{job.job_id}"
        staging_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 1. Write imsmanifest.xml
            manifest_content = self.generate_manifest_xml(job)
            (staging_dir / "imsmanifest.xml").write_text(manifest_content, encoding="utf-8")

            # 2. Write HTML5 SCORM player
            player_html = self.generate_player_html(job)
            (staging_dir / "index.html").write_text(player_html, encoding="utf-8")

            # 3. Copy captions.vtt
            vtt_src = Path(job.vtt_subtitles_file_path) if job.vtt_subtitles_file_path else (job_dir / f"{job.job_id}_captions.vtt")
            if vtt_src.exists():
                shutil.copyfile(vtt_src, staging_dir / "captions.vtt")
            else:
                (staging_dir / "captions.vtt").write_text("WEBVTT\n\n1\n00:00:00.000 --> 00:00:05.000\nLesson start\n", encoding="utf-8")

            # 3b. Copy additional localized captions_<lang>.vtt
            for lang_code, vtt_path_str in job.additional_vtt_tracks.items():
                extra_vtt_src = Path(vtt_path_str)
                dest_vtt = staging_dir / f"captions_{lang_code}.vtt"
                if extra_vtt_src.exists():
                    shutil.copyfile(extra_vtt_src, dest_vtt)
                else:
                    dest_vtt.write_text(f"WEBVTT - Language: {lang_code}\n\n1\n00:00:00.000 --> 00:00:05.000\nLesson start\n", encoding="utf-8")


            # 4. Copy or link video.mp4
            video_src = Path(job.output_file_path) if job.output_file_path else (job_dir / f"{job.job_id}_final.mp4")
            if video_src.exists():
                video_size = video_src.stat().st_size
                if video_size > 500 * 1024 * 1024:
                    logger.warning(
                        "Video file %s (%d MB) exceeds 500MB SCORM limit. Consider compressing before LMS packaging.",
                        video_src,
                        video_size // (1024 * 1024),
                    )
                shutil.copyfile(video_src, staging_dir / "video.mp4")
            else:
                (staging_dir / "video.mp4").touch()

            # 5. Copy screen_overlay.png if available
            overlay_src = job_dir / "screen_overlay.png"
            if overlay_src.exists():
                shutil.copyfile(overlay_src, staging_dir / "screen_overlay.png")
            else:
                (staging_dir / "screen_overlay.png").touch()

            # 6. Create SCORM zip package
            zip_output_path = target_dir / f"{job.job_id}_scorm_package.zip"
            with zipfile.ZipFile(zip_output_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for file_path in staging_dir.iterdir():
                    zipf.write(file_path, arcname=file_path.name)

            return zip_output_path
        finally:
            shutil.rmtree(staging_dir, ignore_errors=True)
