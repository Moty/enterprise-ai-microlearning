"""Autonomous SAP Topic & Note Ingestion Engine (Curated Catalog & RSS Feed Crawler)."""

import logging
import re
import defusedxml.ElementTree as ET
from typing import Any, Dict, List, Optional
import requests

from src.core.models import VideoLayout, VideoRenderJob
from src.pipeline.asset_generator import AssetGenerator
from src.pipeline.avatar_engine import AvatarEngine
from src.pipeline.compositor import VideoCompositor
from src.pipeline.ideation import ScriptGenerator
from src.pipeline.voice_engine import VoiceEngine
from src.publishers.linkedin_publisher import LinkedInPublisher
from src.publishers.scorm_packager import ScormPackager
from src.core.config import settings

logger = logging.getLogger(__name__)


class TopicIngestionEngine:
    """Ingests enterprise SAP topics from curated error catalogs and live Community feeds."""

    # Built-in High-Impact SAP Knowledgebase
    CURATED_SAP_CATALOG: List[Dict[str, Any]] = [
        {
            "id": "sap_error_m7021",
            "topic": "SAP Error M7021: Deficit of SL Unrestricted-Use Stock",
            "persona_id": "erp_functional_consultant",
            "error_code": "M7021",
            "category": "Materials Management (MM) & Inventory",
            "impact_score": 9.5,
        },
        {
            "id": "clean_core_extensibility_tiers",
            "topic": "SAP Clean Core Extensibility: Tier 1 vs Tier 2 vs Tier 3",
            "persona_id": "sap_architect",
            "error_code": None,
            "category": "Architecture & S/4HANA Cloud",
            "impact_score": 9.8,
        },
        {
            "id": "fiori_elements_smart_filterbar",
            "topic": "Fiori Elements: Adding Smart FilterBar with 3 CDS Annotations",
            "persona_id": "fiori_dev",
            "error_code": None,
            "category": "Fiori & ABAP Cloud Development",
            "impact_score": 9.0,
        },
        {
            "id": "sap_sm59_rfc_connection_drops",
            "topic": "Debugging RFC Connection Drops in Transaction SM59",
            "persona_id": "fiori_dev",
            "error_code": "SM59",
            "category": "Integration & SAP Gateway",
            "impact_score": 8.7,
        },
        {
            "id": "cvi_business_partner_mds_load_cockpit",
            "topic": "S/4HANA CVI Synchronization: Fixing MDS_LOAD_COCKPIT Errors",
            "persona_id": "sap_architect",
            "error_code": "MDS_LOAD_COCKPIT",
            "category": "S/4HANA Migration & Master Data",
            "impact_score": 9.2,
        },
        {
            "id": "me21n_purchase_order_commitment_block",
            "topic": "Clearing Purchase Order Commitment Exceptions in ME21N",
            "persona_id": "erp_functional_consultant",
            "error_code": "ME21N",
            "category": "Procurement & Sourcing",
            "impact_score": 8.9,
        },
    ]

    @classmethod
    def get_curated_topics(cls, limit: int = 10) -> List[Dict[str, Any]]:
        """Returns high-impact topics from the enterprise knowledgebase."""
        return cls.CURATED_SAP_CATALOG[:limit]

    @staticmethod
    def match_persona_for_topic(title: str, description: str = "") -> str:
        """Heuristically routes a topic to the best AI-SME persona."""
        combined = f"{title} {description}".lower()

        dev_keywords = ["fiori", "abap", "cds", "rap", "ui5", "adt", "annotation", "badi", "odata"]
        arch_keywords = ["clean core", "s/4hana", "btp", "migration", "architecture", "event mesh", "integration suite", "cvi"]
        functional_keywords = ["migo", "mmbe", "inventory", "stock", "purchase order", "me21n", "logistics", "supply chain", "m7021"]

        if any(k in combined for k in dev_keywords):
            return "fiori_dev"
        if any(k in combined for k in arch_keywords):
            return "sap_architect"
        if any(k in combined for k in functional_keywords):
            return "erp_functional_consultant"

        return "sap_architect"

    USER_AGENT = "EnterpriseMicrolearningEngine/1.0 (+https://github.com/enterprise-ai-microlearning)"

    def crawl_rss_feed(self, feed_url: str = "https://blogs.sap.com/feed/", limit: int = 5) -> List[Dict[str, Any]]:
        """
        Crawls and parses an RSS XML feed from SAP Community or corporate blogs.
        """
        try:
            headers = {"User-Agent": self.USER_AGENT}
            resp = requests.get(feed_url, headers=headers, timeout=15)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)

            items = []
            for item in root.findall(".//item")[:limit]:
                title = item.findtext("title") or ""
                desc = item.findtext("description") or ""
                link = item.findtext("link") or ""

                # Clean HTML tags from description
                clean_desc = re.sub(r"<[^>]+>", "", desc).strip()
                persona = self.match_persona_for_topic(title, clean_desc)

                items.append({
                    "id": f"rss_{abs(hash(title)) % 1000000}",
                    "topic": title,
                    "persona_id": persona,
                    "error_code": None,
                    "source_url": link,
                    "description": clean_desc[:200],
                })
            return items
        except Exception as e:
            logger.warning(f"Failed to crawl RSS feed ({feed_url}): {e}")
            return []

    def execute_batch_production(
        self,
        topics: List[Dict[str, Any]],
        dry_run: bool = True,
        export_scorm: bool = True,
    ) -> List[VideoRenderJob]:
        """
        Orchestrates autonomous batch production across all ingested topics.
        """
        script_gen = ScriptGenerator()
        voice_engine = VoiceEngine()
        avatar_engine = AvatarEngine()
        compositor = VideoCompositor()
        asset_gen = AssetGenerator()
        publisher = LinkedInPublisher()
        scorm_packager = ScormPackager() if export_scorm else None

        completed_jobs: List[VideoRenderJob] = []

        for item in topics:
            topic_title = item.get("topic", "Untitled")
            persona_id = item.get("persona_id", "sap_architect")
            error_code = item.get("error_code")

            try:
                # 1. Script
                script = script_gen.generate_script(
                    topic=topic_title,
                    persona_id=persona_id,
                    specific_error_or_tcode=error_code,
                    dry_run=dry_run,
                )

                job_dir = settings.OUTPUT_DIR / script.script_id
                job_dir.mkdir(parents=True, exist_ok=True)
                persona_config = script_gen.load_persona(persona_id)

                # 2. Visual slide
                slide_path = job_dir / "screen_overlay.png"
                asset_gen.generate_title_card(
                    topic=topic_title,
                    persona_name=persona_config.name,
                    persona_title=persona_config.title,
                    output_path=slide_path,
                )

                # 3. Audio
                audio_path = job_dir / f"{script.script_id}_voice.wav"
                full_text = " ".join([s.voiceover_text for s in script.sections])
                audio_track = voice_engine.synthesize(
                    text=full_text,
                    voice_id=persona_config.voice_profile.voice_id,
                    output_path=audio_path,
                    dry_run=dry_run,
                )

                # 4. Avatar
                avatar_video_path = job_dir / f"{script.script_id}_avatar.mp4"
                avatar_engine.animate_avatar(
                    seed_image_path=settings.BASE_DIR / persona_config.visual_profile.avatar_seed_image,
                    audio_file_path=audio_path,
                    output_video_path=avatar_video_path,
                    dry_run=dry_run,
                )

                # 5. Compositor
                job = VideoRenderJob(
                    job_id=script.script_id,
                    script=script,
                    layout=VideoLayout.LINKEDIN_PORTRAIT_4_5,
                )
                composited_job = compositor.composite(
                    job=job,
                    audio_track=audio_track,
                    avatar_video_path=avatar_video_path,
                    screen_asset_path=slide_path,
                    dry_run=dry_run,
                )

                # 6. LinkedIn draft
                publisher.publish_draft(composited_job, job_dir)

                # 7. SCORM package
                if scorm_packager:
                    scorm_packager.package(composited_job, job_dir)

                completed_jobs.append(composited_job)
            except Exception as e:
                logger.error("Failed to process batch topic '%s' (%s): %s", topic_title, persona_id, e)
                continue

        return completed_jobs
