# Technical Stack & Infrastructure Specification

## 1. Engine Architecture & Component Stack

| Layer | Recommended Component | Alternative | Rationale |
| :--- | :--- | :--- | :--- |
| **Orchestration & Core** | **Python 3.11+ / Pydantic v2** | Node.js / TypeScript | Clean data modeling, rich ecosystem for media automation, and strong native API SDKs. |
| **CLI & Interface** | **Typer / Rich** | Click | Beautiful terminal progress bars, table outputs, and interactive debugging prompts. |
| **Ideation & LLM** | **Claude 3.5 Sonnet / Gemini 1.5 Pro** | GPT-4o | Superior reasoning on complex SAP technical concepts and natural script cadence. |
| **Voice Synthesis (TTS)** | **ElevenLabs API** | Azure Neural TTS | Uncanny vocal inflection, pacing controls, and exact word-level timestamp generation. |
| **Avatar & Lip-Sync** | **Hedra Character-2 / LivePortrait** | HeyGen Video API / Kling | Fast rendering, strong facial expressiveness, and cost-effective batch generation. |
| **Video Compositor** | **MoviePy / FFmpeg** | Remotion (React) | Headless video manipulation, multi-layer alpha blending, PIP masks, and automated subtitle burning. |
| **Automated Screen Asset Capture** | **Playwright (Python)** | Selenium | Headless capture of live SAP Fiori web interfaces and high-resolution UI screenshots. |
| **Code Syntax Rendering** | **Pygments / Carbon CLI** | Shiki | High-contrast enterprise dark-mode code graphics for ABAP, SQL, and JSON. |
| **Publishing & Distribution** | **LinkedIn API v2 & YouTube Data API** | Buffer / Hootsuite API | Native OAuth2 video uploads with custom thumbnail and post captions. |

---

## 2. Audio-Visual Pipeline Specifications

### Video Specs
* **Aspect Ratios:**
  * LinkedIn Feed: `1080x1350` (4:5 optimal vertical real estate) or `1080x1920` (9:16).
  * Enterprise LMS / YouTube: `1920x1080` (16:9 widescreen).
* **Frame Rate:** 30 fps (H.264 / AAC).
* **Bitrate:** 4,000–6,000 kbps for crisp text readability on mobile devices.

### Subtitle & Caption Specs
* **Font:** Inter Bold or Poppins Semi-Bold.
* **Highlight Color:** `#0070F2` (SAP Blue) or `#F0AB00` (Accent Gold).
* **Word Grouping:** 2 to 4 words per frame, synchronized with ElevenLabs word timestamps.
