"""Ideation & Script Generation Subsystem for Enterprise Microlearning."""

import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests
import yaml

from src.core.config import settings
from src.core.models import PersonaConfig, ScriptSection, SectionType, VideoScript

logger = logging.getLogger(__name__)


class ScriptGenerator:
    """Generates structured, high-retention 60-second microlearning scripts."""

    def __init__(
        self,
        personas_dir: Optional[Path] = None,
        templates_dir: Optional[Path] = None,
    ):
        self.personas_dir = personas_dir or (settings.CONFIG_DIR / "personas")
        self.templates_dir = templates_dir or (settings.CONFIG_DIR / "templates")

    def load_persona(self, persona_id: str) -> PersonaConfig:
        """Loads a persona configuration by ID with path traversal protection."""
        if not persona_id or not re.match(r"^[a-zA-Z0-9_-]+$", persona_id):
            raise ValueError(f"Invalid persona_id: {persona_id!r}")

        file_path = self.personas_dir / f"{persona_id}.yaml"
        resolved_path = file_path.resolve()
        resolved_personas_dir = self.personas_dir.resolve()

        if not resolved_path.is_relative_to(resolved_personas_dir):
            raise ValueError(f"Path traversal detected for persona_id: {persona_id!r}")

        if not resolved_path.exists():
            raise FileNotFoundError(f"Persona config not found at: {file_path}")

        with open(resolved_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return PersonaConfig(**data)

    def load_template(self, template_id: str = "bite_size_tip_60s") -> Dict[str, Any]:
        """Loads a script structure template YAML with path traversal protection."""
        if not template_id or not re.match(r"^[a-zA-Z0-9_-]+$", template_id):
            raise ValueError(f"Invalid template_id: {template_id!r}")

        template_file = self.templates_dir / f"{template_id}.yaml"
        resolved_path = template_file.resolve()
        resolved_templates_dir = self.templates_dir.resolve()

        if not resolved_path.is_relative_to(resolved_templates_dir):
            raise ValueError(f"Path traversal detected for template_id: {template_id!r}")

        if not resolved_path.exists():
            return {}
        with open(resolved_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _generate_deterministic(
        self,
        persona: PersonaConfig,
        topic: str,
        specific_error_or_tcode: Optional[str] = None,
    ) -> VideoScript:
        """Synthesizes high-retention enterprise script based on persona specialty and topic."""
        script_id = f"script_{uuid.uuid4().hex}"
        error_ref = specific_error_or_tcode or topic

        if persona.id == "sap_architect":
            hook_text = (
                f"If your team is still building classic custom modifications for {topic} in S/4HANA, "
                f"stop immediately. You're creating an upgrade nightmare."
            )
            problem_text = (
                f"Modifying standard core objects violates Clean Core principles and breaks quarterly cloud upgrades. "
                f"Here is the modern SAP-approved architecture to implement instead."
            )
            solution_text = (
                f"Step 1: Check if Key-User Extensibility in Fiori covers your requirement with zero code. "
                f"Step 2: If custom logic is required, use On-Stack Developer Extensibility with ABAP Cloud and released APIs only. "
                f"Step 3: For complex third-party integrations, decouple your logic side-by-side on SAP BTP using Event Mesh."
            )
            cta_text = (
                f"Which Clean Core tier does your organization use most? "
                f"Save this post and drop your architectural questions in the comments."
            )
            hashtags = ["#SAP", "#S4HANA", "#CleanCore", "#BTP", "#EnterpriseArchitecture"]

        elif persona.id == "fiori_dev":
            hook_text = (
                f"Stop writing 300 lines of custom UI5 JavaScript for {topic} "
                f"when these single CDS annotations do it automatically."
            )
            problem_text = (
                f"Over-customized Fiori apps increase maintenance costs and cause performance bottlenecks. "
                f"Here is how to leverage standard SAP Fiori Elements metadata."
            )
            solution_text = (
                f"Step 1: Add the `@UI.lineItem` and `@UI.selectionField` annotations directly to your consumption CDS view. "
                f"Step 2: Define your value help association using `@Consumption.valueHelpDefinition`. "
                f"Step 3: Expose via the RAP Business Service and preview in ADT in under 60 seconds."
            )
            cta_text = (
                f"Want more ABAP Cloud and Fiori productivity hacks? "
                f"Follow Elena Rostova and let me know your favorite annotation below!"
            )
            hashtags = ["#SAP", "#Fiori", "#ABAP", "#RAP", "#FioriElements", "#DevShortcuts"]

        else:  # erp_functional_consultant or default
            hook_text = (
                f"Getting SAP error {error_ref} during a critical month-end transaction? "
                f"Stop asking the warehouse for a blind recount."
            )
            problem_text = (
                f"This error blocks inventory postings and causes financial reconciliation bottlenecks. "
                f"In 80% of cases, the stock is physically present—it's just locked."
            )
            solution_text = (
                f"Step 1: Jump into transaction MMBE to verify if units are tied up in Quality Inspection or Blocked stock. "
                f"Step 2: Check transaction MB5T to identify pending stock-in-transit between plants. "
                f"Step 3: Transfer cleared stock back to unrestricted using movement type 321 or 343 before posting."
            )
            cta_text = (
                f"Save this post for your next month-end close, "
                f"and drop your trickiest SAP error code in the comments!"
            )
            hashtags = ["#SAP", "#SAPMM", "#SupplyChain", "#Logistics", "#S4HANA"]

        sections = [
            ScriptSection(
                section_type=SectionType.HOOK,
                voiceover_text=hook_text,
                visual_cue="Direct eye contact, rapid punch-in zoom, urgent headline badge overlay.",
                estimated_duration_sec=3.5,
                highlight_box={"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.2},
            ),
            ScriptSection(
                section_type=SectionType.PROBLEM_CONTEXT,
                voiceover_text=problem_text,
                visual_cue="Cut to high-DPI SAP GUI / Fiori screencast with red attention box over error status.",
                estimated_duration_sec=11.5,
                screen_asset_id="sap_error_banner_01",
            ),
            ScriptSection(
                section_type=SectionType.STEP_BY_STEP_SOLUTION,
                voiceover_text=solution_text,
                visual_cue="Split screen: Top 45% screencast with step highlights; bottom 55% avatar presenter.",
                estimated_duration_sec=33.0,
                screen_asset_id="sap_solution_screencast_01",
            ),
            ScriptSection(
                section_type=SectionType.CALL_TO_ACTION,
                voiceover_text=cta_text,
                visual_cue="Avatar presenter with downloadable PDF checklist card and save icon.",
                estimated_duration_sec=12.0,
            ),
        ]

        post_caption = (
            f"🚨 Tackling {topic} in your SAP landscape?\n\n"
            f"Here is the rapid 60-second microlearning fix from {persona.name} ({persona.title}).\n\n"
            f"📌 Key Takeaways:\n"
            f"1. Rapid identification of root-cause blocks\n"
            f"2. Preventing downstream posting bottlenecks\n"
            f"3. Following official Clean Core and SAP best practices\n\n"
            f"💬 What's your project team's workaround for this? Share your experience below!\n\n"
            f"{' '.join(hashtags)}"
        )

        return VideoScript(
            script_id=script_id,
            topic=topic,
            persona_id=persona.id,
            duration_target_seconds=60,
            sections=sections,
            hashtags=hashtags,
            post_caption=post_caption,
        )

    def _generate_via_anthropic(self, persona: PersonaConfig, topic: str) -> Optional[VideoScript]:
        """Calls Anthropic Claude Messages API to generate a structured script."""
        system_prompt = (
            f"You are {persona.name}, {persona.title}. "
            f"Tone: {persona.tone}. Target audience: {persona.target_audience}. "
            f"You are an expert content creator specializing in 60-second high-density B2B LinkedIn microlearning videos. "
            f"Output strictly valid JSON with no markdown formatting or backticks."
        )

        prompt = (
            f"Create a 60-second enterprise microlearning video script for topic: '{topic}'.\n\n"
            f"Required JSON structure:\n"
            f"{{\n"
            f'  "sections": [\n'
            f'    {{"section_type": "hook", "voiceover_text": "...", "visual_cue": "...", "estimated_duration_sec": 3.5}},\n'
            f'    {{"section_type": "problem_context", "voiceover_text": "...", "visual_cue": "...", "estimated_duration_sec": 11.5}},\n'
            f'    {{"section_type": "step_by_step_solution", "voiceover_text": "...", "visual_cue": "...", "estimated_duration_sec": 33.0}},\n'
            f'    {{"section_type": "call_to_action", "voiceover_text": "...", "visual_cue": "...", "estimated_duration_sec": 12.0}}\n'
            f"  ],\n"
            f'  "hashtags": ["#SAP", "#S4HANA"],\n'
            f'  "post_caption": "..."\n'
            f"}}"
        )

        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 1500,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            content_text = data["content"][0]["text"].strip()
            # Clean possible markdown block markers
            cleaned = re.sub(r"^```(?:json)?\n?|\n?```$", "", content_text, flags=re.MULTILINE).strip()
            parsed = json.loads(cleaned)

            sections = [ScriptSection(**s) for s in parsed.get("sections", [])]
            return VideoScript(
                script_id=f"script_{uuid.uuid4().hex}",
                topic=topic,
                persona_id=persona.id,
                duration_target_seconds=60,
                sections=sections,
                hashtags=parsed.get("hashtags", ["#SAP", "#S4HANA"]),
                post_caption=parsed.get("post_caption", ""),
            )
        except Exception as e:
            logger.error(f"Anthropic script generation failed: {e}")
            return None

    def _generate_via_gemini(self, persona: PersonaConfig, topic: str) -> Optional[VideoScript]:
        """Calls Google Gemini API via REST to generate a structured script."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={settings.GOOGLE_API_KEY}"
        system_instruction = (
            f"You are {persona.name}, {persona.title}. Tone: {persona.tone}. Target audience: {persona.target_audience}. "
            f"Generate a 60-second enterprise microlearning script as JSON."
        )
        prompt = (
            f"Topic: {topic}. Return JSON with: sections (list of 4 sections with section_type: 'hook', "
            f"'problem_context', 'step_by_step_solution', 'call_to_action', voiceover_text, visual_cue, estimated_duration_sec), "
            f"hashtags, and post_caption."
        )

        try:
            resp = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "systemInstruction": {"parts": [{"text": system_instruction}]},
                    "generationConfig": {"responseMimeType": "application/json"},
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            content_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            parsed = json.loads(content_text)

            sections = [ScriptSection(**s) for s in parsed.get("sections", [])]
            return VideoScript(
                script_id=f"script_{uuid.uuid4().hex}",
                topic=topic,
                persona_id=persona.id,
                duration_target_seconds=60,
                sections=sections,
                hashtags=parsed.get("hashtags", ["#SAP", "#S4HANA"]),
                post_caption=parsed.get("post_caption", ""),
            )
        except Exception as e:
            logger.error(f"Gemini script generation failed: {e}")
            return None

    def generate_script(
        self,
        topic: str,
        persona_id: str,
        specific_error_or_tcode: Optional[str] = None,
        dry_run: bool = True,
    ) -> VideoScript:
        """
        Generates a 60-second video script adhering to the enterprise hook-solution model.
        In live mode (dry_run=False), queries Anthropic or Google LLM if API key is provided.
        Falls back to intelligent persona-aware deterministic generation.
        """
        persona = self.load_persona(persona_id)

        if not dry_run:
            if settings.LLM_PROVIDER == "anthropic" and settings.ANTHROPIC_API_KEY:
                llm_script = self._generate_via_anthropic(persona, topic)
                if llm_script:
                    return llm_script
            elif settings.LLM_PROVIDER == "google" and settings.GOOGLE_API_KEY:
                llm_script = self._generate_via_gemini(persona, topic)
                if llm_script:
                    return llm_script

        # Deterministic generation (dry-run or fallback)
        return self._generate_deterministic(persona, topic, specific_error_or_tcode)
