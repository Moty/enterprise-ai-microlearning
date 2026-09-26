"""Headless Browser & Simulated Screen Recorder for SAP Fiori and B-Roll Demos."""

import html
import importlib.util
import logging
from pathlib import Path
from typing import Optional
from PIL import Image, ImageDraw, ImageFont

from src.core.config import settings

logger = logging.getLogger(__name__)


class ScreenRecorderEngine:
    """Records high-resolution SAP Fiori, WebGUI, and code execution screencasts for video B-roll."""

    # SAP Fiori Horizon / Dark Design Tokens
    COLOR_SHELL_BG = (22, 27, 34)
    COLOR_HEADER_BG = (13, 17, 23)
    COLOR_SAP_BLUE = (0, 112, 242)
    COLOR_SAP_ACCENT = (240, 171, 0)
    COLOR_TEXT_WHITE = (255, 255, 255)
    COLOR_TEXT_MUTED = (139, 148, 158)
    COLOR_CARD_BG = (28, 34, 44)
    COLOR_BORDER = (48, 54, 61)
    COLOR_ERROR_RED = (248, 81, 73)
    COLOR_SUCCESS_GREEN = (46, 160, 67)

    @classmethod
    def is_playwright_available(cls) -> bool:
        """Checks if playwright is installed in the current environment."""
        return importlib.util.find_spec("playwright") is not None

    def generate_fiori_html(
        self,
        topic: str,
        error_code: Optional[str] = None,
        persona_id: str = "fiori_dev",
    ) -> str:
        """Generates authentic SAP Fiori 3.0 (Horizon theme) HTML mock for headless rendering."""
        safe_topic = html.escape(topic)
        safe_error_code = html.escape(error_code) if error_code else None
        code_tag = f"[{safe_error_code}] " if safe_error_code else ""
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>SAP Fiori Launchpad - {safe_topic}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
      background: #12161c;
      color: #e6edf3;
      padding: 0;
      height: 100vh;
      display: flex;
      flex-direction: column;
    }}
    .shell-header {{
      background: #0d1117;
      height: 52px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 24px;
      border-bottom: 2px solid #0070F2;
    }}
    .shell-logo {{
      font-weight: 800;
      color: #0070F2;
      font-size: 18px;
      letter-spacing: 1px;
    }}
    .shell-title {{
      font-size: 14px;
      color: #8b949e;
    }}
    .page-content {{
      padding: 24px 32px;
      flex: 1;
    }}
    .smart-filterbar {{
      background: #1c222c;
      border: 1px solid #30363d;
      border-radius: 8px;
      padding: 18px 24px;
      margin-bottom: 24px;
      display: flex;
      gap: 20px;
      align-items: center;
    }}
    .filter-item {{
      display: flex;
      flex-direction: column;
      gap: 6px;
      font-size: 12px;
      color: #8b949e;
    }}
    .filter-input {{
      background: #12161c;
      border: 1px solid #30363d;
      padding: 8px 14px;
      border-radius: 4px;
      color: #fff;
      font-size: 13px;
    }}
    .btn-go {{
      background: #0070F2;
      color: #fff;
      border: none;
      padding: 9px 22px;
      border-radius: 4px;
      font-weight: 600;
      margin-left: auto;
      cursor: pointer;
    }}
    .table-card {{
      background: #1c222c;
      border: 1px solid #30363d;
      border-radius: 8px;
      overflow: hidden;
    }}
    .table-header {{
      padding: 16px 24px;
      border-bottom: 1px solid #30363d;
      font-size: 16px;
      font-weight: 600;
      color: #fff;
      display: flex;
      justify-content: space-between;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th {{
      text-align: left;
      padding: 12px 24px;
      background: #161b22;
      color: #8b949e;
      border-bottom: 1px solid #30363d;
    }}
    td {{
      padding: 14px 24px;
      border-bottom: 1px solid #21262d;
    }}
    .row-error {{
      background: rgba(248, 81, 73, 0.12);
      border-left: 4px solid #f85149;
    }}
    .badge-error {{
      background: #f85149;
      color: #fff;
      padding: 3px 8px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: bold;
    }}
    .badge-success {{
      background: #2ea043;
      color: #fff;
      padding: 3px 8px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: bold;
    }}
  </style>
</head>
<body>
  <div class="shell-header">
    <div class="shell-logo">SAP Fiori 3.0</div>
    <div class="shell-title">Manage Stock & Inventory Exceptions - S/4HANA Cloud</div>
    <div style="font-size: 12px; color: #F0AB00;">● System Online (Client 100)</div>
  </div>
  <div class="page-content">
    <div class="smart-filterbar">
      <div class="filter-item">
        <span>Plant (Werks)</span>
        <div class="filter-input">1010 (Walldorf Distribution)</div>
      </div>
      <div class="filter-item">
        <span>Storage Location</span>
        <div class="filter-input">0001 (Raw Materials)</div>
      </div>
      <div class="filter-item">
        <span>Exception Category</span>
        <div class="filter-input">{code_tag}Negative Stock Deficit</div>
      </div>
      <button class="btn-go">Go (Filter)</button>
    </div>

    <div class="table-card">
      <div class="table-header">
        <span>Material Exceptions List (3 items)</span>
        <span style="font-size: 12px; color: #8b949e;">Auto-Refresh: Active</span>
      </div>
      <table>
        <thead>
          <tr>
            <th>Material ID</th>
            <th>Description</th>
            <th>Unrestricted Stock</th>
            <th>Reserved Qty</th>
            <th>Exception Status</th>
          </tr>
        </thead>
        <tbody>
          <tr class="row-error">
            <td><strong>MAT-8842-X</strong></td>
            <td>Industrial Sensor Unit X9</td>
            <td style="color: #f85149; font-weight: bold;">0.000 KG</td>
            <td>150.000 KG</td>
            <td><span class="badge-error">{safe_error_code or 'ERROR'} Deficit Block</span></td>
          </tr>
          <tr>
            <td><strong>MAT-5510-B</strong></td>
            <td>Control Cable Shielded 50m</td>
            <td>420.000 M</td>
            <td>50.000 M</td>
            <td><span class="badge-success">Optimal</span></td>
          </tr>
          <tr>
            <td><strong>MAT-1099-A</strong></td>
            <td>Standard Housing Bracket</td>
            <td>1,200.000 PC</td>
            <td>200.000 PC</td>
            <td><span class="badge-success">Optimal</span></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</body>
</html>"""

    def capture_screen(
        self,
        html_content: str,
        output_path: Path,
        width: int = 1080,
        height: int = 608,
        dry_run: bool = True,
    ) -> Path:
        """
        Captures high-res screen graphic. Uses Playwright if installed and enabled,
        otherwise falls back to deterministic Pillow rendering.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not dry_run and self.is_playwright_available():
            try:
                from playwright.sync_api import sync_playwright

                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page(viewport={"width": width, "height": height})
                    page.set_content(html_content)
                    page.screenshot(path=str(output_path))
                    browser.close()
                logger.info("Captured Playwright headless screenshot to: %s", output_path)
                return output_path
            except Exception as e:
                logger.warning("Playwright capture failed: %s, falling back to PIL renderer.", e)

        # High-Fidelity PIL Simulation Fallback
        return self._render_simulated_fiori_image(output_path, width, height)

    def _render_simulated_fiori_image(self, output_path: Path, width: int, height: int) -> Path:
        """Renders an authentic, crisp SAP Fiori dark-mode interface using Pillow."""
        img = Image.new("RGB", (width, height), color=self.COLOR_SHELL_BG)
        draw = ImageDraw.Draw(img)

        # 1. Shell Header Bar
        header_height = 48
        draw.rectangle([(0, 0), (width, header_height)], fill=self.COLOR_HEADER_BG)
        draw.line([(0, header_height), (width, header_height)], fill=self.COLOR_SAP_BLUE, width=3)
        draw.text((24, 14), "SAP Fiori 3.0", fill=self.COLOR_SAP_BLUE)
        draw.text((160, 16), "Manage Stock & Inventory Exceptions - S/4HANA Cloud", fill=self.COLOR_TEXT_MUTED)
        draw.text((width - 240, 16), "● System Online (Client 100)", fill=self.COLOR_SAP_ACCENT)

        # 2. Smart FilterBar Card
        filter_y = header_height + 20
        filter_h = 75
        draw.rectangle([(24, filter_y), (width - 24, filter_y + filter_h)], fill=self.COLOR_CARD_BG, outline=self.COLOR_BORDER, width=1)
        draw.text((44, filter_y + 12), "Plant: 1010 (Walldorf Distribution)", fill=self.COLOR_TEXT_MUTED)
        draw.text((360, filter_y + 12), "Storage Location: 0001 (Raw Materials)", fill=self.COLOR_TEXT_MUTED)
        draw.text((680, filter_y + 12), "Exception: Negative Stock Deficit", fill=self.COLOR_TEXT_MUTED)

        # Button
        draw.rectangle([(width - 140, filter_y + 20), (width - 44, filter_y + 55)], fill=self.COLOR_SAP_BLUE)
        draw.text((width - 110, filter_y + 30), "Go", fill=self.COLOR_TEXT_WHITE)

        # 3. Exception Table
        tbl_y = filter_y + filter_h + 20
        tbl_h = height - tbl_y - 24
        draw.rectangle([(24, tbl_y), (width - 24, tbl_y + tbl_h)], fill=self.COLOR_CARD_BG, outline=self.COLOR_BORDER, width=1)

        # Table header row
        th_h = 40
        draw.rectangle([(24, tbl_y), (width - 24, tbl_y + th_h)], fill=self.COLOR_HEADER_BG)
        draw.text((44, tbl_y + 12), "Material ID", fill=self.COLOR_TEXT_MUTED)
        draw.text((240, tbl_y + 12), "Description", fill=self.COLOR_TEXT_MUTED)
        draw.text((540, tbl_y + 12), "Unrestricted Stock", fill=self.COLOR_TEXT_MUTED)
        draw.text((760, tbl_y + 12), "Reserved Qty", fill=self.COLOR_TEXT_MUTED)
        draw.text((920, tbl_y + 12), "Status", fill=self.COLOR_TEXT_MUTED)

        # Row 1 (Highlight Error Row)
        r1_y = tbl_y + th_h
        r1_h = 50
        draw.rectangle([(24, r1_y), (width - 24, r1_y + r1_h)], fill=(40, 24, 28))
        draw.rectangle([(24, r1_y), (28, r1_y + r1_h)], fill=self.COLOR_ERROR_RED)  # Left warning stripe
        draw.text((44, r1_y + 16), "MAT-8842-X", fill=self.COLOR_TEXT_WHITE)
        draw.text((240, r1_y + 16), "Industrial Sensor Unit X9", fill=self.COLOR_TEXT_WHITE)
        draw.text((540, r1_y + 16), "0.000 KG", fill=self.COLOR_ERROR_RED)
        draw.text((760, r1_y + 16), "150.000 KG", fill=self.COLOR_TEXT_WHITE)
        draw.rectangle([(915, r1_y + 12), (width - 44, r1_y + 38)], fill=self.COLOR_ERROR_RED)
        draw.text((925, r1_y + 17), "M7021 DEFICIT", fill=self.COLOR_TEXT_WHITE)

        # Row 2 (Success)
        r2_y = r1_y + r1_h
        r2_h = 50
        draw.text((44, r2_y + 16), "MAT-5510-B", fill=self.COLOR_TEXT_MUTED)
        draw.text((240, r2_y + 16), "Control Cable Shielded 50m", fill=self.COLOR_TEXT_MUTED)
        draw.text((540, r2_y + 16), "420.000 M", fill=self.COLOR_TEXT_MUTED)
        draw.text((760, r2_y + 16), "50.000 M", fill=self.COLOR_TEXT_MUTED)
        draw.rectangle([(915, r2_y + 12), (width - 60, r2_y + 38)], fill=self.COLOR_SUCCESS_GREEN)
        draw.text((925, r2_y + 17), "OPTIMAL", fill=self.COLOR_TEXT_WHITE)

        img.save(output_path, "PNG")
        return output_path

    def create_broll_asset(
        self,
        job_id: str,
        topic: str,
        error_code: Optional[str] = None,
        output_path: Optional[Path] = None,
        dry_run: bool = True,
    ) -> Path:
        """Orchestrates generating the complete Fiori demo screen asset."""
        target_path = output_path or (settings.OUTPUT_DIR / job_id / "screen_overlay.png")
        html_code = self.generate_fiori_html(topic=topic, error_code=error_code)
        return self.capture_screen(html_code, target_path, dry_run=dry_run)
