"""Enterprise Microlearning Analytics Feedback & Retention Optimizer."""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from src.core.config import settings

logger = logging.getLogger(__name__)


class ViewershipMetric(BaseModel):
    """Viewership and telemetry record for a single microlearning module."""
    job_id: str
    views_count: int = 0
    completions_count: int = 0
    avg_watch_time_sec: float = 0.0
    hook_dropoff_rate: float = 0.0  # percentage of viewers leaving before 5 seconds
    problem_dropoff_rate: float = 0.0
    scorm_mastery_rate: Optional[float] = None  # percentage scoring >= 80% in LMS
    hook_style: str = "warning_symptom"
    retention_score: float = 0.0  # Composite 0-100 score
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


try:
    import fcntl
except ImportError:
    fcntl = None  # Windows fallback


class AnalyticsEngine:
    """Tracks learner engagement, calculates retention scores, and auto-tunes hook formulas."""

    def __init__(self, data_file: Optional[Path] = None):
        self.data_file = data_file or (settings.OUTPUT_DIR / "analytics_telemetry.json")

    def _load_data(self) -> Dict[str, Dict[str, Any]]:
        """Loads telemetry database from disk with a shared lock."""
        if not self.data_file.exists():
            return {}
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                if fcntl:
                    try:
                        fcntl.flock(f, fcntl.LOCK_SH)
                    except OSError:
                        pass
                try:
                    content = f.read()
                    return json.loads(content) if content.strip() else {}
                finally:
                    if fcntl:
                        try:
                            fcntl.flock(f, fcntl.LOCK_UN)
                        except OSError:
                            pass
        except Exception as e:
            logger.warning("Failed to load analytics telemetry: %s", e)
            return {}

    def _save_data(self, data: Dict[str, Dict[str, Any]]) -> None:
        """Persists telemetry database to disk with an exclusive lock."""
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.data_file, "w", encoding="utf-8") as f:
            if fcntl:
                try:
                    fcntl.flock(f, fcntl.LOCK_EX)
                except OSError:
                    pass
            try:
                f.write(json.dumps(data, indent=2, default=str))
                f.flush()
            finally:
                if fcntl:
                    try:
                        fcntl.flock(f, fcntl.LOCK_UN)
                    except OSError:
                        pass

    def _atomic_update(self, updater_fn) -> Dict[str, Any]:
        """Atomically loads, updates, and persists telemetry data under an exclusive lock."""
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.data_file.exists():
            self.data_file.write_text("{}", encoding="utf-8")

        with open(self.data_file, "r+", encoding="utf-8") as f:
            if fcntl:
                try:
                    fcntl.flock(f, fcntl.LOCK_EX)
                except OSError:
                    pass
            try:
                content = f.read()
                data = json.loads(content) if content.strip() else {}
                updated = updater_fn(data)
                f.seek(0)
                f.truncate()
                f.write(json.dumps(updated, indent=2, default=str))
                f.flush()
                return updated
            finally:
                if fcntl:
                    try:
                        fcntl.flock(f, fcntl.LOCK_UN)
                    except OSError:
                        pass

    @staticmethod
    def calculate_retention_score(
        completion_rate: float,
        avg_watch_time_sec: float,
        target_duration_sec: float = 60.0,
        hook_dropoff_rate: float = 0.15,
    ) -> float:
        """
        Calculates composite retention index (0-100).
        Weights:
        - 50% Completion Rate
        - 30% Relative Watch Duration
        - 20% Hook Survival Rate (1 - hook_dropoff)
        """
        comp_norm = min(max(completion_rate, 0.0), 1.0)
        watch_norm = min(max(avg_watch_time_sec / max(target_duration_sec, 1.0), 0.0), 1.0)
        hook_survival = min(max(1.0 - hook_dropoff_rate, 0.0), 1.0)

        score = (comp_norm * 50.0) + (watch_norm * 30.0) + (hook_survival * 20.0)
        return round(score, 2)

    def record_telemetry(
        self,
        job_id: str,
        views_count: int,
        completions_count: int,
        avg_watch_time_sec: float,
        hook_dropoff_rate: float,
        hook_style: str = "warning_symptom",
        scorm_mastery_rate: Optional[float] = None,
    ) -> ViewershipMetric:
        """Records telemetry for a completed video module."""
        completion_rate = completions_count / max(views_count, 1)
        score = self.calculate_retention_score(
            completion_rate=completion_rate,
            avg_watch_time_sec=avg_watch_time_sec,
            hook_dropoff_rate=hook_dropoff_rate,
        )

        metric = ViewershipMetric(
            job_id=job_id,
            views_count=views_count,
            completions_count=completions_count,
            avg_watch_time_sec=avg_watch_time_sec,
            hook_dropoff_rate=hook_dropoff_rate,
            hook_style=hook_style,
            scorm_mastery_rate=scorm_mastery_rate,
            retention_score=score,
        )

        def updater(db: Dict[str, Any]) -> Dict[str, Any]:
            db[job_id] = metric.model_dump()
            return db

        self._atomic_update(updater)
        return metric

    def get_summary_report(self) -> Dict[str, Any]:
        """Generates executive retention and performance report across all microlearning modules."""
        db = self._load_data()
        if not db:
            return {
                "total_modules_tracked": 0,
                "overall_retention_avg": 0.0,
                "best_hook_style": "N/A",
                "modules": [],
            }

        scores = [v.get("retention_score", 0.0) for v in db.values()]
        avg_score = round(sum(scores) / max(len(scores), 1), 2)

        # Evaluate best-performing hook style
        hook_scores: Dict[str, List[float]] = {}
        for item in db.values():
            style = item.get("hook_style", "default")
            hook_scores.setdefault(style, []).append(item.get("retention_score", 0.0))

        best_style = "warning_symptom"
        best_avg = 0.0
        for style, s_list in hook_scores.items():
            s_avg = sum(s_list) / len(s_list)
            if s_avg > best_avg:
                best_avg = s_avg
                best_style = style

        return {
            "total_modules_tracked": len(db),
            "overall_retention_avg": avg_score,
            "best_hook_style": best_style,
            "modules": list(db.values()),
        }

    def recommend_hook_improvements(self, persona_id: str) -> List[str]:
        """Generates actionable prompt optimization recommendations based on retention telemetry."""
        summary = self.get_summary_report()
        recommendations = [
            f"Front-load exact SAP Error Code / T-Code within the first 2.5 seconds to reduce hook drop-off.",
            f"Prioritize '{summary['best_hook_style']}' style hooks which currently average the highest retention.",
            f"Keep the Problem Context segment under 12 seconds to prevent mid-video drop-off.",
            f"Ensure call-to-action explicitly promises downloadable implementation artifacts (PDF/GitHub).",
        ]
        return recommendations
