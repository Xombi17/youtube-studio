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

Every Short and video produced in this studio must comply with the **High-Retention Kinetic Framework** to prevent audience drop-off:
- **The 2.5-Second Rule:** Zero static frames. Every beat must contain continuous micro-motion.
- **Dynamic Ken Burns Zooms:** Every graphic card/scene must continuously scale (1.0x → 1.08x) or pan across its duration.
- **Visual Punctuation on Cuts:** Every transition must trigger a visual effect—screen flicker, white flash cut, glowing edge flare, or camera punch-in.
- **High-Contrast Styling:** Dark backgrounds (`#0b1420`), GTA sunset orange (`#f47750`), coral alerts (`#e96643`), and glowing neon accent badges.
- **Kinetic Word-by-Word Captions:** Captions must emphasize key stress words in contrasting accent colors to keep eyes locked on screen.

---

## 8. Brand Consistency

| Element | Standard |
|---|---|
| **Font** | [Define channel font here] |
| **Primary Colors** | [Define brand palette here] |
| **Thumbnail Style** | Bold text, high contrast, consistent face/character framing |
| **Intro/Outro** | Standard bumper (max 5 sec intro, max 20 sec outro) |
| **Captions** | White text, dark background, bottom-third, minimum 48px equivalent |
| **Logo placement** | Bottom-right corner watermark for long-form |

---

## 7. Quality Gates Before Export

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

## 8. File Naming & Storage

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
