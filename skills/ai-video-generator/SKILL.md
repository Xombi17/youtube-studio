---
name: ai-video-generator
description: Generate video assets using available local tools — HyperFrames HTML+GSAP, FFmpeg compositing, Python scripts.
---

## Purpose
Render each storyboard scene to an MP4 file using only local or approved tools.

## Tool Priority
1. **HyperFrames** — HTML/CSS/GSAP → MP4 via headless Chrome/Puppeteer (primary)
2. **FFmpeg** — `drawtext`, `overlay`, `fade` filters for simple title cards / transitions (fallback)
3. **Python** — `pyttsx3` or `espeak` for TTS narration; `moviepy` for compositing glue

## Output Specs
| Format | Resolution | FPS | Video | Audio |
|--------|-----------|-----|-------|-------|
| Shorts | 1080×1920 | 30 | H.264 | AAC 128k |
| Long-form | 1920×1080 | 30 | H.264 | AAC 128k |

## Asset Rules
- ✅ Original HyperFrames infographics and animations
- ✅ Rockstar official press-kit art — with attribution overlay
- ✅ Official trailers (commentary/review use)
- ❌ AI image generators for fake gameplay screenshots
- ❌ Uncleared third-party footage

## Narration
- Use `pyttsx3` or `espeak` for local TTS draft
- Note where ElevenLabs API key would improve quality (do NOT auto-spend)

## Clearance Log
Document every asset in `assets/clearance-log.md`:
```
| Asset | Source | License | Status | Attribution |
```

## Output
Scenes → `renders/<topic>/scene-N.mp4`
Narration → `renders/<topic>/narration.wav`
