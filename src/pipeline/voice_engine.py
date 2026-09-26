"""Voice Synthesis Subsystem using ElevenLabs and phonetic normalization."""

import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple
from src.core.config import settings
from src.core.models import AudioTrack, WordTimestamp

logger = logging.getLogger(__name__)


class VoiceEngine:
    """Handles text-to-speech generation with enterprise phonetic normalization."""

    PHONETIC_RULES: List[Tuple[str, str]] = [
        (r"\bS/4HANA\b", "S four HAH-nah"),
        (r"\bS4HANA\b", "S four HAH-nah"),
        (r"\bSAP's\b", "S-A-P's"),
        (r"\bSAP\b", "S-A-P"),
        (r"\bBTP\b", "B-T-P"),
        (r"\bABAP\b", "AH-bop"),
        (r"\bFiori\b", "Fee-OR-ee"),
        (r"\bCDS\b", "C-D-S"),
        (r"\bRAP\b", "R-A-P"),
        (r"\bBAPI\b", "BAH-pee"),
        (r"\bRFC\b", "R-F-C"),
        (r"\bMIGO\b", "MEE-go"),
        (r"\bSPRO\b", "S-pro"),
    ]

    @classmethod
    def normalize_sap_phonetics(cls, text: str) -> str:
        """
        Normalizes SAP enterprise acronyms for natural text-to-speech pronunciation.
        Uses boundary-aware regex to ensure matches at sentence start, end, and around punctuation.
        """
        normalized = text
        for pattern, replacement in cls.PHONETIC_RULES:
            normalized = re.sub(pattern, replacement, normalized)
        return normalized

    def synthesize(
        self,
        text: str,
        voice_id: str,
        output_path: Path,
        dry_run: bool = True
    ) -> AudioTrack:
        """
        Synthesizes speech from text.
        In dry_run mode, creates mock timing data and placeholder audio file.
        In live mode, performs atomic streaming write and handles network errors.
        """
        if not text or not text.strip():
            raise ValueError("Cannot synthesize audio from empty text")

        normalized_text = self.normalize_sap_phonetics(text)
        words = normalized_text.split()

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if dry_run or not settings.ELEVENLABS_API_KEY:
            # Simulate word-level timestamps (~0.32 seconds per word)
            current_time = 0.0
            word_timestamps: List[WordTimestamp] = []
            for w in words:
                start = round(current_time, 2)
                end = round(current_time + 0.32, 2)
                word_timestamps.append(WordTimestamp(word=w, start_time=start, end_time=end))
                current_time = end

            total_duration = round(current_time, 2)

            # Generate a valid, playable WAV audio file for FFmpeg compatibility
            import wave
            with wave.open(str(output_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(22050)
                num_frames = int(total_duration * 22050)
                wf.writeframes(b"\x00\x00" * num_frames)

            # Write a placeholder metadata manifest
            meta_path = output_path.with_suffix(".json")
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump([wt.model_dump() for wt in word_timestamps], f, indent=2)

            return AudioTrack(
                audio_file_path=str(output_path),
                duration_seconds=total_duration,
                word_timestamps=word_timestamps
            )
        else:
            # Live ElevenLabs API call with atomic temp-file streaming
            from elevenlabs.client import ElevenLabs

            client = ElevenLabs(api_key=settings.ELEVENLABS_API_KEY)
            tmp_path = None
            try:
                audio_generator = client.text_to_speech.convert(
                    voice_id=voice_id,
                    text=normalized_text,
                    model_id="eleven_multilingual_v2"
                )
                with tempfile.NamedTemporaryFile(
                    dir=output_path.parent,
                    prefix=f"tmp_{output_path.stem}_",
                    suffix=".wav",
                    delete=False
                ) as tmp_file:
                    tmp_path = Path(tmp_file.name)
                    for chunk in audio_generator:
                        tmp_file.write(chunk)
                    tmp_file.flush()
                    os.fsync(tmp_file.fileno())

                # Atomic rename
                tmp_path.replace(output_path)
            except Exception as e:
                if tmp_path and tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)
                logger.error(f"ElevenLabs synthesis failed: {e}")
                raise RuntimeError(f"Voice synthesis failed for voice_id {voice_id}: {e}") from e

            return AudioTrack(
                audio_file_path=str(output_path),
                duration_seconds=round(len(words) * 0.35, 2),
                word_timestamps=[]
            )
