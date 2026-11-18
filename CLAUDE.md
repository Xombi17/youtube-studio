# CreatorRadar — YouTube Studio Configuration for Claude Code

Claude Code reads this file at project root on every session. Apply all rules and skill routing below throughout this workspace.

---

## Skill Routing Table

All skills live in `skills/<name>/SKILL.md`. Read the matching skill file **before** starting the corresponding task. Claude Code symlinks are under `.claude/skills/<name>/SKILL.md`.

| Task | Skill | Symlink |
|---|---|---|
| Find current video ideas | `trend-scout` | `.claude/skills/trend-scout/` |
| Verify claims and collect sources | `source-researcher` | `.claude/skills/source-researcher/` |
| Write a vertical video script | `shorts-scriptwriter` | `.claude/skills/shorts-scriptwriter/` |
| Plan shots, typography and motion | `visual-director` | `.claude/skills/visual-director/` |
| Use Indian visual traditions thoughtfully | `indian-art-styles` | `.claude/skills/indian-art-styles/` |
| Clear third-party footage, music and images | `clip-rights-checker` | `.claude/skills/clip-rights-checker/` |
| Review a rendered video | `video-quality-reviewer` | `.claude/skills/video-quality-reviewer/` |
| Interpret channel data | `channel-analyst` | `.claude/skills/channel-analyst/` |
| Create a Lemo-Opuscar styled film | `lemo-opuscar` | `.claude/skills/lemo-opuscar/` |
| Research GTA VI facts from authoritative sources | `gta6-researcher` | `.claude/skills/gta6-researcher/` |
| Write tutorial scripts (long-form or Shorts) | `tutorial-scriptwriter` | `.claude/skills/tutorial-scriptwriter/` |
| Plan shots, scenes and storyboard for video | `video-director` | `.claude/skills/video-director/` |
| Generate AI animation scenes with HyperFrames | `ai-video-generator` | `.claude/skills/ai-video-generator/` |
| Assemble and export final video with FFmpeg | `video-editor` | `.claude/skills/video-editor/` |
| Verify all assets are cleared for YouTube use | `copyright-checker` | `.claude/skills/copyright-checker/` |
| Generate title, description, tags and thumbnail concept | `youtube-seo` | `.claude/skills/youtube-seo/` |
| Orchestrate the full TOPIC→METADATA pipeline | `production-pipeline` | `.claude/skills/production-pipeline/` |
| Voice cloning & neural speech synthesis via VoiceStudio | `voice-studio` | `.claude/skills/voice-studio/` |
| Select optimal visual motion style across catalogs | `style-selector` | `.claude/skills/style-selector/` |
| Produce Vox-style documentary explainer videos | `vox-explainer` | `.claude/skills/vox-explainer/` |
| Portable viral Shorts blueprint v2 (2.5D motion, visual proof, plan validator, 3-stem handoff) | `codex-shorts-blueprint` | `.claude/skills/codex-shorts-blueprint/` |
| Write script from 21 hook formulas with retention beats | `yt-script` | `.claude/skills/yt-script/` |
| Title & thumbnail pairing linter | `yt-package` | `.claude/skills/yt-package/` |
| Edit decision list from transcript (dead air, filler cues) | `yt-edit` | `.claude/skills/yt-edit/` |
| Triage comments and draft replies in voice | `yt-comment` | `.claude/skills/yt-comment/` |
| Weekly YouTube content schedule planner | `yt-plan` | `.claude/skills/yt-plan/` |
| Outlier video research ranked by channel multiple | `yt-viral` | `.claude/skills/yt-viral/` |
| Audience retention curve & cliff diagnostics | `yt-retention` | `.claude/skills/yt-retention/` |
| Extract Shorts from long-form video transcript | `yt-shorts` | `.claude/skills/yt-shorts/` |
| Description, tags, and search query optimization | `yt-seo` | `.claude/skills/yt-seo/` |
| Video chapters generator from transcript | `yt-chapters` | `.claude/skills/yt-chapters/` |
| Channel audit ending in high-leverage single fix | `yt-audit` | `.claude/skills/yt-audit/` |

