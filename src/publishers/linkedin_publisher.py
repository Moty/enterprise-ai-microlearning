"""LinkedIn Post Formatter and Publisher."""

import json
from pathlib import Path
from typing import Dict, List, Optional
from src.core.config import settings
from src.core.models import VideoRenderJob


class LinkedInPublisher:
    """Handles formatting and publishing video microlearning assets to LinkedIn."""

    def format_post_payload(
        self,
        job: VideoRenderJob,
        first_comment_link: Optional[str] = None
    ) -> Dict:
        """
        Formats a LinkedIn Community Management API video share payload.
        """
        caption = job.script.post_caption
        if job.script.hashtags:
            caption += "\n\n" + " ".join(job.script.hashtags)

        payload = {
            "author": settings.LINKEDIN_AUTHOR_URN,
            "commentary": caption,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": []
            },
            "content": {
                "media": {
                    "title": job.script.topic,
                    "description": f"60-second SAP microlearning breakdown for {job.script.topic}."
                }
            }
        }
        
        if first_comment_link:
            payload["first_comment"] = f"📥 Download the full step-by-step PDF guide here: {first_comment_link}"

        return payload

    def publish_draft(self, job: VideoRenderJob, output_dir: Path) -> Path:
        """
        Saves a local publish package (video reference, captions, copy, and first comment).
        """
        payload = self.format_post_payload(job)
        publish_file = output_dir / f"{job.job_id}_linkedin_package.json"
        with open(publish_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return publish_file
