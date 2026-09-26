"""LinkedIn Post Formatter and Direct REST API Publisher."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import requests

from src.core.config import settings
from src.core.models import VideoRenderJob

logger = logging.getLogger(__name__)


class LinkedInError(RuntimeError):
    """Base exception for LinkedIn publishing operations."""
    pass


class LinkedInAuthError(LinkedInError):
    """Raised on authentication/authorization failures (HTTP 401, 403)."""
    pass


class LinkedInRateLimitError(LinkedInError):
    """Raised when LinkedIn API rate limit is exceeded (HTTP 429)."""
    pass


class LinkedInUploadError(LinkedInError):
    """Raised when media registration or binary stream upload fails."""
    pass


class LinkedInPublisher:
    """Handles formatting and publishing video microlearning assets to LinkedIn."""

    API_BASE = "https://api.linkedin.com/v2"

    def __init__(self, access_token: Optional[str] = None, author_urn: Optional[str] = None):
        self.access_token = access_token or settings.LINKEDIN_ACCESS_TOKEN
        self.author_urn = author_urn or settings.LINKEDIN_AUTHOR_URN

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        }

    def format_post_payload(
        self,
        job: VideoRenderJob,
        first_comment_link: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Formats a LinkedIn Community Management API video share payload.
        """
        caption = job.script.post_caption
        if job.script.hashtags:
            caption += "\n\n" + " ".join(job.script.hashtags)

        payload: Dict[str, Any] = {
            "author": self.author_urn,
            "commentary": caption,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "content": {
                "media": {
                    "title": job.script.topic,
                    "description": f"60-second SAP microlearning breakdown for {job.script.topic}.",
                }
            },
        }

        if first_comment_link:
            payload["first_comment"] = f"📥 Download the full step-by-step PDF guide here: {first_comment_link}"

        return payload

    def register_video_upload(self, title: str) -> Tuple[str, str]:
        """
        Registers an asset upload request with LinkedIn Digital Media API.
        Returns: (upload_url, asset_urn)
        """
        url = f"{self.API_BASE}/assets?action=registerUpload"
        body = {
            "registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-video"],
                "owner": self.author_urn,
                "serviceRelationships": [
                    {
                        "relationshipType": "OWNER",
                        "identifier": "urn:li:userGeneratedContent",
                    }
                ],
            }
        }
        resp = requests.post(url, headers=self._headers(), json=body, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        upload_mechanism = data["value"]["uploadMechanism"]
        upload_url = upload_mechanism["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]["uploadUrl"]
        asset_urn = data["value"]["asset"]
        return upload_url, asset_urn

    def upload_video_binary(self, upload_url: str, video_path: Path) -> None:
        """Uploads the binary MP4 file to LinkedIn's media CDN."""
        video_path = Path(video_path)
        with open(video_path, "rb") as f:
            headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/octet-stream"}
            resp = requests.put(upload_url, headers=headers, data=f, timeout=120)
            resp.raise_for_status()

    def create_ugc_post(self, commentary: str, asset_urn: str, title: str) -> str:
        """Publishes the UGC post referencing the uploaded digital asset."""
        url = f"{self.API_BASE}/ugcPosts"
        body = {
            "author": self.author_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "media": [
                        {
                            "media": asset_urn,
                            "status": "READY",
                            "title": {"attributes": [], "text": title[:200]},
                        }
                    ],
                    "shareCommentary": {"attributes": [], "text": commentary},
                    "shareMediaCategory": "VIDEO",
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }
        resp = requests.post(url, headers=self._headers(), json=body, timeout=20)
        resp.raise_for_status()
        post_urn = resp.json().get("id") or resp.headers.get("x-restli-id", "")
        return post_urn

    def post_first_comment(self, post_urn: str, comment_text: str) -> str:
        """Publishes a first comment on the post with lead magnet resource links."""
        url = f"{self.API_BASE}/socialActions/{post_urn}/comments"
        body = {
            "actor": self.author_urn,
            "message": {"attributes": [], "text": comment_text},
        }
        resp = requests.post(url, headers=self._headers(), json=body, timeout=20)
        resp.raise_for_status()
        return resp.json().get("id", "comment_created")

    def publish_draft(self, job: VideoRenderJob, output_dir: Path) -> Path:
        """
        Saves a local publish package (video reference, captions, copy, and first comment).
        Ensures target directory exists before writing.
        """
        target_dir = Path(output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        payload = self.format_post_payload(job)
        publish_file = target_dir / f"{job.job_id}_linkedin_package.json"
        with open(publish_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return publish_file

    def publish_live(
        self,
        job: VideoRenderJob,
        video_path: Optional[Path] = None,
        first_comment_link: Optional[str] = None,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """
        Executes end-to-end publishing to LinkedIn:
        1. Registers video asset upload
        2. Streams video binary to CDN
        3. Creates UGC video post
        4. Adds first-comment lead magnet
        """
        payload = self.format_post_payload(job, first_comment_link=first_comment_link)

        if dry_run or not self.access_token:
            return {
                "status": "simulated",
                "post_urn": f"urn:li:ugcPost:simulated_{job.job_id}",
                "author": self.author_urn or "urn:li:person:LOCAL_SIMULATED",
                "payload": payload,
            }

        try:
            target_video = video_path or Path(job.output_file_path or "")
            if not target_video.exists():
                raise FileNotFoundError(f"Video file not found at: {target_video}")

            # 1. Register
            upload_url, asset_urn = self.register_video_upload(title=job.script.topic)

            # 2. Upload binary
            self.upload_video_binary(upload_url, target_video)

            # 3. Create UGC Post
            post_urn = self.create_ugc_post(
                commentary=payload["commentary"],
                asset_urn=asset_urn,
                title=job.script.topic,
            )

            # 4. Optional first comment
            comment_urn = None
            if first_comment_link:
                comment_text = f"📥 Download the full step-by-step PDF guide here: {first_comment_link}"
                comment_urn = self.post_first_comment(post_urn, comment_text)

            return {
                "status": "published",
                "post_urn": post_urn,
                "asset_urn": asset_urn,
                "comment_urn": comment_urn,
            }
        except requests.HTTPError as e:
            status_code = getattr(e.response, "status_code", None)
            logger.error(f"LinkedIn HTTP error ({status_code}): {e}")
            if status_code in (401, 403):
                raise LinkedInAuthError(f"LinkedIn authentication failed ({status_code}): {e}") from e
            elif status_code == 429:
                raise LinkedInRateLimitError(f"LinkedIn rate limit exceeded (429): {e}") from e
            raise LinkedInUploadError(f"LinkedIn API error ({status_code}): {e}") from e
        except FileNotFoundError as e:
            logger.error(f"Video file missing: {e}")
            raise LinkedInError(f"Video file not found: {e}") from e
        except LinkedInError:
            raise
        except Exception as e:
            logger.error(f"Failed to publish to LinkedIn: {e}")
            raise LinkedInError(f"LinkedIn publishing failed: {e}") from e
