"""Data contracts and schemas for the Enterprise AI Microlearning Engine."""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class PersonaVisualProfile(BaseModel):
    avatar_seed_image: str
    gender: str
    apparent_age: str
    attire: str
    lighting: str


class PersonaVoiceProfile(BaseModel):
    provider: Literal["elevenlabs", "azure", "openai"] = "elevenlabs"
    voice_id: str
    stability: float = 0.65
    similarity_boost: float = 0.80
    speaking_rate: float = 1.0


class PersonaConfig(BaseModel):
    id: str
    name: str
    title: str
    tone: str
    target_audience: str
    visual_profile: PersonaVisualProfile
    voice_profile: PersonaVoiceProfile
    content_focus: List[str]
    sample_hooks: List[str]


class SectionType(str, Enum):
    HOOK = "hook"
    PROBLEM_CONTEXT = "problem_context"
    STEP_BY_STEP_SOLUTION = "step_by_step_solution"
    CALL_TO_ACTION = "call_to_action"


class ScriptSection(BaseModel):
    section_type: SectionType
    voiceover_text: str
    visual_cue: str
    estimated_duration_sec: float
    screen_asset_id: Optional[str] = None
    highlight_box: Optional[Dict[str, float]] = None  # e.g. {"x": 0.1, "y": 0.2, "w": 0.4, "h": 0.3}


class VideoScript(BaseModel):
    script_id: str
    topic: str
    persona_id: str
    duration_target_seconds: int = 60
    sections: List[ScriptSection]
    hashtags: List[str] = Field(default_factory=list)
    post_caption: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class WordTimestamp(BaseModel):
    word: str
    start_time: float
    end_time: float


class AudioTrack(BaseModel):
    audio_file_path: str
    duration_seconds: float
    word_timestamps: List[WordTimestamp] = Field(default_factory=list)


class VideoLayout(str, Enum):
    LINKEDIN_PORTRAIT_4_5 = "1080x1350"
    VERTICAL_9_16 = "1080x1920"
    WIDESCREEN_16_9 = "1920x1080"


class VideoRenderJob(BaseModel):
    job_id: str
    script: VideoScript
    layout: VideoLayout = VideoLayout.LINKEDIN_PORTRAIT_4_5
    fps: int = 30
    status: Literal["pending", "audio_generated", "avatar_rendered", "composited", "failed"] = "pending"
    output_file_path: Optional[str] = None
    subtitles_file_path: Optional[str] = None
    error_message: Optional[str] = None
