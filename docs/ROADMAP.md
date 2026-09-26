# Product & Engineering Roadmap

## Phase 1: Core Engine & Semi-Automated MVP (Completed)
- [x] Project architecture design, data models, and persona definitions.
- [x] Script generation engine with SAP-specific prompt engineering (hook + problem + 3-step solution + CTA).
- [x] Voice synthesis module (ElevenLabs integration with word-level timestamp extraction & phonetic normalization).
- [x] Video compositor MVP (Multi-layout FFmpeg pipeline, burns subtitles, generates render script).
- [x] End-to-end sample generation for initial SAP topics.

## Phase 2: Dynamic Asset Capture & Advanced Layouts (Completed)
- [x] Automatic code snippet syntax highlighting generator (ABAP, CDS views, SQL) & title cards.
- [x] Multi-layout templates: Split-screen (4:5 LinkedIn), PIP overlay (16:9), and vertical (9:16).
- [x] Pluggable state repository (Local JSON & Cloud Firestore support).
- [x] Playwright-based headless browser capture & high-fidelity simulation for SAP Fiori live demos.
- [x] Local fallback lip-sync & mock engine for zero-cost dev iteration.

## Phase 3: Distribution & Enterprise Integration (Completed)
- [x] SCORM 1.2 / 2004 export packager with HTML5 player for LMS integration (Cornerstone, SAP SuccessFactors LMS).
- [x] WebVTT accessibility closed captions (WCAG 2.1 AA compliant).
- [x] Microsoft Teams & Slack webhook notifications for internal enterprise learning drops.
- [x] LinkedIn API direct integration (auto-post with caption, hashtags, and first-comment link).

## Phase 4: Autonomous Content Operations (Completed)
- [x] Automated RSS / SAP Community scraper & curated high-impact catalog to identify trending issues and new SAP Release Notes.
- [x] Multi-language localization (script translation, multi-track WebVTT closed captions for German, Spanish, French, and Japanese in SCORM 1.2/2004).
- [x] Analytics feedback loop: Track video watch-time, drop-off curves, and auto-tune hook formulas.

## Phase 5: Security Hardening & Enterprise Scale (Completed)
- [x] XML entity expansion protection (defusedxml) for external RSS crawlers.
- [x] HTML/XSS sanitization in Fiori mock renderers.
- [x] POSIX/cross-platform file-locking on telemetry persistence (`fcntl.flock`).
- [x] Typed LinkedIn exception hierarchy (`LinkedInAuthError`, `LinkedInRateLimitError`, `LinkedInUploadError`).
- [x] Path traversal guards on `job_id` and `template_id` across local and cloud repositories.
- [x] 81 automated tests across 9 comprehensive test modules (100% pass rate).



