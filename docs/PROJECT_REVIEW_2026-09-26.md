# Deep project review — 26 September 2026

Reviewed revision: `8bcca86`. Scope: Python CLI and pipeline, persistence, FastAPI review API, Firebase dashboard and rules, publishers, media generation, localization, packaging, analytics, and the existing test suite.

**Assessment: a working prototype with production-blocking security and correctness defects.** The modular pipeline and typed data contracts provide a useful foundation, but the current approval portal cannot reliably establish who approved which rendered asset. Several live paths return placeholders or success after failure. These gaps matter more than the passing unit-test count.

The review did not change application code, cloud rules, or deployed services, and did not publish messages or invoke paid generation services. Cloud exposure findings below describe the checked-in configuration; the deployed Firebase rules and live database were not inspected. Local security probes used temporary sentinel data. Browser probes ran in local Chromium with all browser network traffic blocked.

**Validation performed**

- Existing suite: **100 passed, 1 deprecation warning, 6.96 seconds**, using Python 3.14 in the existing virtual environment. Provider credentials were cleared in memory, socket connections blocked, and the configured output directory redirected to temporary storage. Some existing tests choose their own paths.
- Actual FFmpeg smoke renders: all three layouts (`1080x1350`, `1080x1920`, `1920x1080`) produced nonempty MP4 files. These short fixtures used silent audio and generated backgrounds; they do not validate speech, lip sync, or instructional quality.
- Targeted offline API/pipeline probes confirmed failed-job approval, notification failure, arbitrary manifest-path file serving, missing Firestore ordering field, missing live avatar files, incorrect translation fallback, cyclic subtitle text, silent live-mode fallback, misleading CLI success, approval-state conflation, lost updates, and empty live TTS captions.
- Local Chromium confirmed stored script execution, identical video selection for unrelated jobs, and SCORM completion reset on reopening.
- A wheel built successfully from a clean temporary copy of the committed revision, but importing its advertised entry module outside the checkout failed with `ModuleNotFoundError: No module named 'main'`.
- Provider model retirement dates and Firestore ordering semantics were checked against official documentation. No live provider request was needed.

**Findings, in repair priority order**

1. **[P1] Restrict database access and authenticate the review API.**

   [firestore.rules](/Users/moty/.gemini/antigravity/scratch/enterprise-ai-microlearning/firestore.rules:5) grants unconditional reads and writes to jobs and analytics. Deployed as written, anonymous clients can read, overwrite, or delete documents and forge approvals. Separately, [the FastAPI approval endpoint](/Users/moty/.gemini/antigravity/scratch/enterprise-ai-microlearning/src/dashboard/app.py:107) has no authentication or authorization dependency; the generation/localization endpoints also lack one. An unauthenticated temporary-data request successfully changed a failed job to `completed`. Network exposure of that API depends on its bind/proxy configuration; the CLI defaults to loopback.

   Require authenticated reviewer roles, restrict client-editable fields, validate document schemas, and make publication a server-authorized operation. Add anonymous-denial and unauthorized-transition tests. Confirm and correct deployed rules before using this with internal content.

2. **[P1] Remove stored XSS from the hosted dashboard.**

   [public/index.html](/Users/moty/.gemini/antigravity/scratch/enterprise-ai-microlearning/public/index.html:605) interpolates `job_id`, `layout`, and `status` directly into `innerHTML` and inline event handlers. Other modal fields are also unescaped. Firestore data bypasses Python model validation. A local browser fixture with an image/error-handler payload in `status` executed JavaScript simply by rendering the job table. Combined with finding 1, an anonymous database writer can poison a reviewer's dashboard.

   Build DOM nodes with `textContent`, bind handlers with `addEventListener`, validate document fields, and add a restrictive CSP as defense in depth. Escape-for-HTML alone does not safely handle the inline JavaScript contexts.

