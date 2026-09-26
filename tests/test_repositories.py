"""Unit tests for the repository abstraction (Local JSON & Cloud Firestore)."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from src.core.config import settings
from src.core.models import VideoLayout, VideoRenderJob, VideoScript
from src.core.repositories import (
    FirestoreJobRepository,
    JobRepository,
    LocalJsonJobRepository,
    get_job_repository,
)


def _create_sample_job(job_id: str, status: str = "pending") -> VideoRenderJob:
    script = VideoScript(
        script_id=job_id,
        topic="S/4HANA Clean Core Extensibility",
        persona_id="sap_architect",
        sections=[],
        hashtags=["#SAP"],
        post_caption="Clean Core Breakdown",
    )
    return VideoRenderJob(
        job_id=job_id,
        script=script,
        status=status,  # type: ignore[arg-type]
    )


class TestLocalJsonJobRepository(unittest.TestCase):
    def test_save_and_get_job(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = LocalJsonJobRepository(base_dir=Path(tmp_dir))
            job = _create_sample_job("job_001", status="pending")

            repo.save_job(job)

            retrieved = repo.get_job("job_001")
            self.assertIsNotNone(retrieved)
            self.assertEqual(retrieved.job_id, "job_001")
            self.assertEqual(retrieved.status, "pending")
            self.assertEqual(retrieved.script.topic, "S/4HANA Clean Core Extensibility")

    def test_get_nonexistent_job(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = LocalJsonJobRepository(base_dir=Path(tmp_dir))
            self.assertIsNone(repo.get_job("nonexistent_id"))

    def test_list_jobs_and_filter(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = LocalJsonJobRepository(base_dir=Path(tmp_dir))
            job1 = _create_sample_job("job_001", status="pending")
            job2 = _create_sample_job("job_002", status="composited")
            job3 = _create_sample_job("job_003", status="composited")

            repo.save_job(job1)
            repo.save_job(job2)
            repo.save_job(job3)

            all_jobs = repo.list_jobs()
            self.assertEqual(len(all_jobs), 3)

            composited = repo.list_jobs(status="composited")
            self.assertEqual(len(composited), 2)
            for j in composited:
                self.assertEqual(j.status, "composited")

            limited = repo.list_jobs(limit=1)
            self.assertEqual(len(limited), 1)

    def test_update_status(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = LocalJsonJobRepository(base_dir=Path(tmp_dir))
            job = _create_sample_job("job_update", status="pending")
            repo.save_job(job)

            updated = repo.update_status(
                job_id="job_update",
                status="failed",
                error_message="Audio timeout",
            )
            self.assertIsNotNone(updated)
            self.assertEqual(updated.status, "failed")
            self.assertEqual(updated.error_message, "Audio timeout")

            # Verify persisted
            re_read = repo.get_job("job_update")
            self.assertEqual(re_read.status, "failed")
            self.assertEqual(re_read.error_message, "Audio timeout")


class TestFirestoreJobRepository(unittest.TestCase):
    def test_save_and_get_with_mock_client(self):
        mock_client = MagicMock()
        mock_col = MagicMock()
        mock_doc = MagicMock()
        mock_client.collection.return_value = mock_col
        mock_col.document.return_value = mock_doc

        repo = FirestoreJobRepository(client=mock_client, collection_name="test_jobs")
        job = _create_sample_job("fire_001", status="composited")

        # Test save
        repo.save_job(job)
        mock_client.collection.assert_called_with("test_jobs")
        mock_col.document.assert_called_with("fire_001")
        mock_doc.set.assert_called_once()
        saved_payload = mock_doc.set.call_args[0][0]
        self.assertEqual(saved_payload["job_id"], "fire_001")
        self.assertEqual(saved_payload["status"], "composited")

        # Test get existing
        mock_snapshot = MagicMock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = job.model_dump(mode="json")
        mock_doc.get.return_value = mock_snapshot

        fetched = repo.get_job("fire_001")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.job_id, "fire_001")
        self.assertEqual(fetched.status, "composited")

    def test_get_nonexistent_document(self):
        mock_client = MagicMock()
        mock_col = MagicMock()
        mock_doc = MagicMock()
        mock_client.collection.return_value = mock_col
        mock_col.document.return_value = mock_doc

        mock_snapshot = MagicMock()
        mock_snapshot.exists = False
        mock_doc.get.return_value = mock_snapshot

        repo = FirestoreJobRepository(client=mock_client)
        self.assertIsNone(repo.get_job("not_found"))

    def test_update_status_calls_update(self):
        mock_client = MagicMock()
        mock_col = MagicMock()
        mock_doc = MagicMock()
        mock_client.collection.return_value = mock_col
        mock_col.document.return_value = mock_doc

        job = _create_sample_job("fire_002", status="generating_audio")
        mock_snapshot = MagicMock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = job.model_dump(mode="json")
        mock_doc.get.return_value = mock_snapshot

        repo = FirestoreJobRepository(client=mock_client)
        repo.update_status(
            job_id="fire_002",
            status="audio_generated",
            output_file_path="/path/to/voice.wav",
        )

        mock_doc.update.assert_called_once_with({
            "status": "audio_generated",
            "output_file_path": "/path/to/voice.wav",
        })


class TestRepositoryFactory(unittest.TestCase):
    def test_default_returns_local_repo(self):
        repo = get_job_repository("local")
        self.assertIsInstance(repo, LocalJsonJobRepository)

    def test_firestore_returns_firestore_repo(self):
        with unittest.mock.patch("google.cloud.firestore.Client"):
            repo = get_job_repository("firestore")
            self.assertIsInstance(repo, FirestoreJobRepository)


if __name__ == "__main__":
    unittest.main()
