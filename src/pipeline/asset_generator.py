"""Visual Asset & Code Snippet Generator for Microlearning B-Roll."""

import io
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageFont
import pygments
from pygments.formatters import ImageFormatter
from pygments.lexers import get_lexer_by_name, guess_lexer

from src.core.config import settings


class AssetGenerator:
    """Generates broadcast-quality visual graphics, title cards, and code snippets."""

    # Enterprise SAP Palette
    COLOR_BG_DARK = (18, 22, 28)
    COLOR_CARD_DARK = (28, 34, 44)
    COLOR_SAP_BLUE = (0, 112, 242)
    COLOR_ACCENT_GOLD = (240, 171, 0)
    COLOR_TEXT_WHITE = (255, 255, 255)
    COLOR_TEXT_MUTED = (160, 170, 185)

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or settings.OUTPUT_DIR

    def generate_title_card(
        self,
        topic: str,
        persona_name: str,
        persona_title: str,
        output_path: Path,
        dimensions: Tuple[int, int] = (1080, 608),
    ) -> Path:
        """
        Renders a high-contrast enterprise title / hook slide for the top 45% of a 4:5 LinkedIn video.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        width, height = dimensions
        img = Image.new("RGB", (width, height), color=self.COLOR_BG_DARK)
        draw = ImageDraw.Draw(img)

        # Gradient top accent bar (SAP Blue)
        draw.rectangle([(0, 0), (width, 8)], fill=self.COLOR_SAP_BLUE)

        # Container card with rounded outline
        draw.rounded_rectangle(
            [(40, 30), (width - 40, height - 30)],
            radius=16,
            fill=self.COLOR_CARD_DARK,
            outline=self.COLOR_SAP_BLUE,
            width=2,
        )

        # Category / Microlearning badge
        draw.rounded_rectangle(
            [(70, 55), (320, 95)],
            radius=6,
            fill=self.COLOR_SAP_BLUE,
        )
        draw.text((85, 65), "SAP MICROLEARNING", fill=self.COLOR_TEXT_WHITE)

        # Headline Topic
        # Word wrap basic text
        lines = []
        words = topic.split()
        current_line = []
        for w in words:
            if len(" ".join(current_line + [w])) <= 32:
                current_line.append(w)
            else:
                lines.append(" ".join(current_line))
                current_line = [w]
        if current_line:
            lines.append(" ".join(current_line))

        y_offset = 125
        for line in lines[:3]:
            draw.text((70, y_offset), line, fill=self.COLOR_TEXT_WHITE)
            y_offset += 40

        # Presenter byline
        draw.line([(70, height - 90), (width - 70, height - 90)], fill=(45, 55, 72), width=1)
        draw.text((70, height - 75), f"AI-SME: {persona_name}", fill=self.COLOR_ACCENT_GOLD)
        draw.text((70, height - 55), persona_title, fill=self.COLOR_TEXT_MUTED)

        img.save(output_path, "PNG")
        return output_path

    def generate_code_snippet(
        self,
        code_text: str,
        language: str = "sql",
        output_path: Optional[Path] = None,
        dimensions: Tuple[int, int] = (1080, 608),
    ) -> Path:
        """
        Renders a syntax-highlighted code block using Pygments ImageFormatter.
        """
        if output_path is None:
            output_path = self.output_dir / "code_snippet.png"
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            lexer = get_lexer_by_name(language)
        except Exception:
            lexer = guess_lexer(code_text)

        formatter = ImageFormatter(
            font_name="Courier",
            font_size=18,
            style="monokai",
            line_numbers=True,
            image_pad=30,
            background_color="#12161c",
        )
        png_bytes = pygments.highlight(code_text, lexer, formatter)

        code_img = Image.open(io.BytesIO(png_bytes))

        # Fit onto target canvas
        target_w, target_h = dimensions
        final_img = Image.new("RGB", (target_w, target_h), color=self.COLOR_BG_DARK)

        # Center or scale
        code_img.thumbnail((target_w - 60, target_h - 60))
        offset_x = (target_w - code_img.width) // 2
        offset_y = (target_h - code_img.height) // 2
        final_img.paste(code_img, (offset_x, offset_y))

        final_img.save(output_path, "PNG")
        return output_path

    def generate_solution_steps_card(
        self,
        steps: list,
        output_path: Path,
        dimensions: Tuple[int, int] = (1080, 608),
    ) -> Path:
        """
        Renders a 3-step action card summarizing the solution.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        width, height = dimensions
        img = Image.new("RGB", (width, height), color=self.COLOR_BG_DARK)
        draw = ImageDraw.Draw(img)

        # Top Accent
        draw.rectangle([(0, 0), (width, 8)], fill=self.COLOR_ACCENT_GOLD)

        # Title
        draw.text((50, 35), "⚡ 3-STEP SOLUTION OVERVIEW", fill=self.COLOR_ACCENT_GOLD)

        y = 90
        step_height = 140
        for i, step_text in enumerate(steps[:3], 1):
            draw.rounded_rectangle(
                [(50, y), (width - 50, y + step_height)],
                radius=10,
                fill=self.COLOR_CARD_DARK,
                outline=self.COLOR_SAP_BLUE,
                width=1,
            )
            # Step badge
            draw.rounded_rectangle(
                [(70, y + 15), (145, y + 50)],
                radius=6,
                fill=self.COLOR_SAP_BLUE,
            )
            draw.text((82, y + 25), f"STEP {i}", fill=self.COLOR_TEXT_WHITE)

            # Step text
            draw.text((165, y + 25), step_text[:75] + ("..." if len(step_text) > 75 else ""), fill=self.COLOR_TEXT_WHITE)
            y += step_height + 20

        img.save(output_path, "PNG")
        return output_path