3. **[P1] Confine media file reads to the job's approved artifact directory.**

   [src/dashboard/app.py](/Users/moty/.gemini/antigravity/scratch/enterprise-ai-microlearning/src/dashboard/app.py:71) serves any nonempty file named by `job.output_file_path`, without resolving and checking it against the configured media root. A manifest pointing to a temporary text sentinel outside the output directory was returned by the video endpoint with HTTP 200. No real secret was read. Exploitation requires control of the stored manifest and access to this API; the open Firestore rules supply manifest control when that backend is used.

   Treat stored paths as untrusted. Prefer server-generated artifact identifiers, check resolved paths and symlinks against the job directory, and verify the media type. Apply the same boundary to subtitle/package inputs that are copied from manifest paths.

4. **[P1] Replace retired LLM model IDs and stop silently substituting canned content.**

   [ideation.py](/Users/moty/.gemini/antigravity/scratch/enterprise-ai-microlearning/src/pipeline/ideation.py:219) hard-codes `claude-3-5-sonnet-20241022`; its Gemini path uses `gemini-2.0-flash` at line 249. Localization repeats both IDs. Anthropic lists the former as retired on **28 October 2025**; Google lists the latter as shut down on **1 June 2026**. These dates precede this review. Errors are caught and replaced with deterministic scripts/translations, allowing a live run to appear successful with unrelated stock content.

   Configure supported model IDs centrally and surface provider/model failures as failed or explicitly degraded jobs. Require an explicit simulation mode for canned content. Sources: [Anthropic model deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations), [Google Gemini deprecations](https://ai.google.dev/gemini-api/docs/deprecations).

5. **[P1] Separate successful rendering, human approval, and publication states.**

   [compositor.py](/Users/moty/.gemini/antigravity/scratch/enterprise-ai-microlearning/src/pipeline/compositor.py:332) sets `completed` immediately after rendering, while both dashboards interpret that state as approved. [approve_job](/Users/moty/.gemini/antigravity/scratch/enterprise-ai-microlearning/src/dashboard/app.py:115) sets the same state before publishing, without checking prior status, media validity, reviewer identity, or a content revision. Probes confirmed both an unreviewed render becoming `completed` and a failed job being approved. Publishing results are returned but not durably recorded, leaving retries vulnerable to duplicate external posts.

   Introduce distinct render, approval, and distribution states. Record reviewer identity, time, approved content/artifact hash, and publication identifiers. Reject approval of failed/missing artifacts and use idempotency for publishing. Editing/localizing approved content should have an explicit reapproval policy.

6. **[P1] Bind hosted review actions to the selected job's actual artifacts.**

   [public/index.html](/Users/moty/.gemini/antigravity/scratch/enterprise-ai-microlearning/public/index.html:646) chooses between two fixed videos by job-ID prefix, and [downloadScorm](/Users/moty/.gemini/antigravity/scratch/enterprise-ai-microlearning/public/index.html:721) always downloads the same ZIP. Chromium confirmed two unrelated jobs show the identical video URL. A reviewer can therefore approve a script while watching a different lesson, then distribute the wrong SCORM package. Localization and ticket synthesis buttons only show alerts; hosted approval only writes a status field.

   Store and resolve versioned media/package URLs per job and connect actions to real backend operations. Unavailable functionality should be disabled or clearly marked as a demo. Keep the hosted and local dashboards on one shared frontend contract.

7. **[P1] Align the Firestore query with the serialized timestamp field.**

   [public/index.html](/Users/moty/.gemini/antigravity/scratch/enterprise-ai-microlearning/public/index.html:533) orders by root `created_at`, but [the repository](/Users/moty/.gemini/antigravity/scratch/enterprise-ai-microlearning/src/core/repositories.py:199) serializes the model unchanged, whose timestamp is `script.created_at`. A captured repository write confirmed the root field is absent. Firestore ordering excludes documents missing the ordered field, so normal pipeline jobs disappear from this dashboard query and the UI falls back toward demo data. Both dashboards also display the wrong date field.

   Query `script.created_at` or introduce and migrate a consistent root timestamp. Test the actual persisted document shape against the frontend query. [Firebase documents this exclusion behavior](https://firebase.google.com/docs/firestore/query-data/order-limit-data).

8. **[P1] Propagate render failure and reject empty SCORM media.**

   [main.py](/Users/moty/.gemini/antigravity/scratch/enterprise-ai-microlearning/main.py:142) reports rendering success and continues packaging without checking the returned job status. [ScormPackager.package](/Users/moty/.gemini/antigravity/scratch/enterprise-ai-microlearning/src/publishers/scorm_packager.py:327) creates an empty `video.mp4` when the source is missing. Batch production similarly appends failed results to `completed_jobs`.

   With FFmpeg discovery deliberately disabled in a temporary fixture, `generate --dry-run` exited **0**, printed that the pipeline completed successfully, persisted `failed`, and produced a ZIP containing a **0-byte video**. Reject missing/empty/unparseable media before packaging, stop downstream production on failure, and return nonzero CLI status. Keep simulation packages unmistakably separate from distributable output.

9. **[P1] Do not use unrelated Clean Core text as a translation fallback.**

   [localization.py](/Users/moty/.gemini/antigravity/scratch/enterprise-ai-microlearning/src/pipeline/localization.py:87) replaces every input section with a fixed Clean Core corpus. This occurs in dry-run mode, when no LLM key is available, and after translation errors. An inventory/M7021 fixture lost its `MMBE` instructions and gained Clean Core architecture instructions under the original topic. The local dashboard always requests dry-run localization but announces completion and regenerates the package.

   Preserve the original lesson on translation failure, expose failure explicitly, and prohibit simulated translations from becoming production caption tracks. Add source-specific translation checks, including preservation of error codes and transaction names.

10. **[P2] Align translated captions by section or utterance, not round-robin.**

    [localization.py](/Users/moty/.gemini/antigravity/scratch/enterprise-ai-microlearning/src/pipeline/localization.py:265) cycles whole translated sections across each base cue. Base captions are four-word blocks, so a four-section script is repeatedly displayed from the beginning rather than following the spoken content. An eight-cue fixture repeated the hook twice. Entire paragraphs also appear for very short cue durations.

    Retain section-to-audio boundaries and split translated text into readable cues within those intervals. Test semantic sequence, duration, readability, and coverage rather than only file existence and language headers.

11. **[P1] Fail explicitly for unimplemented live avatar providers.**

    [HedraAvatarProvider](/Users/moty/.gemini/antigravity/scratch/enterprise-ai-microlearning/src/pipeline/avatar_engine.py:174) and [HeyGenAvatarProvider](/Users/moty/.gemini/antigravity/scratch/enterprise-ai-microlearning/src/pipeline/avatar_engine.py:216) return the requested output path without making a request or creating a file when a key is present and `dry_run=False`. Both behaviors were reproduced with fake credentials and blocked networking. The compositor substitutes a solid background for absent avatar input, masking the integration failure. The configured `liveportrait` provider also resolves to the mock adapter.

    Implement and contract-test each advertised adapter or reject unsupported providers. Require an actual validated video on success and record whether an artifact is simulated. Seedance's request also sends local filesystem path strings rather than uploading asset contents; its live contract needs separate verification.

12. **[P1] Produce alignment data for live speech and validate live-mode prerequisites.**

    [voice_engine.py](/Users/moty/.gemini/antigravity/scratch/enterprise-ai-microlearning/src/pipeline/voice_engine.py:130) returns no word timestamps after successful live TTS and estimates duration from word count. The compositor consequently writes empty captions. An injected SDK response containing a one-second WAV produced **zero timestamps**, an **empty SRT**, and a reported duration of **3.5 seconds**. Missing credentials take another silent-success path: live mode produces a silent WAV without indicating degradation on `AudioTrack`.

    Use measured audio duration and provider alignment or a forced-alignment step. Fail live mode when required credentials/dependencies are missing. Preserve original display text separately from pronunciation-normalized speech. This is necessary before claiming live accessibility captions.

13. **[P2] Fix the dashboard notification dispatch method.**

    [src/dashboard/app.py](/Users/moty/.gemini/antigravity/scratch/enterprise-ai-microlearning/src/dashboard/app.py:134) calls `WebhookPublisher.send_notification`, but the class implements only `send_teams` and `send_slack`. Requesting a Teams notification returned **HTTP 500**, while the job was already persisted as `completed`. No notification was sent. The API request model also has no destination webhook configuration.

    Add validated channel dispatch and server-side destination configuration, with separate distribution status/error handling. Add endpoint tests for both channels and delivery failure.

14. **[P1] Make the built package installable and declare its runtime dependencies.**

    [pyproject.toml](/Users/moty/.gemini/antigravity/scratch/enterprise-ai-microlearning/pyproject.toml:24) advertises `microlearning = main:app`, but the built wheel omits `main.py`, the `src` package namespace expected by imports, and persona/template configs. Setuptools instead packages `core`, `pipeline`, `dashboard`, and `publishers` at the wheel root. Isolated entry-module import failed. The project dependency list also omits unconditional imports such as Pillow, Pygments, and defusedxml. The live ElevenLabs SDK appears in neither dependency file and is absent from the inspected virtual environment.

    Configure explicit package discovery, move the entry point into the package, include resources, and use a single authoritative dependency list with extras where appropriate. Validate a wheel installed in a fresh environment from outside the checkout; a successful wheel build is insufficient.

15. **[P2] Prevent stale whole-job saves from overwriting concurrent changes.**

    [LocalJsonJobRepository.save_job](/Users/moty/.gemini/antigravity/scratch/enterprise-ai-microlearning/src/core/repositories.py:67) rewrites the manifest without locking, atomic replacement, or revision checks. Approval and localization both read a job, mutate it, and save the entire object. A deterministic two-reader probe lost the first reader's approval metadata after the second reader saved a caption update. Firestore's full-model `set(..., merge=True)` also overwrites overlapping stale fields; it is not optimistic concurrency control.

    Use revision-checked updates/transactions and field-specific state mutations. For local persistence, protect the complete read-modify-write operation and atomically replace manifests. Add concurrent approval/localization tests.

16. **[P2] Show unavailable analytics instead of fabricated success metrics.**

    [the local dashboard](/Users/moty/.gemini/antigravity/scratch/enterprise-ai-microlearning/src/dashboard/app.py:591) replaces a valid zero score or request failure with `84.5 %`. [The hosted dashboard](/Users/moty/.gemini/antigravity/scratch/enterprise-ai-microlearning/public/index.html:377) hard-codes that score and also hard-codes monthly savings and ticket clusters, regardless of backend state. These displays cannot support operational decisions.

    Distinguish unavailable, zero, and explicitly labeled sample data. Wire metrics to their real source and display the observation period. Keep a retention index distinct from a measured percentage.

17. **[P2] Preserve LMS completion when learners reopen a SCORM lesson.**

    [scorm_packager.py](/Users/moty/.gemini/antigravity/scratch/enterprise-ai-microlearning/src/publishers/scorm_packager.py:242) unconditionally sets `cmi.core.lesson_status` to `incomplete` at startup. A browser fixture with an LMS reporting an already completed lesson observed that downgrade immediately. Closing the reopened lesson before the completion trigger can erase completion in an LMS that accepts that write. The current completion trigger also treats seeking beyond 85% as viewing that much content.

    Read existing LMS state, preserve completed/passed results, and implement the intended viewing/assessment policy. Check SCORM API return values and validate against a real LMS sandbox before claiming interoperability. The generated package is SCORM 1.2; there is no selectable SCORM 2004 implementation despite the documentation claims.

18. **[P2] Derive monthly ticket projections from a declared observation period.**

    [ticket_deflection.py](/Users/moty/.gemini/antigravity/scratch/enterprise-ai-microlearning/src/pipeline/ticket_deflection.py:241) describes the input as approximately one week but multiplies ticket count by **12** to estimate a month, then assumes **70%** deflection. Ticket timestamps and export duration are ignored. Identical counts from one day or a full year therefore produce identical monthly savings projections.

    Require an observation window and explicit deflection assumptions. Separate measured ticket volume from scenario estimates, deduplicate ticket IDs, and test the calculation across different periods. Avoid presenting the estimates as measured savings.

**Architecture and test implications**

The most important architectural change is a server-owned job lifecycle that binds authenticated approvals to immutable artifacts. The current duplicated orchestration in CLI generation, batch production, and ticket deflection produces inconsistent failure handling. A shared production service should validate each stage's outputs and persist transitions. Longer rendering/localization work should have durable job ownership, timeouts, and recoverable status instead of relying entirely on a synchronous HTTP request.

The two separately maintained dashboards have materially different behavior. Sharing one frontend and API/schema contract would address the timestamp mismatch and reduce the risk of demo-only actions being presented as operational. Keep cloud artifacts in a deliberately managed artifact store with per-job references and access policy; local machine paths are not usable hosted media URLs.

The existing tests provide useful coverage of schemas, deterministic outputs, path-ID validation, XML entity rejection, formatting, and mocked publishing errors. Their green result does not verify Firebase authorization, browser output encoding, installed-package behavior, live provider adapters, media-to-job identity, approval transitions, or real caption alignment. No CI workflow or dependency lockfile is tracked. The roadmap marks several of these capabilities complete prematurely, including SCORM 2004, word-level live speech timing, cross-platform file locking, and automatic hook tuning.

Suggested repair sequence:

1. Close authorization and file/HTML trust-boundary gaps; independently inspect deployed rules.
2. Correct approval state, per-job artifact identity, and failure propagation; reject empty distribution packages.
3. Repair packaging and provider prerequisites; configure supported models and distinguish simulations from real artifacts.
4. Implement valid live alignment/localization and missing provider actions.
5. Add focused regression tests for the confirmed probes, then test a full production-like workflow in an isolated backend/LMS sandbox. Add CI, install-from-wheel checks, browser checks, and Firebase rules tests.

**Evidence artifacts**

- [Offline reproduction script](/Users/moty/.gemini/antigravity/scratch/enterprise-ai-microlearning/output/project-review/probes.py)
- [API and pipeline probe results](/Users/moty/.gemini/antigravity/scratch/enterprise-ai-microlearning/output/project-review/probes.jsonl)
- [Browser reproduction script](/Users/moty/.gemini/antigravity/scratch/enterprise-ai-microlearning/output/project-review/browser_probes.py)
- [Browser results](/Users/moty/.gemini/antigravity/scratch/enterprise-ai-microlearning/output/project-review/browser-probes.jsonl)
- [FFmpeg smoke results](/Users/moty/.gemini/antigravity/scratch/enterprise-ai-microlearning/output/project-review/render-smoke.json)
- [Wheel build log](/Users/moty/.gemini/antigravity/scratch/enterprise-ai-microlearning/output/project-review/build.log), [wheel contents](/Users/moty/.gemini/antigravity/scratch/enterprise-ai-microlearning/output/project-review/wheel-inspection.json), [entry-point import failure](/Users/moty/.gemini/antigravity/scratch/enterprise-ai-microlearning/output/project-review/wheel-entry.log)

Evidence files are under the existing ignored `output/` directory. The report is the only added non-ignored project file. Production deployment state, live provider credentials/permissions, actual LinkedIn posting, real speech/lip sync, and LMS interoperability remain unverified.
