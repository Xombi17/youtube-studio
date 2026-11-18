# CreatorRadar — Autonomous YouTube Production Studio

CreatorRadar is a local-first, agentic YouTube production studio for high-retention vertical Shorts (9:16) and long-form videos (16:9). It orchestrates hook scoring, verified research, structured scriptwriting, VoiceStudio voice cloning (with neural Edge-TTS fallback), -14 LUFS broadcast audio mastering + SFX mixing, deterministic HTML5/GSAP kinetic rendering via **NVIDIA NVENC**, automated QA auditing, and YouTube SEO packaging.

---

## ⚡ Quickstart

```bash
./setup.sh
./scripts/start_studio.sh
# Or include the local VoiceStudio CUDA server:
./scripts/start_studio.sh --with-voicestudio
```

- **Studio UI (Next.js):** `http://localhost:3000`
- **Studio Engine API (Python):** `http://127.0.0.1:8080`
- **VoiceStudio CUDA Server (optional):** `http://127.0.0.1:3900`

---

## 🤖 Multi-Agent Autonomous Production (CLI)

Run the end-to-end 7-stage production wave for **any topic** from the command line:

```bash
# Vertical 9:16 Short (auto-selects style from 120 styles)
.venv/bin/python orchestration/multi_agent_studio.py "GTA VI Launch Day Survival Guide"

# Landscape 16:9 Explainer with explicit style & custom script
.venv/bin/python orchestration/multi_agent_studio.py \
  --topic "Why Local AI Workflows Beat Cloud Subscriptions" \
  --format long \
  --style swiss-kinetic \
  --script path/to/script.md
```

### The Production Wave:
1. **Trend & Hook Analyst**: Formulates candidate hooks and scores them with `skills/yt-script/hookscore.py`.
2. **Script Architect**: Parses a provided `script.md`/`beats.json` or drafts verified beats (strictly citing `config/gta6-sources.md` for GTA VI topics).
3. **Studio Director**: Indexes all **120 styles** (21 Claude Video 2.0 + 99 Lemo-Opuscar) via `scripts/select_style.py` and extracts real color tokens.
4. **Voice & Audio Engineer**: Synthesizes per-beat narration via VoiceStudio (`http://localhost:3900`) or neural Edge-TTS fallback, applies broadcast EQ/compression (`-14 LUFS`), measures exact beat durations, and mixes beat-synced SFX from `assets/sfx/`.
5. **Motion Graphics Artist**: Builds a deterministic `studio.js` + GSAP HTML5 composition in the selected style's palette with continuous Ken Burns motion, beat cut flashes, and word-by-word synced captions.
6. **Video Assembler**: Renders frames deterministically via `scripts/render_scene.py` (Playwright + Chrome → FFmpeg `h264_nvenc` GPU encoding) and muxes the master MP4 into `exports/<slug>/`.
7. **Quality & Compliance Gatekeeper**: Runs `scripts/video_review_agent.py` (real `ffprobe` streams, EBU R128 loudness & True Peak audit, frame-hash motion verification, `metadata.md` with AI disclosure, and unchecked human-approval `checklist.md`).

---

## 🎙️ VoiceStudio (CUDA Voice Cloning)

`setup.sh` clones [VoiceStudio](https://github.com/debpalash/VoiceStudio.git) into `./VoiceStudio` (git-ignored) and syncs its Python 3.11 + CUDA PyTorch environment via `uv`:

```bash
cd VoiceStudio
.venv/bin/uvicorn main:app --app-dir backend --host 127.0.0.1 --port 3900
```

When VoiceStudio is online, `scripts/voice_studio_client.py` synthesizes with your enrolled voice profile (`assets/voices/creator_sample.wav`). When offline, it seamlessly falls back to local neural Edge-TTS with identical broadcast mastering.

---

## 🖥️ Studio Control Center

- **Next.js Studio UI (`dashboard-next/`)**: Production wave launcher, live `ideas-queue.md` manager, 120-style visual catalog with color swatches, Exports & QA video reviewer with beat-frame filmstrip and Rule 4 sign-off, in-browser Voice Studio mic recorder, and live Hook Scorer / Title Linter tools.
- **Python Studio API (`dashboard/app.py`)**: Serves `/api/*` and HTTP Range `/media/*` on `http://127.0.0.1:8080`.
- **CLI Dashboard (`dashboard/radar.py`)**: Quick terminal overview (`python3 dashboard/radar.py [queue|monetization|facts|skills]`).

---

## 🛠️ Integrated Production Skills (32 Skills)

All **32 skills** live in `skills/<name>/SKILL.md` and are symlinked into `.claude/skills/` and routed via `AGENTS.md` / `CLAUDE.md`. Highlights include:
- **Production & Direction:** `production-pipeline`, `codex-shorts-blueprint` (v2.0.0 — 2.5D motion presets, visual proof & `validate_plan.py`), `trend-scout`, `source-researcher`, `gta6-researcher`, `shorts-scriptwriter`, `tutorial-scriptwriter`, `visual-director`, `video-director`, `style-selector`, `ai-video-generator`, `video-editor`, `vox-explainer`, `lemo-opuscar`, `indian-art-styles`, `voice-studio`
- **Review & Rights:** `video-quality-reviewer`, `copyright-checker`, `clip-rights-checker`
- **YouTube Growth & CLI Tools:** `youtube-seo`, `channel-analyst`, `yt-script` (`hookscore.py`), `yt-package` (`title.py`), `yt-edit` (`deadair.py`), `yt-chapters` (`chapters.py`), `yt-retention` (`retention.py`), `yt-viral` (`swipe.py`), `yt-shorts`, `yt-seo`, `yt-plan`, `yt-comment`, `yt-audit`

---

## 🛡️ Studio Rules (Mandatory)

1. **No first-hand gameplay claims** — Never fabricate personal GTA VI play sessions.
2. **No fabricated mechanics** — All GTA VI specs and dates must trace to `config/gta6-sources.md`.
3. **Always cite official sources** — Link primary sources in scripts and YouTube descriptions.
4. **Human approval before upload** — Agents prepare exports and checklists but never publish autonomously.
5. **Mandatory AI disclosure** — Descriptions include: *"Graphics created with AI assistance. All facts sourced from official documentation."*
6. **Mandatory voice cloning & broadcast audio** — VoiceStudio profile (`assets/voices/creator_sample.wav`) + `-14 LUFS` mastering.
7. **Mandatory kinetic motion graphics** — Zero static frames; continuous micro-motion, cut punctuations, and kinetic captions.
