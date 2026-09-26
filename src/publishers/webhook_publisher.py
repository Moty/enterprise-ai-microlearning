"""Internal Enterprise Distribution Webhook Publisher (Microsoft Teams & Slack)."""

import json
import logging
from typing import Any, Dict, Optional
import requests

from src.core.models import VideoRenderJob

logger = logging.getLogger(__name__)


class WebhookPublisher:
    """Dispatches microlearning drops to enterprise learning channels (Teams / Slack)."""

    @staticmethod
    def format_teams_payload(job: VideoRenderJob, video_url: Optional[str] = None) -> Dict[str, Any]:
        """
        Formats an actionable Microsoft Teams MessageCard payload.
        """
        topic = job.script.topic
        persona = job.script.persona_id
        duration_target = job.script.duration_target_seconds

        facts = [
            {"name": "AI-SME Presenter", "value": persona},
            {"name": "Target Duration", "value": f"{duration_target} seconds"},
            {"name": "Status", "value": job.status.upper()},
            {"name": "Hashtags", "value": " ".join(job.script.hashtags)},
        ]

        actions = []
        if video_url:
            actions.append({
                "@type": "OpenURI",
                "name": "▶ Watch Video",
                "targets": [{"os": "default", "uri": video_url}],
            })

        return {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": "0070F2",  # SAP Blue
            "summary": f"New SAP Microlearning Drop: {topic}",
            "sections": [
                {
                    "activityTitle": f"⚡ New 60s Microlearning Drop: {topic}",
                    "activitySubtitle": f"Published by Enterprise AI-SME Engine for {persona}",
                    "facts": facts,
                    "text": job.script.post_caption[:250] + "...",
                }
            ],
            "potentialAction": actions,
        }

    @staticmethod
    def format_slack_payload(job: VideoRenderJob, video_url: Optional[str] = None) -> Dict[str, Any]:
        """
        Formats a rich Slack Block Kit notification payload.
        """
        topic = job.script.topic
        persona = job.script.persona_id

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"⚡ SAP Microlearning: {topic}", "emoji": True},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Presenter:*\n{persona}"},
                    {"type": "mrkdwn", "text": f"*Format:*\n{job.layout.value}"},
                    {"type": "mrkdwn", "text": f"*Status:*\n`{job.status}`"},
                    {"type": "mrkdwn", "text": f"*Sections:*\n{len(job.script.sections)} steps"},
                ],
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"> {job.script.post_caption[:200]}..."},
            },
        ]

        if video_url:
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "▶ Watch Microlearning", "emoji": True},
                        "style": "primary",
                        "url": video_url,
                    }
                ],
            })

        return {"blocks": blocks}

    def send_teams(self, webhook_url: str, job: VideoRenderJob, video_url: Optional[str] = None, dry_run: bool = False) -> Dict[str, Any]:
        """Sends or previews a Microsoft Teams notification."""
        payload = self.format_teams_payload(job, video_url)
        if dry_run:
            return {"status": "simulated", "payload": payload}

        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            resp.raise_for_status()
            return {"status": "sent", "status_code": resp.status_code}
        except Exception as e:
            logger.error(f"Failed to post to Teams webhook: {e}")
            raise RuntimeError(f"Teams webhook failed: {e}") from e

    def send_slack(self, webhook_url: str, job: VideoRenderJob, video_url: Optional[str] = None, dry_run: bool = False) -> Dict[str, Any]:
        """Sends or previews a Slack notification."""
        payload = self.format_slack_payload(job, video_url)
        if dry_run:
            return {"status": "simulated", "payload": payload}

        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            resp.raise_for_status()
            return {"status": "sent", "status_code": resp.status_code}
        except Exception as e:
            logger.error(f"Failed to post to Slack webhook: {e}")
            raise RuntimeError(f"Slack webhook failed: {e}") from e
