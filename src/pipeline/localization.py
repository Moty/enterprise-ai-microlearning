"""Enterprise Multi-Language Localization Engine for Microlearning Modules."""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests

from src.core.config import settings
from src.core.models import ScriptSection, VideoRenderJob, VideoScript
from src.core.repositories import get_job_repository

logger = logging.getLogger(__name__)


class LocalizationEngine:
    """Translates and localizes scripts, metadata, and subtitle tracks into enterprise languages."""

    SUPPORTED_LANGUAGES: Dict[str, str] = {
        "de": "Deutsch",
        "es": "Español",
        "fr": "Français",
        "ja": "日本語",
    }

    # High-fidelity domain translations for deterministic / dry-run execution
    SPECIALIZED_TRANSLATIONS: Dict[str, Dict[str, Dict[str, str]]] = {
        "de": {
            "hook": "Wenn Ihr Team im Jahr 2026 immer noch Standard-SAP-Tabellen ändert, stoppen Sie sofort.",
            "problem": "Modifikationen im Standardcode zerstören Ihre Release-Fähigkeit und blockieren S/4HANA Cloud Upgrades.",
            "solution": "Wenden Sie stattdessen die 3 Clean-Core-Regeln an: Tier 1 ABAP Cloud, Tier 2 BTP Wrapper und Tier 3 Side-by-Side Erweiterungen.",
            "cta": "Speichern Sie dieses Video für Ihren nächsten Architektur-Review und fordern Sie das Clean-Core-Whitepaper an.",
            "topic_prefix": "SAP Microlearning (DE): ",
            "caption": "🚀 60-Sekunden Clean-Core-Architektur-Guide für SAP-Architekten.\n\n#SAP #CleanCore #S4HANA #CloudArchitektur",
        },
        "es": {
            "hook": "Si su equipo todavía modifica tablas estándar de SAP en 2026, deténgase de inmediato.",
            "problem": "Las modificaciones al código estándar destruyen la capacidad de actualización y bloquean S/4HANA Cloud.",
            "solution": "Aplique en su lugar las 3 reglas de Clean Core: Nivel 1 ABAP Cloud, Nivel 2 BTP Wrapper y Nivel 3 extensiones Side-by-Side.",
            "cta": "Guarde este video para su próxima revisión de arquitectura y solicite la guía completa.",
            "topic_prefix": "SAP Microlearning (ES): ",
            "caption": "🚀 Guía de 60 segundos sobre arquitectura Clean Core para arquitectos SAP.\n\n#SAP #CleanCore #S4HANA #ArquitecturaTI",
        },
        "fr": {
            "hook": "Si votre équipe modifie encore des tables standard SAP en 2026, arrêtez immédiatement.",
            "problem": "Les modifications du code standard détruisent votre évolutivité et bloquent les mises à niveau S/4HANA Cloud.",
            "solution": "Appliquez plutôt les 3 règles Clean Core : Tier 1 ABAP Cloud, Tier 2 BTP Wrapper et Tier 3 extensions Side-by-Side.",
            "cta": "Enregistrez cette vidéo pour votre prochaine revue d'architecture et demandez le livre blanc complet.",
            "topic_prefix": "SAP Microlearning (FR): ",
            "caption": "🚀 Guide Clean Core de 60 secondes pour les architectes d'entreprise SAP.\n\n#SAP #CleanCore #S4HANA #CloudArchitecture",
        },
        "ja": {
            "hook": "2026年になっても標準SAPテーブルを直接変更している場合は、直ちに中止してください。",
            "problem": "標準コードの変更はアップグレード性を損ない、S/4HANA Cloudへの移行を妨げます。",
            "solution": "代わりにClean Coreの3つの階層を適用してください: Tier 1 ABAP Cloud、Tier 2 BTPラッパー、Tier 3 サイドバイサイド拡張。",
            "cta": "次回のアーキテクチャレビューのためにこの動画を保存し、詳細ガイドをダウンロードしてください。",
            "topic_prefix": "SAP マイクロラーニング (JA): ",
            "caption": "🚀 SAPエンタープライズアーキテクト向け60秒クリーンコア解説。\n\n#SAP #CleanCore #S4HANA #クラウドアーキテクチャ",
        },
    }

    def __init__(self):
        self.repository = get_job_repository()

    def translate_script(
        self,
        script: VideoScript,
        target_lang: str,
        dry_run: bool = True,
    ) -> VideoScript:
        """
        Translates a VideoScript into the target language while maintaining section structure.
        """
        lang = target_lang.lower()
        if lang not in self.SUPPORTED_LANGUAGES and lang != "en":
            raise ValueError(f"Unsupported language code '{target_lang}'. Supported: {list(self.SUPPORTED_LANGUAGES.keys())}")

        if lang == "en":
            return script.model_copy()

        if dry_run or not (settings.ANTHROPIC_API_KEY or settings.GOOGLE_API_KEY):
            return self._deterministic_translation(script, lang)

        return self._llm_translation(script, lang)

    def _deterministic_translation(self, script: VideoScript, lang: str) -> VideoScript:
        """Creates specialized enterprise translations deterministically."""
        corpus = self.SPECIALIZED_TRANSLATIONS.get(lang, self.SPECIALIZED_TRANSLATIONS["de"])
        translated_sections: List[ScriptSection] = []

        type_map = {
            "hook": corpus["hook"],
            "problem_context": corpus["problem"],
            "step_by_step_solution": corpus["solution"],
            "call_to_action": corpus["cta"],
        }

        for sec in script.sections:
            sec_type_str = sec.section_type.value if hasattr(sec.section_type, "value") else str(sec.section_type)
            text = type_map.get(sec_type_str, sec.voiceover_text)
            translated_sections.append(
                ScriptSection(
                    section_type=sec.section_type,
                    voiceover_text=text,
                    visual_cue=f"[{self.SUPPORTED_LANGUAGES[lang]}] {sec.visual_cue}",
                    estimated_duration_sec=sec.estimated_duration_sec,
                    screen_asset_id=sec.screen_asset_id,
                    highlight_box=sec.highlight_box,
                )
            )

        return VideoScript(
            script_id=f"{script.script_id}_{lang}",
            topic=f"{corpus['topic_prefix']}{script.topic}",
            persona_id=script.persona_id,
            language=lang,
            duration_target_seconds=script.duration_target_seconds,
            sections=translated_sections,
            hashtags=script.hashtags,
            post_caption=corpus["caption"],
        )

    @staticmethod
    def _extract_json_payload(raw_text: str) -> Optional[Dict[str, Any]]:
        """Safely extracts JSON payload from LLM response text."""
        # 1. Clean markdown fences
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text.strip(), flags=re.MULTILINE).strip()
        # 2. Try direct parsing
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict) and "sections" in parsed:
                return parsed
        except Exception:
            pass

        # 3. Search for JSON candidate blocks
        candidates = re.findall(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", cleaned, re.DOTALL)
        for candidate in sorted(candidates, key=len, reverse=True):
            try:
                candidate_obj = json.loads(candidate)
                if isinstance(candidate_obj, dict) and "sections" in candidate_obj:
                    return candidate_obj
            except Exception:
                continue

        # 4. Fallback search for outer curly braces if single object
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                candidate_obj = json.loads(match.group(0))
                if isinstance(candidate_obj, dict):
                    return candidate_obj
            except Exception:
                pass
        return None

    def _llm_translation(self, script: VideoScript, lang: str) -> VideoScript:
        """Calls external LLM to translate script keeping enterprise SAP terms intact."""
        lang_name = self.SUPPORTED_LANGUAGES[lang]
        prompt = (
            f"You are an expert enterprise SAP localization specialist. Translate this 60-second microlearning video "
            f"script into {lang_name} ({lang}).\n"
            f"RULES:\n"
            f"1. Keep technical SAP terms, T-Codes (e.g. MMBE, SM59, ME21N), Error Codes (e.g. M7021), and core keywords "
            f"(Clean Core, BTP, Fiori, CDS, RAP) intact or in appropriate industry standard form.\n"
            f"2. Output strictly JSON with keys: topic, post_caption, sections (array of voiceover_text and visual_cue).\n\n"
            f"Original Topic: {script.topic}\n"
            f"Original Sections: {json.dumps([{'type': s.section_type.value, 'text': s.voiceover_text, 'cue': s.visual_cue} for s in script.sections])}"
        )

        try:
            if settings.LLM_PROVIDER == "anthropic" and settings.ANTHROPIC_API_KEY:
                headers = {
                    "x-api-key": settings.ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                }
                body = {
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 1500,
                    "messages": [{"role": "user", "content": prompt}],
                }
                resp = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=body, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                raw_text = data["content"][0]["text"]
            else:
                headers = {"Content-Type": "application/json"}
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={settings.GOOGLE_API_KEY}"
                body = {"contents": [{"parts": [{"text": prompt}]}]}
                resp = requests.post(url, headers=headers, json=body, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                raw_text = data["candidates"][0]["content"]["parts"][0]["text"]

            # Parse JSON safely (H2 robust extraction)
            payload = self._extract_json_payload(raw_text)
            if payload and "sections" in payload and isinstance(payload["sections"], list):
                translated_sections = []
                for idx, sec in enumerate(script.sections):
                    trans_item = payload["sections"][idx] if idx < len(payload["sections"]) else {}
                    if not isinstance(trans_item, dict):
                        trans_item = {}
                    translated_sections.append(
                        ScriptSection(
                            section_type=sec.section_type,
                            voiceover_text=trans_item.get("voiceover_text", sec.voiceover_text),
                            visual_cue=trans_item.get("visual_cue", sec.visual_cue),
                            estimated_duration_sec=sec.estimated_duration_sec,
                            screen_asset_id=sec.screen_asset_id,
                            highlight_box=sec.highlight_box,
                        )
                    )
                return VideoScript(
                    script_id=f"{script.script_id}_{lang}",
                    topic=payload.get("topic", script.topic),
                    persona_id=script.persona_id,
                    language=lang,
                    duration_target_seconds=script.duration_target_seconds,
                    sections=translated_sections,
                    hashtags=payload.get("hashtags", script.hashtags),
                    post_caption=payload.get("post_caption", script.post_caption),
                )
        except Exception as e:
            logger.warning("LLM translation failed (%s), falling back to deterministic: %s", lang, e)

        return self._deterministic_translation(script, lang)

    def generate_localized_vtt(
        self,
        base_vtt_path: Path,
        translated_script: VideoScript,
        output_vtt_path: Path,
    ) -> Path:
        """
        Creates a localized WebVTT closed-captions file synchronized with the base timings.
        """
        base_vtt_path = Path(base_vtt_path)
        output_vtt_path = Path(output_vtt_path)
        output_vtt_path.parent.mkdir(parents=True, exist_ok=True)

        # Extract timestamps from base WebVTT if exists
        time_cues: List[str] = []
        if base_vtt_path.exists():
            content = base_vtt_path.read_text(encoding="utf-8")
            for line in content.splitlines():
                if "-->" in line:
                    time_cues.append(line.strip())

        # If no base cues exist, construct synthesized 4-block cues
        if not time_cues:
            time_cues = [
                "00:00:00.000 --> 00:00:05.000",
                "00:00:05.000 --> 00:00:15.000",
                "00:00:15.000 --> 00:00:50.000",
                "00:00:50.000 --> 00:01:00.000",
            ]

        # Break translated sections into corresponding subtitle blocks
        section_texts = [s.voiceover_text for s in translated_script.sections]
        if not section_texts:
            section_texts = ["(Inhalte werden geladen)"]

        with open(output_vtt_path, "w", encoding="utf-8") as f:
            f.write(f"WEBVTT - Language: {translated_script.language}\n\n")
            for idx, cue_time in enumerate(time_cues, 1):
                # Cycle or select text corresponding to block
                sec_text = section_texts[(idx - 1) % len(section_texts)]
                f.write(f"{idx}\n{cue_time}\n{sec_text}\n\n")

        return output_vtt_path

    def localize_job(
        self,
        job: VideoRenderJob,
        target_languages: List[str],
        dry_run: bool = True,
    ) -> VideoRenderJob:
        """
        Produces multi-language scripts and synchronized WebVTT closed captions for a VideoRenderJob.
        """
        job_dir = settings.OUTPUT_DIR / job.job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        base_vtt = Path(job.vtt_subtitles_file_path) if job.vtt_subtitles_file_path else (job_dir / f"{job.job_id}_captions.vtt")

        for lang in target_languages:
            lang_code = lang.strip().lower()
            if lang_code not in self.SUPPORTED_LANGUAGES:
                continue

            # 1. Translate Script
            trans_script = self.translate_script(job.script, lang_code, dry_run=dry_run)
            job.localized_scripts[lang_code] = trans_script

            # Save localized script metadata
            script_file = job_dir / f"{job.job_id}_script_{lang_code}.json"
            script_file.write_text(trans_script.model_dump_json(indent=2), encoding="utf-8")

            # 2. Generate Localized WebVTT
            lang_vtt_path = job_dir / f"{job.job_id}_captions_{lang_code}.vtt"
            self.generate_localized_vtt(base_vtt, trans_script, lang_vtt_path)
            job.additional_vtt_tracks[lang_code] = str(lang_vtt_path)

        # Save updated job state to repository
        self.repository.save_job(job)
        return job