**Total skills: 32**

---

## CreatorRadar — Studio Rules

These rules are **mandatory** and cannot be overridden by any task instruction:

1. **No first-hand gameplay claims** — Never claim personal/first-hand gameplay experience of GTA VI. The studio does not own a PS5 or Xbox; we have not played the game ourselves.

2. **No fabricated mechanics** — Never fabricate gameplay mechanics, cheat codes, missions, in-game details, or stats that are not independently verified from authoritative sources listed in `config/gta6-sources.md`.

3. **Always cite official sources for GTA VI facts** — Every GTA VI factual claim must be backed by an official Rockstar Games, PlayStation, or Xbox source. Consult `config/gta6-sources.md` for the approved source registry and confidence levels.

4. **Human approval before upload** — No video, Short, or Community post may be uploaded to YouTube without explicit human (channel owner) approval. Prepare content; never publish autonomously.

5. **Label all AI-generated content** — Every video or Short containing AI-generated graphics, animation, or narration must include in its YouTube description:
   > *"Graphics created with AI assistance. All facts sourced from official documentation."*

6. **Mandatory voice cloning via VoiceStudio** — Always use the channel owner's cloned voice profile (`assets/voices/creator_sample.wav`) via `scripts/voice_studio_client.py` and VoiceStudio (`http://localhost:3900`). Apply audio compression, EQ presence, and high-energy pacing (~170–175 WPM).

7. **Mandatory high-retention kinetic motion graphics** — Never render static video cards. All videos must incorporate continuous micro-motion (Ken Burns zooms 1.0x → 1.08x), visual cut punctuations (screen flickers, flash cuts, scanlines), high-contrast glowing elements, and animated captions to prevent audience drop-off.
8. **Clean full-bleed canvas (Zero UI/template chrome)** — Never render top masthead header bars, `CATEGORY // SUBTITLE` kickers, top horizontal divider lines, `01 / 09` beat-counter boxes, bottom source/disclaimer bars (`ILLUSTRATIVE EXAMPLE • SOURCE: ...`), on-screen timers (`00:00.0 / 00:43.5`), or bottom progress bars. Place all source links and disclosures in the YouTube description (`metadata.md`), and use the full 1080×1920 vertical canvas for bold, immersive storytelling, layered animated background elements, and kinetic visuals.
9. **2026 Mobile-first Shorts upload & Browse Features protocol** — All YouTube Shorts must include a 1-frame custom thumbnail card baked into the timeline for mobile frame selection (unlocking YouTube Home Browse traffic), stage initially as UNLISTED for Content ID / HD clearance, strictly cap hashtags to 3–5 niche tags, deploy curiosity / end-payoff hooks (< 55 characters), attach an authoritative Related Video link, and schedule/publish 60 minutes prior to audience peak activity.

---

## Supporting Config Files

| File | Purpose |
|---|---|
| `config/channel-strategy.md` | Channel goals, content pillars, posting cadence, monetization checklist |
| `config/production-rules.md` | Quality gates, file naming, copyright compliance, brand standards |
| `config/model-routing.md` | Which AI model tier to use for which task class |
| `config/gta6-sources.md` | Authoritative GTA VI source registry with verified facts and confidence levels |
| `dashboard/ideas-queue.md` | Live content idea tracking table |
| `assets/clearance-log.md` | Copyright clearance log for all assets used |

---

## Production Pipeline Summary

```
TOPIC → gta6-researcher → source-researcher → [human fact-check] →
tutorial-scriptwriter → video-director → ai-video-generator →
video-editor → video-quality-reviewer → [human QA] →
youtube-seo → [human approval] → PUBLISH
```

Full pipeline instructions: `skills/production-pipeline/SKILL.md`
