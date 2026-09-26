"""Automated Support Ticket Deflection Engine ('Ticket-to-Tutorial').

Ingests enterprise support desk tickets (ServiceNow, Jira Service Desk, Zendesk),
clusters repetitive issues, calculates deflection ROI, and autonomously synthesizes
60-second microlearning video tutorials and KB articles.
"""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from src.core.config import settings
from src.core.models import ScriptSection, SectionType, VideoLayout, VideoRenderJob, VideoScript
from src.core.repositories import get_job_repository
from src.pipeline.asset_generator import AssetGenerator
from src.pipeline.avatar_engine import AvatarEngine
from src.pipeline.compositor import VideoCompositor
from src.pipeline.ideation import ScriptGenerator
from src.pipeline.voice_engine import VoiceEngine
from src.publishers.scorm_packager import ScormPackager
from src.publishers.webhook_publisher import WebhookPublisher

logger = logging.getLogger(__name__)


class SupportTicket(BaseModel):
    """Model representing an enterprise IT support ticket."""
    ticket_id: str
    source_system: Literal["servicenow", "jira", "zendesk", "generic"] = "servicenow"
    title: str
    description: str
    error_code: Optional[str] = None
    category: str = "SAP ERP"
    resolution_time_minutes: float = 25.0
    cost_per_ticket_usd: float = 45.0  # Industry benchmark for L1/L2 enterprise ticket
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolution_notes: Optional[str] = None


class TicketCluster(BaseModel):
    """Represents a grouped cluster of repetitive support tickets with ROI metrics."""
    cluster_id: str
    title: str
    category: str
    primary_error_code: Optional[str] = None
    ticket_count: int
    tickets: List[SupportTicket]
    recommended_persona: str = "erp_functional_consultant"
    avg_resolution_minutes: float
    cost_per_ticket_usd: float
    estimated_monthly_volume: int
    projected_monthly_savings_usd: float
    projected_hours_saved_monthly: float
    deflection_priority: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"] = "HIGH"
    root_cause_summary: str
    quick_fix_steps: List[str]


