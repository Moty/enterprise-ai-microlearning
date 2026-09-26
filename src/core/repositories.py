"""Repository abstraction for VideoRenderJob state persistence (Local JSON & Cloud Firestore)."""

import json
import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.config import settings
from src.core.models import VideoRenderJob

logger = logging.getLogger(__name__)


class JobRepository(ABC):
    """Abstract base repository contract for managing VideoRenderJob lifecycles."""

    @abstractmethod
    def save_job(self, job: VideoRenderJob) -> None:
        """Persists or updates a VideoRenderJob."""
        pass

    @abstractmethod
    def get_job(self, job_id: str) -> Optional[VideoRenderJob]:
        """Retrieves a job by its unique job_id."""
        pass

    @abstractmethod
    def list_jobs(self, status: Optional[str] = None, limit: int = 50) -> List[VideoRenderJob]:
        """Lists historical jobs, optionally filtered by status."""
        pass

    @abstractmethod
    def update_status(
        self,
        job_id: str,
        status: str,
        error_message: Optional[str] = None,
        output_file_path: Optional[str] = None,
    ) -> Optional[VideoRenderJob]:
        """Updates the status and optional metadata of an existing job."""
        pass


class LocalJsonJobRepository(JobRepository):
    """Local filesystem repository persisting job manifests as JSON files."""

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or settings.OUTPUT_DIR

    @staticmethod
    def _validate_job_id(job_id: str) -> None:
        if not job_id or not re.match(r"^[a-zA-Z0-9_-]+$", job_id):
            raise ValueError(f"Invalid job_id: {job_id!r}")

    def _manifest_path(self, job_id: str) -> Path:
        self._validate_job_id(job_id)
        resolved_base = self.base_dir.resolve()
        path = (self.base_dir / job_id / "manifest.json").resolve()
        if not path.is_relative_to(resolved_base):
            raise ValueError(f"Path traversal detected for job_id: {job_id!r}")
        return path

    def save_job(self, job: VideoRenderJob) -> None:
        path = self._manifest_path(job.job_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(job.model_dump_json(indent=2))

    def get_job(self, job_id: str) -> Optional[VideoRenderJob]:
        path = self._manifest_path(job_id)
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return VideoRenderJob.model_validate_json(f.read())

    def list_jobs(self, status: Optional[str] = None, limit: int = 50) -> List[VideoRenderJob]:
        if not self.base_dir.exists():
            return []

        jobs: List[VideoRenderJob] = []
        manifest_files = sorted(
            self.base_dir.glob("*/manifest.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        for path in manifest_files:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    job = VideoRenderJob.model_validate_json(f.read())
                    if status is None or job.status == status:
                        jobs.append(job)
                        if len(jobs) >= limit:
                            break
            except Exception as e:
                logger.warning(f"Failed to parse manifest at {path}: {e}")
                continue

        return jobs

    def update_status(
        self,
        job_id: str,
        status: str,
        error_message: Optional[str] = None,
        output_file_path: Optional[str] = None,
    ) -> Optional[VideoRenderJob]:
        job = self.get_job(job_id)
        if not job:
            return None

        job.status = status  # type: ignore[assignment]
        if error_message is not None:
            job.error_message = error_message
        if output_file_path is not None:
            job.output_file_path = output_file_path

        self.save_job(job)
        return job


class FirestoreJobRepository(JobRepository):
    """
    Cloud Firestore repository for multi-worker distributed rendering
    and real-time enterprise SME review dashboards.
    """

    def __init__(
        self,
        client: Optional[Any] = None,
        collection_name: Optional[str] = None,
        database: Optional[str] = None,
        project_id: Optional[str] = None,
    ):
        self.collection_name = collection_name or settings.FIRESTORE_COLLECTION_JOBS
        self.database = database or settings.FIRESTORE_DATABASE_ID
        self.project_id = project_id or (settings.FIREBASE_PROJECT_ID or None)

        if client is not None:
            self.db = client
        else:
            try:
                import shutil
                import subprocess
                from google.cloud import firestore

                credentials = None
                try:
                    import google.auth
                    from google.auth.transport.requests import Request

                    creds, _ = google.auth.default()
                    creds.refresh(Request())
                    credentials = creds
                except Exception:
                    # Fallback to active gcloud token if ADC has expired refresh token
                    if shutil.which("gcloud"):
                        try:
                            token_res = subprocess.run(
                                ["gcloud", "auth", "print-access-token"],
                                capture_output=True,
                                text=True,
                                timeout=5,
                            )
                            if token_res.returncode == 0 and token_res.stdout.strip():
                                from google.oauth2.credentials import Credentials

                                credentials = Credentials(token_res.stdout.strip())
                        except Exception as e:
                            logger.debug(f"Failed to fetch gcloud access token: {e}")

                if self.project_id:
                    self.db = firestore.Client(
                        project=self.project_id,
                        database=self.database,
                        credentials=credentials,
                    )
                else:
                    self.db = firestore.Client(
                        database=self.database,
                        credentials=credentials,
                    )
            except ImportError as e:
                raise ImportError(
                    "google-cloud-firestore package is required for FirestoreJobRepository. "
                    "Install with: pip install google-cloud-firestore"
                ) from e
            except Exception as e:
                raise RuntimeError(
                    f"Failed to initialize Firestore client for project '{self.project_id}': {e}"
                ) from e

    @staticmethod
    def _validate_job_id(job_id: str) -> None:
        if not job_id or not re.match(r"^[a-zA-Z0-9_-]+$", job_id):
            raise ValueError(f"Invalid job_id: {job_id!r}")

    def save_job(self, job: VideoRenderJob) -> None:
        self._validate_job_id(job.job_id)
        doc_ref = self.db.collection(self.collection_name).document(job.job_id)
        # Use mode='json' to ensure datetime and UUIDs are properly serialized for NoSQL
        data = job.model_dump(mode="json")
        doc_ref.set(data, merge=True)

    def get_job(self, job_id: str) -> Optional[VideoRenderJob]:
        self._validate_job_id(job_id)
        doc_ref = self.db.collection(self.collection_name).document(job_id)
        snapshot = doc_ref.get()
        if not snapshot.exists:
            return None
        return VideoRenderJob.model_validate(snapshot.to_dict())

    def list_jobs(self, status: Optional[str] = None, limit: int = 50) -> List[VideoRenderJob]:
        col_ref = self.db.collection(self.collection_name)
        query = col_ref

        if status:
            query = query.where("status", "==", status)

        docs = query.limit(limit).stream()
        results: List[VideoRenderJob] = []
        for doc in docs:
            try:
                job = VideoRenderJob.model_validate(doc.to_dict())
                results.append(job)
            except Exception as e:
                logger.warning(f"Failed to deserialize Firestore document {doc.id}: {e}")
                continue
        return results

    def update_status(
        self,
        job_id: str,
        status: str,
        error_message: Optional[str] = None,
        output_file_path: Optional[str] = None,
    ) -> Optional[VideoRenderJob]:
        self._validate_job_id(job_id)
        doc_ref = self.db.collection(self.collection_name).document(job_id)
        updates: Dict[str, Any] = {"status": status}
        if error_message is not None:
            updates["error_message"] = error_message
        if output_file_path is not None:
            updates["output_file_path"] = output_file_path

        doc_ref.update(updates)
        return self.get_job(job_id)


def get_job_repository(backend: Optional[str] = None) -> JobRepository:
    """Factory helper returning the configured JobRepository implementation."""
    selected_backend = backend or settings.STORAGE_BACKEND
    if selected_backend == "firestore":
        return FirestoreJobRepository()
    return LocalJsonJobRepository()
