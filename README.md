# CreatorRadar — Autonomous YouTube Production Studio

CreatorRadar is an autonomous, agentic YouTube video production workspace engineered for high-retention vertical Shorts and long-form video production. It orchestrates research, verified claim checks, scriptwriting, voice cloning, HTML5/GSAP kinetic motion graphic rendering, and YouTube SEO packaging.

Designed to run locally on your workstation or laptop with **NVIDIA GPU acceleration (CUDA + NVENC)**.

---

## ⚡ Quickstart: One-Click Setup

Clone this repository and run the automated bootstrap script:

```bash
git clone <your-repo-url> youtube-studio
cd youtube-studio
./setup.sh
```

### What `./setup.sh` does automatically:
1. **Toolchain Verification**: Checks Python 3.10+, Node.js 18+, FFmpeg, and Git.
2. **NVIDIA GPU Detection**: Probes `nvidia-smi` for CUDA version and GPU VRAM; configures CUDA-accelerated PyTorch (`torch`, `torchaudio`).
3. **Hardware Video Acceleration**: Detects FFmpeg NVENC support (`h264_nvenc`, `hevc_nvenc`) for blazing fast video renders.
4. **Sub-Repository Auto-Clone**: Automatically clones the external [VoiceStudio](https://github.com/debpalash/VoiceStudio.git) repository into `./VoiceStudio` and configures its virtual environment.
5. **Skill Links**: Verifies and links all 19 agent skills into `.claude/skills/` for Claude Code and AGENTS.md for Codex / Antigravity.
6. **Voice Profile**: Validates the channel owner's cloned voice sample at `assets/voices/creator_sample.wav`.

---

## 🚀 Running on a Laptop with NVIDIA GPU

### 1. Hardware Video Acceleration (FFmpeg NVENC)
When an NVIDIA GPU driver is detected, FFmpeg can utilize hardware-accelerated NVENC encoding instead of CPU software rendering, yielding 5x–10x faster export speeds:
- **H.264 NVENC**: `ffmpeg -hwaccel cuda -i input.mp4 -c:v h264_nvenc -preset p4 -cq 20 output.mp4`
- **HEVC NVENC**: `ffmpeg -hwaccel cuda -i input.mp4 -c:v hevc_nvenc -preset p4 -cq 22 output.mp4`

### 2. CUDA-Accelerated Voice Cloning & Speech Synthesis
VoiceStudio utilizes PyTorch and CUDA for real-time neural voice cloning:
```bash
# Verify GPU availability in Python
python3 -c "import torch; print('CUDA available:', torch.cuda.is_available(), '| Device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
```

---

## 🎙️ VoiceStudio Sub-Repository (Voice Cloning)

VoiceStudio is maintained as a separate repository to keep this studio repository lean and modular:
- **Repository URL**: `https://github.com/debpalash/VoiceStudio.git`
- **Local Directory**: `./VoiceStudio` (automatically managed by `setup.sh` and ignored by `.gitignore`)

### Manual Clone & Startup (if not using setup.sh):
```bash
# 1. Clone VoiceStudio into the workspace root
git clone https://github.com/debpalash/VoiceStudio.git VoiceStudio

# 2. Setup VoiceStudio environment
cd VoiceStudio
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# For NVIDIA GPU:
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121

# 3. Start the VoiceStudio server on port 3900
python app.py
```

The CreatorRadar voice client (`scripts/voice_studio_client.py`) will automatically connect to `http://localhost:3900` to synthesize speech using your enrolled voice profile.

---

## 🖥️ Interactive Control Centers & Dashboards

### 1. Mission Control Dashboard (Python Engine)
Features in-browser microphone voice enrollment, one-click kinetic video rendering, and live pipeline logs:
```bash
python3 dashboard/app.py
```
Open **`http://localhost:8080`** in your browser.

### 2. Next.js Studio Dashboard (React / TypeScript)
Modern web interface for managing topics, reviewing metrics, and previewing exports:
```bash
cd dashboard-next
npm install
npm run dev
```
Open **`http://localhost:3000`** in your browser.

---

## 🤖 Multi-Agent Autonomous Production

Run the end-to-end 7-agent production pipeline from a single CLI command:

```bash
python3 orchestration/multi_agent_studio.py "GTA VI Storage Requirements PS5"
```

### The Autonomous Wave:
1. **Trend & Hook Analyst**: Formulates high-retention (0–3s) contrarian hooks.
2. **GTA VI Fact & Source Researcher**: Verifies all factual claims against official Rockstar / PlayStation sources.
3. **Script Architect**: Writes high-cadence vertical Shorts scripts with on-screen visual cues.
4. **Style Selector**: Analyzes the topic across 120+ motion styles (Claude Video 2.0 & Lemo-Opuscar) and selects the ideal visual language.
5. **Voice Studio Audio Engineer**: Synthesizes speech using the channel owner's voice profile via VoiceStudio API.
6. **Motion Graphics Artist**: Builds dynamic HTML5/GSAP scenes with continuous micro-motion (Ken Burns, kinetic typography, neon accents).
7. **Quality & Compliance Reviewer**: Inspects rendered frames, checks audio pacing, and ensures strict adherence to CreatorRadar studio rules.

---

## 🛠️ Integrated Production Skills (19 Skills)

All skills are available in `skills/<name>/SKILL.md` and symlinked to `.claude/skills/`:

| Task | Skill | Description |
| --- | --- | --- |
| Find current video ideas | `trend-scout` | Unearths high-CTR gaming and tech topic angles |
| Verify claims and sources | `source-researcher` | Cross-checks facts with primary documentation |
| Write vertical video script | `shorts-scriptwriter` | High-cadence, retention-engineered Shorts scripts |
| Plan shots and motion | `visual-director` | Formulates shot lists, kinetic typography, pacing |
| Indian visual traditions | `indian-art-styles` | Contextual visual styling and aesthetics |
| Clear third-party footage | `clip-rights-checker` | Fair-use and copyright risk mitigation |
| Review rendered video | `video-quality-reviewer` | Evaluates MP4 composition, pacing, and audio |
| Channel performance | `channel-analyst` | Interprets YouTube Studio retention analytics |
| Code-generated styled films | `lemo-opuscar` | 100+ styled procedural visual aesthetics |
| Authoritative GTA VI facts | `gta6-researcher` | Verified Rockstar / console hardware registry |
| Tutorial scripts | `tutorial-scriptwriter` | Step-by-step guides with zero fluff |
| Storyboarding & scene plans | `video-director` | Multi-scene layout and visual beat mapping |
| HyperFrames AI animation | `ai-video-generator` | Procedural HTML5 video scenes |
| Final FFmpeg assembly | `video-editor` | Hardware-accelerated muxing, filters, and audio |
| Asset copyright clearance | `copyright-checker` | Validates licenses before publication |
| YouTube SEO & packaging | `youtube-seo` | High-CTR titles, descriptions, tags, thumbnail prompts |
| Full autonomous pipeline | `production-pipeline` | Orchestrates TOPIC → METADATA pipeline |
| Voice cloning & speech | `voice-studio` | Clones channel owner voice via VoiceStudio API |
| Dynamic visual style match | `style-selector` | Automatically routes script to optimal visual style |

---

## 🛡️ Studio Rules (Mandatory)

1. **No first-hand gameplay claims**: Never fabricate personal play sessions; strictly cite verified documentation.
2. **Zero fabricated mechanics**: All specifications, storage requirements, and dates must be backed by official sources in `config/gta6-sources.md`.
3. **Mandatory voice cloning via VoiceStudio**: Always utilize the channel owner voice profile (`assets/voices/creator_sample.wav`) with punchy pacing (170–175 WPM).
4. **Mandatory kinetic motion graphics**: Avoid static video cards. Always use continuous micro-motion, glowing callouts, visual cuts, and animated captions.
5. **Mandatory AI disclosure**: Include the disclosure line in video descriptions:
   > *"Graphics created with AI assistance. All facts sourced from official documentation."*
6. **Human approval before upload**: Content in `exports/` requires a completed `checklist.md` before YouTube publishing.