class TicketDeflectionEngine:
    """Orchestrates ticket ingestion, clustering, ROI analysis, and tutorial generation."""

    # Built-in High-Frequency Enterprise Support Ticket Catalog
    SAMPLE_ENTERPRISE_TICKETS: List[Dict[str, Any]] = [
        # Cluster 1: SAP FI/CO Posting Period Closed (F5201)
        {
            "ticket_id": "INC0089101",
            "source_system": "servicenow",
            "title": "Cannot post vendor invoice - Error F5201 Posting period 009 2026 is not open",
            "description": "Accounts payable user getting error F5201 when trying to post incoming supplier invoice via FB60.",
            "error_code": "F5201",
            "category": "SAP FI/CO",
            "resolution_time_minutes": 30.0,
            "resolution_notes": "Open posting period in transaction OB52 for account type '+' and 'K' for company code 1000.",
        },
        {
            "ticket_id": "INC0089145",
            "source_system": "servicenow",
            "title": "Posting period closed in company code 1000",
            "description": "Month end billing failed with F5201 period 009 closed in variant 1000.",
            "error_code": "F5201",
            "category": "SAP FI/CO",
            "resolution_time_minutes": 25.0,
            "resolution_notes": "T-Code OB52 update posting periods.",
        },
        {
            "ticket_id": "INC0089202",
            "source_system": "servicenow",
            "title": "Batch job cancelled due to closed posting period F5201",
            "description": "Nightly depreciation run aborted with period not open message.",
            "error_code": "F5201",
            "category": "SAP FI/CO",
            "resolution_time_minutes": 35.0,
            "resolution_notes": "Finance period opened in OB52.",
        },
        # Cluster 2: SAP MM Deficit of Stock (M7021)
        {
            "ticket_id": "INC0078120",
            "source_system": "jira",
            "title": "Deficit of SL Unrestricted-use stock 50 EA during MIGO goods issue",
            "description": "Warehouse unable to issue component to production order. Error M7021.",
            "error_code": "M7021",
            "category": "SAP MM",
            "resolution_time_minutes": 30.0,
            "resolution_notes": "Check MMBE stock. Transfer from Quality inspection using movement type 321 in MIGO.",
        },
        {
            "ticket_id": "INC0078189",
            "source_system": "jira",
            "title": "Stock deficit error M7021 on plant 1000 sloc 0001",
            "description": "Production confirmation failed due to unrestricted stock deficit.",
            "error_code": "M7021",
            "category": "SAP MM",
            "resolution_time_minutes": 20.0,
            "resolution_notes": "Verify stock in transit (MB5T) and transfer to unrestricted.",
        },
        {
            "ticket_id": "INC0078233",
            "source_system": "jira",
            "title": "MIGO goods issue blocked: M7021 deficit of stock",
            "description": "Outbound delivery post goods issue rejected with deficit message.",
            "error_code": "M7021",
            "category": "SAP MM",
            "resolution_time_minutes": 25.0,
            "resolution_notes": "Move stock from blocked or QI to unrestricted.",
        },
        # Cluster 3: SAP Gateway RFC Connection Drop (SM59)
        {
            "ticket_id": "INC0091040",
            "source_system": "servicenow",
            "title": "SM59 RFC connection to BTP subaccount failing with connection timeout",
            "description": "Cloud connector tunnel dropped, BTP apps unable to call backend on-premise RFC.",
            "error_code": "SM59",
            "category": "SAP Integration",
            "resolution_time_minutes": 45.0,
            "resolution_notes": "Check SAP Cloud Connector status in SCC dashboard and re-ping destination in SM59.",
        },
        {
            "ticket_id": "INC0091105",
            "source_system": "servicenow",
            "title": "RFC ping timeout on SM59 destination BTP_CORE",
            "description": "Integration test failing due to destination connection drop.",
            "error_code": "SM59",
            "category": "SAP Integration",
            "resolution_time_minutes": 40.0,
            "resolution_notes": "Restart cloud connector service and re-authenticate credentials.",
        },
    ]

    def get_sample_tickets(self) -> List[SupportTicket]:
        """Loads default realistic enterprise support tickets."""
        return [SupportTicket(**t) for t in self.SAMPLE_ENTERPRISE_TICKETS]

    def ingest_from_file(self, file_path: Path) -> List[SupportTicket]:
        """Ingests support tickets from a JSON or CSV file with path sanitization."""
        path = Path(file_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Ticket export file not found: {path}")

        tickets: List[SupportTicket] = []
        if path.suffix.lower() == ".json":
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        tickets.append(SupportTicket(**item))
                elif isinstance(data, dict) and "tickets" in data:
                    for item in data["tickets"]:
                        tickets.append(SupportTicket(**item))
        elif path.suffix.lower() == ".csv":
            import csv
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    tickets.append(
                        SupportTicket(
                            ticket_id=row.get("ticket_id", f"CSV_{len(tickets)+1}"),
                            source_system=row.get("source_system", "generic"),
                            title=row.get("title", "Untitled Ticket"),
                            description=row.get("description", ""),
                            error_code=row.get("error_code") or None,
                            category=row.get("category", "SAP ERP"),
                            resolution_time_minutes=float(row.get("resolution_time_minutes", 25.0)),
                            cost_per_ticket_usd=float(row.get("cost_per_ticket_usd", 45.0)),
                            resolution_notes=row.get("resolution_notes"),
                        )
                    )
        else:
            raise ValueError(f"Unsupported file format: {path.suffix}. Must be .json or .csv")

        return tickets

    @staticmethod
    def _extract_error_pattern(ticket: SupportTicket) -> str:
        """Extracts an error code or normalized keyword pattern for grouping."""
        if ticket.error_code:
            return ticket.error_code.upper().strip()

        # Heuristic regex search for SAP error codes (e.g. F5201, M7021, SM59, ME21N)
        found = re.findall(r"\b([A-Z]{1,3}\d{3,5}|SM59|MIGO|ME21N|OB52|FB60)\b", ticket.title.upper())
        if found:
            return found[0]

        # Fallback to category + first 3 words of title
        words = re.sub(r"[^\w\s]", "", ticket.title.lower()).split()[:3]
        return f"{ticket.category}_{'_'.join(words)}"

    def cluster_tickets(self, tickets: List[SupportTicket], min_frequency: int = 2) -> List[TicketCluster]:
        """
        Groups tickets by repetitive error code/signature and computes deflection ROI metrics.
        """
        groups: Dict[str, List[SupportTicket]] = {}
        for t in tickets:
            sig = self._extract_error_pattern(t)
            groups.setdefault(sig, []).append(t)

        clusters: List[TicketCluster] = []
        for sig, group_tickets in groups.items():
            if len(group_tickets) < min_frequency:
                continue

            primary_error = group_tickets[0].error_code or (sig if re.match(r"^[A-Z0-9_]{3,8}$", sig) else None)
            category = group_tickets[0].category

            # Determine Persona
            if "FI" in category or "CO" in category or "Finance" in category:
                persona = "erp_functional_consultant"
            elif "Integration" in category or "BTP" in category or "BASIS" in category:
                persona = "fiori_dev"
            elif "MM" in category or "Logistics" in category or "Supply Chain" in category:
                persona = "erp_functional_consultant"
            else:
                persona = "sap_architect"

            avg_res_min = sum(t.resolution_time_minutes for t in group_tickets) / len(group_tickets)
            cost_per_ticket = sum(t.cost_per_ticket_usd for t in group_tickets) / len(group_tickets)

            # Estimate monthly volume (assuming sample represents ~1 week of tickets)
            est_monthly_volume = len(group_tickets) * 12  # conservative projection
            projected_monthly_savings = est_monthly_volume * cost_per_ticket * 0.70  # 70% deflection rate
            projected_hours_saved = (est_monthly_volume * avg_res_min * 0.70) / 60.0

            priority: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"] = "MEDIUM"
            if projected_monthly_savings > 3000 or len(group_tickets) >= 3:
                priority = "CRITICAL"
            elif projected_monthly_savings > 1500:
                priority = "HIGH"

            # Derive root cause & quick fixes
            root_cause = f"Repeated user exceptions triggered by {sig} in {category}."
            quick_fixes = [
                f"Verify transaction settings and authorization for error {sig}.",
                "Check master data or posting period open statuses.",
                "Execute corrective movement or configuration update before retrying.",
            ]
            if primary_error == "F5201":
                root_cause = "Posting period is closed for the target month/year in transaction OB52."
                quick_fixes = [
                    "Open transaction OB52 in SAP GUI.",
                    "Locate account type '+' and target company code variant.",
                    "Advance the 'To Period' to the active fiscal month and save.",
                ]
            elif primary_error == "M7021":
                root_cause = "Deficit of unrestricted-use stock. Units are typically locked in Quality Inspection or Blocked Stock."
                quick_fixes = [
                    "Open transaction MMBE to review stock breakdown.",
                    "Check for stock locked under 'Quality Inspection' or 'Blocked'.",
                    "Transfer stock to Unrestricted via MIGO Movement Type 321 or 343.",
                ]
            elif primary_error == "SM59":
                root_cause = "RFC connection timeout between on-premise SAP backend and cloud destinations."
                quick_fixes = [
                    "Log into SAP Cloud Connector administration console.",
                    "Verify the tunnel status to the target BTP subaccount.",
                    "Perform a connection test in transaction SM59 and check response code.",
                ]

            cluster_id = f"cluster_{sig.lower()}"
            title = f"Automated Self-Service Fix: SAP Error {sig} ({category})"

            clusters.append(
                TicketCluster(
                    cluster_id=cluster_id,
                    title=title,
                    category=category,
                    primary_error_code=primary_error,
                    ticket_count=len(group_tickets),
                    tickets=group_tickets,
                    recommended_persona=persona,
                    avg_resolution_minutes=round(avg_res_min, 1),
                    cost_per_ticket_usd=round(cost_per_ticket, 2),
                    estimated_monthly_volume=est_monthly_volume,
                    projected_monthly_savings_usd=round(projected_monthly_savings, 2),
                    projected_hours_saved_monthly=round(projected_hours_saved, 1),
                    deflection_priority=priority,
                    root_cause_summary=root_cause,
                    quick_fix_steps=quick_fixes,
                )
            )

        # Sort clusters by projected monthly savings descending
        clusters.sort(key=lambda c: c.projected_monthly_savings_usd, reverse=True)
        return clusters

    def generate_deflection_tutorial(
        self,
        cluster: TicketCluster,
        output_dir: Optional[Path] = None,
        dry_run: bool = True,
        export_scorm: bool = True,
    ) -> Dict[str, Any]:
        """
        Takes a ticket cluster and autonomously builds:
        1. A 60-second microlearning video tutorial
        2. A ServiceNow / Confluence Knowledge Base (KB) Article with video embed
        3. A Teams/Slack IT Helpdesk Deflection webhook payload
        """
        job_dir = (output_dir or settings.OUTPUT_DIR) / cluster.cluster_id
        job_dir.mkdir(parents=True, exist_ok=True)

        # 1. Ideation & Script Generation
        script_gen = ScriptGenerator()
        persona_config = script_gen.load_persona(cluster.recommended_persona)

        # Generate custom deflection-focused script
        err = cluster.primary_error_code or cluster.category
        sections = [
            ScriptSection(
                section_type=SectionType.HOOK,
                voiceover_text=(
                    f"Stop! If you just got error {err} in S-A-P, don't waste 45 minutes opening a support ticket. "
                    f"Here is how to resolve it yourself in under 60 seconds."
                ),
                visual_cue="AI-SME avatar urgent direct-to-camera punch in, red IT Support banner.",
                estimated_duration_sec=4.0,
                highlight_box={"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.2},
            ),
            ScriptSection(
                section_type=SectionType.PROBLEM_CONTEXT,
                voiceover_text=(
                    f"This error triggers when {cluster.root_cause_summary} "
                    f"Our helpdesk receives dozens of these tickets every month, but the fix is completely self-service."
                ),
                visual_cue="Cut to SAP interface showing the error prompt with amber callout.",
                estimated_duration_sec=12.0,
                screen_asset_id=f"sap_error_{err.lower()}",
            ),
            ScriptSection(
                section_type=SectionType.STEP_BY_STEP_SOLUTION,
                voiceover_text=(
                    f"Step 1: {cluster.quick_fix_steps[0]} "
                    f"Step 2: {cluster.quick_fix_steps[1]} "
                    f"Step 3: {cluster.quick_fix_steps[2]}"
                ),
                visual_cue="Split screen: Avatar in corner, SAP GUI screencast showing each click.",
                estimated_duration_sec=32.0,
                screen_asset_id=f"sap_fix_{err.lower()}",
            ),
            ScriptSection(
                section_type=SectionType.CALL_TO_ACTION,
                voiceover_text=(
                    f"Save this 60-second walkthrough to your team's knowledge base, "
                    f"and confirm below if this resolved your posting error without an IT ticket!"
                ),
                visual_cue="Full screen avatar with Knowledge Base link and 'Ticket Deflected' badge.",
                estimated_duration_sec=12.0,
            ),
        ]

        script = VideoScript(
            script_id=cluster.cluster_id,
            topic=cluster.title,
            persona_id=cluster.recommended_persona,
            duration_target_seconds=60,
            sections=sections,
            hashtags=["#SAPSupport", "#TicketDeflection", "#EnterpriseIT", "#SelfService"],
            post_caption=(
                f"🚨 Resolving SAP Error {err} (Self-Service IT Deflection Guide)\n\n"
                f"Root Cause: {cluster.root_cause_summary}\n\n"
                f"3-Step Fix:\n"
                f"1. {cluster.quick_fix_steps[0]}\n"
                f"2. {cluster.quick_fix_steps[1]}\n"
                f"3. {cluster.quick_fix_steps[2]}\n\n"
                f"💡 Estimated enterprise savings: {cluster.projected_hours_saved_monthly} hours/month deflected."
            ),
        )

        # 2. Asset & Title Card Generation
        asset_gen = AssetGenerator()
        slide_path = job_dir / "screen_overlay.png"
        asset_gen.generate_title_card(
            topic=f"IT Support Deflection: Error {err}",
            persona_name=persona_config.name,
            persona_title=persona_config.title,
            output_path=slide_path,
        )

        # 3. Voice Synthesis
        voice_engine = VoiceEngine()
        audio_path = job_dir / f"{script.script_id}_voice.wav"
        full_text = " ".join([s.voiceover_text for s in script.sections])
        audio_track = voice_engine.synthesize(
            text=full_text,
            voice_id=persona_config.voice_profile.voice_id,
            output_path=audio_path,
            dry_run=dry_run,
        )

        # 4. Avatar Lip-Sync
        avatar_engine = AvatarEngine()
        avatar_video_path = job_dir / f"{script.script_id}_avatar.mp4"
        avatar_engine.animate_avatar(
            seed_image_path=Path(persona_config.visual_profile.avatar_seed_image),
            audio_file_path=audio_path,
            output_video_path=avatar_video_path,
            dry_run=dry_run,
        )

        # 5. Compositing
        compositor = VideoCompositor()
        job = VideoRenderJob(
            job_id=script.script_id,
            script=script,
            layout=VideoLayout.WIDESCREEN_16_9,
        )
        composited_job = compositor.composite(
            job=job,
            audio_track=audio_track,
            avatar_video_path=avatar_video_path,
            screen_asset_path=slide_path,
            dry_run=dry_run,
        )

        # 6. SCORM Export
        scorm_zip_path = None
        if export_scorm:
            scorm_packager = ScormPackager()
            scorm_zip_path = str(scorm_packager.package(composited_job, job_dir))

        # 7. Knowledge Base Article Generation (HTML & Markdown)
        kb_content = self.generate_kb_article(composited_job, cluster)
        kb_path = job_dir / "service_desk_kb_article.md"
        with open(kb_path, "w", encoding="utf-8") as f:
            f.write(kb_content)

        # 8. Helpdesk Bot Notification Webhook Payload
        webhook_pub = WebhookPublisher()
        webhook_payload = webhook_pub.send_teams(
            webhook_url="https://outlook.office.com/webhook/sample-it-deflection",
            job=composited_job,
            dry_run=True,
        )

        # Persist job
        repo = get_job_repository()
        repo.save_job(composited_job)

        return {
            "cluster_id": cluster.cluster_id,
            "job_id": composited_job.job_id,
            "topic": cluster.title,
            "persona": persona_config.name,
            "video_path": composited_job.output_file_path,
            "subtitles_path": composited_job.subtitles_file_path,
            "kb_article_path": str(kb_path),
            "scorm_package_path": scorm_zip_path,
            "projected_monthly_savings_usd": cluster.projected_monthly_savings_usd,
            "projected_hours_saved_monthly": cluster.projected_hours_saved_monthly,
            "webhook_payload": webhook_payload,
        }

    def generate_kb_article(self, job: VideoRenderJob, cluster: TicketCluster) -> str:
        """Generates an enterprise-grade Knowledge Base article for ServiceNow or Confluence."""
        err = cluster.primary_error_code or cluster.category
        steps_md = "\n".join([f"{i+1}. **{step}**" for i, step in enumerate(cluster.quick_fix_steps)])

        return f"""# Knowledge Base Article: Resolving SAP Error {err}
**KB Number:** KB009412 | **Category:** {cluster.category} | **Target Audience:** All SAP Users & Business Planners  
**Deflection Status:** Active (Automated 60-Second Video Solution Attached)

---

## 📹 60-Second Self-Service Video Walkthrough
*(Delivered by AI-SME {job.script.persona_id.replace('_', ' ').title()})*

```html
<video controls width="100%" poster="screen_overlay.png">
  <source src="{job.job_id}_final.mp4" type="video/mp4">
  <track src="{job.job_id}_captions.vtt" kind="subtitles" srclang="en" label="English">
  Your browser does not support video playback.
</video>
```

---

## 1. Problem Description & Symptoms
When executing transactions in {cluster.category}, users encounter error **{err}**:
> *"{cluster.root_cause_summary}"*

### Impact on Operations
* Delayed order fulfillment or blocked financial reconciliations.
* Support desk wait times of ~{cluster.avg_resolution_minutes} minutes per ticket.

---

## 2. Step-by-Step Self-Service Resolution
Follow these steps to clear the error immediately without waiting for an IT support agent:

{steps_md}

---

## 3. Verification Checklist
- [ ] Error status bar in SAP GUI / Fiori turns green.
- [ ] Document number or posting confirmation is generated.
- [ ] No subsequent posting locks are reported in transaction SM12.

---

## 4. Still Need Assistance?
If the error persists after following these 3 steps, please reply to your existing ticket with:
1. The exact Company Code / Plant / Storage Location.
2. A screenshot of transaction output.
"""
