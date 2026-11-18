# Production Rules

These rules govern all content produced in this workspace. Every agent must follow them. They complement the studio rules in `AGENTS.md`.

---

## 1. Factual Accuracy

- **All factual claims must have a source.** No claim goes into a script without a URL + date stamp in the claim ledger (`research/<topic>/claims.md`).
- **GTA VI facts** — only claims backed by sources in `config/gta6-sources.md` may be presented as fact.
- **Confidence levels** — if a claim is from a secondary source (press article, fan wiki), label it "unverified" in the claim ledger and do not present it as confirmed fact in the video.
- **Corrections** — if a published video contains an error, pin a correction comment immediately and update the description.

---

## 2. Source Citation Standards

Every script file (`scripts/<topic>/script.md`) must include a **Sources** section at the end listing:

```
[Source Name] — URL — Accessed YYYY-MM-DD
```

The YouTube description of every published video must include at least one source link where relevant.

---

## 3. No Fabricated Gameplay Footage or Screenshots

- **Never fabricate gameplay footage.** We do not own GTA VI. Do not create or use fake in-game screenshots, AI-generated fake gameplay, or screen-recorded content from other creators without explicit permission.
- **Official press kit materials** (Rockstar-released trailers, screenshots, promotional images) may be used for commentary/tutorial purposes under Rockstar's Video Policy.
- **Third-party footage** requires individual rights clearance — run `copyright-checker` before including any such asset.
- All AI-generated scenes must be visually distinguishable from real gameplay (animation style, text overlay, etc.) to avoid misleading viewers.

---

## 4. AI Disclosure Requirements

Any video containing AI-generated content must include in its YouTube description:

> *"Graphics created with AI assistance. All facts sourced from official documentation."*

Additionally:
- AI voiceover: note "AI narration" if applicable.
- AI music: attribute the tool used (e.g., "Background music generated with [Tool]").
- AI-generated images/animations: label clearly in description.

---

## 5. Copyright Compliance Checklist

Before exporting any video, run `copyright-checker` and confirm:

- [ ] All gameplay footage is from official Rockstar press materials (or own gameplay once game is owned)
- [ ] Background music is from YouTube Audio Library or is fully licensed
- [ ] No third-party copyrighted images used without license
- [ ] No song clips, movie clips, or TV clips included
- [ ] AI-generated assets do not infringe third-party IP
- [ ] Clearance log updated: `assets/clearance-log.md`

---

## 6. Mandatory Voice Cloning (VoiceStudio Integration)

