"""Voice Synthesis Subsystem using ElevenLabs and phonetic normalization."""

import json
from pathlib import Path
from typing import List, Optional
from src.core.config import settings
from src.core.models import AudioTrack, WordTimestamp


class VoiceEngine:
    """Handles text-to-speech generation with enterprise phonetic normalization."""

    @staticmethod
    def normalize_sap_phonetics(text: str) -> str:
        """
        Normalizes SAP enterprise acronyms for natural text-to-speech pronunciation.
        Prevents TTS from pronouncing SAP as a single word 'sap'.
        """
        replacements = {
            " SAP ": " S-A-P ",
            "SAP's": "S-A-P's",
            "S/4HANA": "S four HAH-nah",
            "S4HANA": "S four HAH-nah",
            "BTP": "B-T-P",
            "ABAP": "AH-bop",
            "Fiori": "Fee-OR-ee",
            "CDS": "C-D-S",
            "RAP": "R-A-P",
            "BAPI": "BAH-pee",
            "RFC": "R-F-C",
            "MIGO": "MEE-go",
            "SPRO": "S-pro",
        }
        normalized = text
        for term, phonetic in replacements.items():
            normalized = normalized.replace(term, phonetic)
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
        In dry_run mode (default when no API key is supplied), creates mock timing data.
        """
        normalized_text = self.normalize_sap_phonetics(text)
        words = normalized_text.split()
        
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
            # Live ElevenLabs API call (when API key is provided)
            from elevenlabs.client import ElevenLabs
            client = ElevenLabs(api_key=settings.ELEVENLABS_API_KEY)
            
            audio_generator = client.text_to_speech.convert(
                voice_id=voice_id,
                text=normalized_text,
                model_id="eleven_multilingual_v2"
            )
            with open(output_path, "wb") as f:
                for chunk in audio_generator:
                    f.write(chunk)
                    
            # Return AudioTrack with estimated or alignment timestamps
            return AudioTrack(
                audio_file_path=str(output_path),
                duration_seconds=len(words) * 0.35,
                word_timestamps=[]
            )
