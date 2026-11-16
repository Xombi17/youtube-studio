---
name: production-pipeline
description: Orchestrate the full TOPIC→PUBLISHED VIDEO pipeline for GTA VI tutorials and gaming content.
---

## Purpose
Step-by-step execution plan from topic selection to YouTube-ready export. Human approval required at three gates.

## Pipeline Stages

| Stage | Action | Skill | Output |
|-------|--------|-------|--------|
| 1. Research | Gather verified claims | `gta6-researcher` / `source-researcher` | `research/<topic>/claims.md` |
| 2. Fact-check | ⛔ **HUMAN GATE** — verify all claims have source URL + date; flag unverified | — | Signed-off `claims.md` |
| 3. Script | Write beat-by-beat script | `tutorial-scriptwriter` / `shorts-scriptwriter` | `scripts/<topic>/script.md` |
| 4. Storyboard | Plan shots + HyperFrames specs | `video-director` | `scripts/<topic>/storyboard.md` + `storyboard-scenes.json` |
| 5. Generate | Render scenes | `ai-video-generator` | `renders/<topic>/scene-N.mp4` |
| 6. Narration | TTS or ElevenLabs draft | `ai-video-generator` | `renders/<topic>/narration.wav` |
| 7. Edit | Assemble + captions | `video-editor` | `renders/<topic>/final.mp4` |
| 8. Captions | Burn SRT / drawtext | `video-editor` | `renders/<topic>/final-captioned.mp4` |
| 9. Review | ⛔ **HUMAN GATE** — quality pass | `video-quality-reviewer` | Review report |
| 10. Export | Rename final file | — | `exports/<topic>/YYYYMMDD-<slug>.mp4` |
| 11. Metadata | ⛔ **HUMAN GATE** — approve before upload | `youtube-seo` | `exports/<topic>/metadata.md` |

## Human Gates (do not auto-proceed)
- **Stage 2**: Fact-check signoff — confirm every claim is sourced
- **Stage 9**: Quality review pass — confirm video is publish-ready
- **Stage 11**: Metadata approval — confirm title, description and tags before upload

## Directory Layout
```
research/<topic>/claims.md
scripts/<topic>/script.md
scripts/<topic>/storyboard.md
renders/<topic>/scene-N.mp4
renders/<topic>/narration.wav
renders/<topic>/final-captioned.mp4
exports/<topic>/YYYYMMDD-<slug>.mp4
exports/<topic>/metadata.md
assets/clearance-log.md
editing/session-log.md
```

## Abort Conditions
- Any uncleared asset found by `copyright-checker` → stop at Stage 7
- Quality review fails → return to Stage 5 or 7, do not export