- **Creator Cloned Voice Standard:** All video voiceovers must use the channel owner's cloned voice profile stored at `assets/voices/creator_sample.wav`.
- **Synthesis Engine:** Routed through [VoiceStudio](https://github.com/debpalash/VoiceStudio) via `scripts/voice_studio_client.py` (`http://localhost:3900`).
- **Audio Presence & Energy:** Voiceovers must be punchy, dynamic, and fast-paced (~170–175 WPM). Never output flat, robotic, or quiet audio. Always apply dynamic compression and presence EQ.

---

## 7. Mandatory High-Retention Kinetic Motion Graphics

Every Short and video produced in this studio must comply with the **High-Retention Kinetic Framework** (and `skills/codex-shorts-blueprint/` v2.0.0 for 9:16 editorial explainers) to prevent audience drop-off:
- **Meaningful Visual Cadence (1.2–2.0s):** Never rely on static slides or decorative jitter. Every 1.2–2.0s must deliver a meaningful visual event (revealing crop, state change, comparison, mechanism demonstration, evidence highlight, or new shot) anchored inside coherent story worlds.
- **Mandatory Visual Proof & Authored Motion:** Include at least one mechanism/proof sequence (occlusion reveal, cross-section, matched comparison, or causal follow-through). Use authored velocity curves (not one default easing or perpetual zoom everywhere) and physically tied transform/shutter motion blur where fast motion occurs.
- **Three-Clock Separation (Paper-Collage Shorts):** Render intrinsic paper poses at `12 fps` while keeping camera, mattes, world placement, typography, and 2D screen-space captions at `30 fps`.
- **Strict Mobile Safe Zones (`1080×1920`):** Keep all critical text, figures, badges, and captions inside `x = 60–910`, `y = 200–1350`, hero artwork inside `x = 60–900`, `y = 220–1180`, and captions inside `x = 70–900`, `y = 1160–1340` (keep `x = 915–1080` right UI rail and `y > 1350` bottom UI zone clear except for background atmosphere).
- **Frameless Kinetic Captions:** Render 3–5 words per chunk (max 2 lines, `64–72px` starting size), breaking on spoken meaning with a stable baseline, single active-word emphasis color, no per-word scale pumping/bounce, and swept bounds verified inside the safe zone.
- **Clean Full-Bleed Canvas (Zero HUD/Template Chrome):** Never render top masthead bars, `CATEGORY // SUBTITLE` kickers, horizontal divider lines, `01 / 09` beat-counter rectangles, bottom source/disclaimer bars, timers, or progress bars on screen. Source citations and AI disclosures belong in `metadata.md` / `POST_CAPTION.txt`.
- **Pre-Render Plan Validation:** For editorial Shorts using `codex-shorts-blueprint`, author `premium_plan.json` and validate structure with `python3 skills/codex-shorts-blueprint/scripts/validate_plan.py <plan.json>` before full render.

---

## 8. 2026 YouTube Shorts Packaging & Upload Standards (Browse Features Funnel)

To bypass the standard Shorts Feed volatility and unlock 2x–5x total views from **YouTube Browse Features (Homepage)**:
1. **1-Frame Injected Thumbnail:** Every Short must include a high-contrast thumbnail card baked into the timeline for 1–2 frames at `t=0` or the tail.
2. **Mobile App Upload Mandate:** Upload via the YouTube Mobile App; use the preview pencil icon to scrub and select the custom frame (desktop does not support Shorts custom thumbnail frames).
3. **Curiosity & Reverse-Psychology Titles:** Titles must be under 55 characters, utilizing an end-payoff hook (*"What happens at the 25-second mark is wild"*) or reverse-psychology friction (*"Don't click the sound"*).
4. **Minimalist Metadata & Anti-Spam Tagging:** Strict maximum of **3–5 niche hashtags**. Never exceed 15 hashtags. Always select the accurate Video Category in YouTube Studio.
5. **UNLISTED Staging & Precision Timing:** Always stage uploads as **UNLISTED** (never Private) to allow full Content ID copyright checks and HD 1080p60 encoding to complete. Schedule or release **60 minutes prior to audience peak activity hours**.
6. **Related Video Funnel:** In YouTube Studio, always link a high-value long-form video or episodic Short in the **Related Video** slot to initiate channel binge loops.

---

## 9. Brand Consistency

| Element | Standard |
|---|---|
| **Font** | [Define channel font here] |
| **Primary Colors** | [Define brand palette here] |
| **Thumbnail Style** | Bold text, high contrast, consistent face/character framing |
| **Intro/Outro** | Standard bumper (max 5 sec intro, max 20 sec outro) |
| **Captions** | White text, dark background, bottom-third, minimum 48px equivalent |
| **Logo placement** | Bottom-right corner watermark for long-form |

---

## 10. Quality Gates Before Export

A video may only proceed to export after **all** gates pass:

| Gate | Who checks | Tool |
|---|---|---|
| Fact-check signoff | Human (channel owner) | Claim ledger review |
| Script review | Agent QA pass | `tutorial-scriptwriter` / `shorts-scriptwriter` |
| Storyboard approved | Agent review | `video-director` |
| AI scenes generated correctly | Agent verify | `ai-video-generator` |
| Video assembled correctly | Agent verify | `video-editor` |
| Copyright clearance | Agent + Human | `copyright-checker` |
| Quality review pass | Agent | `video-quality-reviewer` |
| Metadata prepared | Agent | `youtube-seo` |
| **Final human approval** | Human (channel owner) | Manual sign-off |

No autonomous upload. Human approval is required at fact-check, quality review, and before any publish action.

---

## 11. File Naming & Storage

```
research/<topic>/claims.md         — fact-checked claim ledger
scripts/<topic>/script.md          — final script
scripts/<topic>/storyboard.md      — scene breakdown
renders/<topic>/scene-N.mp4        — raw rendered scenes
renders/<topic>/narration.wav      — narration audio
renders/<topic>/final.mp4          — assembled video
renders/<topic>/final-captioned.mp4 — with captions burned in
exports/<topic>/YYYYMMDD-<slug>.mp4 — ready-to-upload file
exports/<topic>/metadata.md        — title, description, tags, chapters
assets/clearance-log.md            — copyright clearance record
```
