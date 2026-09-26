# Product & Engineering Roadmap

## Phase 1: Core Engine & Semi-Automated MVP (Current Milestone)
- [x] Project architecture design, data models, and persona definitions.
- [x] Script generation engine with SAP-specific prompt engineering (hook + problem + 3-step solution + CTA).
- [ ] Voice synthesis module (ElevenLabs integration with word-level timestamp extraction).
- [ ] Video compositor MVP (FFmpeg/MoviePy pipeline for PIP avatar + static screenshot + burned-in kinetic subtitles).
- [ ] End-to-end sample generation for 2 initial SAP topics.

## Phase 2: Dynamic Asset Capture & Advanced Layouts
- [ ] Playwright-based headless browser capture for SAP Fiori live demos.
- [ ] Automatic code snippet syntax highlighting generator (ABAP, CDS views, SQL).
- [ ] Multi-layout templates: Split-screen (4:5 LinkedIn), PIP overlay, and widescreen (16:9 LMS).
- [ ] Local fallback lip-sync using LivePortrait / SadTalker for zero-cost dev iteration.

## Phase 3: Distribution & Enterprise Integration
- [ ] LinkedIn API direct integration (auto-post with caption, hashtags, and first-comment link).
- [ ] SCORM / xAPI export packager for LMS integration (Cornerstone, SAP SuccessFactors LMS).
- [ ] Microsoft Teams / Slack webhook notifications for internal enterprise learning drops.

## Phase 4: Autonomous Content Operations
- [ ] Automated RSS / SAP Community scraper to identify trending issues and new SAP Release Notes.
- [ ] Analytics feedback loop: Track video watch-time and comments to auto-tune hook formulas.
- [ ] Multi-language localization (automatic dubbing and subtitle translation into German, Spanish, French, and Japanese).
