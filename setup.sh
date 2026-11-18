#!/usr/bin/env bash
# ==============================================================================
# CreatorRadar Studio :: Automated Environment Setup & Hardware Configuration
# One-click bootstrap script for Linux / WSL2 / NVIDIA GPU Laptops
# ==============================================================================

set -e

BOLD='\033[1m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$WORKSPACE_ROOT"

echo -e "${BOLD}${BLUE}==============================================================================${NC}"
echo -e "${BOLD}${BLUE}   CreatorRadar Studio :: Autonomous YouTube Production Workspace Setup        ${NC}"
echo -e "${BOLD}${BLUE}==============================================================================${NC}"
echo -e "Workspace Root: ${BOLD}$WORKSPACE_ROOT${NC}\n"

# ------------------------------------------------------------------------------
# 1. System Requirements & Toolchain Check
# ------------------------------------------------------------------------------
echo -e "${BOLD}[1/7] Checking System Requirements & Toolchain...${NC}"

# Prefer Python 3.11 / 3.12 for full PyTorch/CUDA wheel compatibility
PYTHON_BIN=""
for candidate in python3.11 python3.12 python3; do
    if command -v "$candidate" &> /dev/null; then
        PYTHON_BIN="$(command -v "$candidate")"
        break
    fi
done
if [ -z "$PYTHON_BIN" ]; then
    echo -e "${RED}Error: Python 3.11+ is required.${NC}"
    exit 1
fi
echo -e "  ✔ Python: ${GREEN}$($PYTHON_BIN --version) ($PYTHON_BIN)${NC}"

if command -v uv &> /dev/null; then
    echo -e "  ✔ uv: ${GREEN}$(uv --version)${NC}"
fi

if ! command -v node &> /dev/null; then
    echo -e "${YELLOW}Notice: node is not installed. Required for Next.js Studio UI.${NC}"
else
    echo -e "  ✔ Node.js: ${GREEN}$(node --version)${NC}"
fi

if ! command -v ffmpeg &> /dev/null; then
    echo -e "${RED}Error: ffmpeg is not installed. Please install FFmpeg.${NC}"
    exit 1
fi
echo -e "  ✔ FFmpeg: ${GREEN}$(ffmpeg -version 2>&1 | head -n1 | awk '{print $3}')${NC}"

if ! command -v git &> /dev/null; then
    echo -e "${RED}Error: git is not installed.${NC}"
    exit 1
fi
echo -e "  ✔ Git: ${GREEN}$(git --version)${NC}"

# ------------------------------------------------------------------------------
# 2. NVIDIA GPU & Hardware Acceleration Detection
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}[2/7] Checking NVIDIA GPU & Acceleration Capabilities...${NC}"

HAS_NVIDIA_GPU=false
if command -v nvidia-smi &> /dev/null; then
    GPU_INFO=$(nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>/dev/null | head -n 1)
    if [ -n "$GPU_INFO" ]; then
        HAS_NVIDIA_GPU=true
        echo -e "  ${GREEN}✔ NVIDIA GPU Detected:${NC} ${BOLD}$GPU_INFO${NC}"
    fi
fi

if [ "$HAS_NVIDIA_GPU" = true ]; then
    if ffmpeg -encoders 2>/dev/null | grep -q "h264_nvenc"; then
        echo -e "  ${GREEN}✔ FFmpeg NVENC Hardware Acceleration: Available (h264_nvenc, hevc_nvenc)${NC}"
    else
        echo -e "  ${YELLOW}⚠ FFmpeg does not have NVENC compiled; falling back to CPU libx264.${NC}"
    fi
else
    echo -e "  ${YELLOW}⚠ No active NVIDIA GPU driver detected via nvidia-smi. Running in CPU mode.${NC}"
fi

# ------------------------------------------------------------------------------
# 3. Setup Top-Level Python Virtual Environment
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}[3/7] Setting up Studio Python Virtual Environment (.venv)...${NC}"

if command -v uv &> /dev/null; then
    if [ ! -d ".venv" ]; then
        uv venv --python "$PYTHON_BIN" .venv
    fi
    uv pip install --python .venv/bin/python -r requirements.txt
else
    if [ ! -d ".venv" ]; then
        "$PYTHON_BIN" -m venv .venv
    fi
    source .venv/bin/activate
    pip install --upgrade pip --quiet
    pip install -r requirements.txt --quiet
fi
echo -e "  ${GREEN}✔ Studio .venv ready (Playwright, Edge-TTS, audio utilities installed).${NC}"

# ------------------------------------------------------------------------------
# 4. Clone & Setup VoiceStudio Sub-Repository
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}[4/7] Verifying VoiceStudio Sub-Repository...${NC}"

VOICE_STUDIO_DIR="$WORKSPACE_ROOT/VoiceStudio"
VOICE_STUDIO_REPO="https://github.com/debpalash/VoiceStudio.git"

if [ ! -d "$VOICE_STUDIO_DIR" ] || [ ! -d "$VOICE_STUDIO_DIR/.git" ]; then
    echo -e "  Cloning VoiceStudio from ${BOLD}$VOICE_STUDIO_REPO${NC}..."
    git clone "$VOICE_STUDIO_REPO" "$VOICE_STUDIO_DIR"
else
    echo -e "  ${GREEN}✔ VoiceStudio repository present.${NC}"
fi

if [ -d "$VOICE_STUDIO_DIR" ] && [ ! -d "$VOICE_STUDIO_DIR/.venv" ]; then
    echo "  Syncing VoiceStudio Python environment..."
    if command -v uv &> /dev/null; then
        if [ "$HAS_NVIDIA_GPU" = true ]; then
            (cd "$VOICE_STUDIO_DIR" && uv sync --python "$PYTHON_BIN" --no-group dev --group cuda)
        else
            (cd "$VOICE_STUDIO_DIR" && uv sync --python "$PYTHON_BIN" --no-group dev --group cpu)
        fi
    else
        echo -e "  ${YELLOW}⚠ Install 'uv' to sync VoiceStudio's lockfile cleanly.${NC}"
    fi
    echo -e "  ${GREEN}✔ VoiceStudio virtual environment initialized.${NC}"
elif [ -d "$VOICE_STUDIO_DIR/.venv" ]; then
    echo -e "  ${GREEN}✔ VoiceStudio virtual environment ready.${NC}"
fi

# ------------------------------------------------------------------------------
# 5. Dashboard-Next (Next.js Studio UI) Dependencies
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}[5/7] Setting up Next.js Studio UI (dashboard-next)...${NC}"

if [ -d "dashboard-next" ] && command -v npm &> /dev/null; then
    if [ ! -d "dashboard-next/node_modules" ]; then
        echo "  Installing dashboard-next dependencies via npm..."
        (cd dashboard-next && npm install --quiet)
    else
        echo -e "  ${GREEN}✔ dashboard-next dependencies already installed.${NC}"
    fi
fi

# ------------------------------------------------------------------------------
# 6. Agent Skills Verification
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}[6/7] Verifying Agent Skills & Relative Links...${NC}"

mkdir -p .claude/skills
for skill_dir in skills/*; do
    if [ -d "$skill_dir" ]; then
        skill_name=$(basename "$skill_dir")
        if [ ! -L ".claude/skills/$skill_name" ]; then
            ln -sf "../../skills/$skill_name" ".claude/skills/$skill_name"
        fi
    fi
done
SKILL_COUNT=$(find skills -mindepth 1 -maxdepth 1 -type d | wc -l)
echo -e "  ${GREEN}✔ Verified $SKILL_COUNT production skills linked to .claude/skills/${NC}"

chmod +x scripts/*.py scripts/*.sh orchestration/*.py dashboard/*.py 2>/dev/null || true

# ------------------------------------------------------------------------------
# 7. Voice Profile Verification
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}[7/7] Verifying Voice Profile for Voice Cloning...${NC}"

VOICE_SAMPLE="$WORKSPACE_ROOT/assets/voices/creator_sample.wav"
if [ -f "$VOICE_SAMPLE" ]; then
    SAMPLE_SIZE=$(ls -lh "$VOICE_SAMPLE" | awk '{print $5}')
    echo -e "  ${GREEN}✔ Channel Owner voice profile found (${SAMPLE_SIZE}): assets/voices/creator_sample.wav${NC}"
else
    echo -e "  ${YELLOW}⚠ Voice sample not found. Record via Studio UI -> Voice Studio tab.${NC}"
fi

echo -e "\n${BOLD}${GREEN}==============================================================================${NC}"
echo -e "${BOLD}${GREEN}   Setup Complete! CreatorRadar Studio is ready on your machine.              ${NC}"
echo -e "${BOLD}${GREEN}==============================================================================${NC}"
echo -e "\n${BOLD}Quickstart Commands:${NC}"
echo -e "  1. ${BOLD}Start Studio API + Next.js UI (one command):${NC}"
echo -e "     ./scripts/start_studio.sh"
echo -e "     (UI: http://localhost:3000 | API: http://127.0.0.1:8080)"
echo -e ""
echo -e "  2. ${BOLD}Optional — Start VoiceStudio GPU Server (CUDA):${NC}"
echo -e "     cd VoiceStudio && .venv/bin/uvicorn main:app --app-dir backend --host 127.0.0.1 --port 3900"
echo -e ""
echo -e "  3. ${BOLD}Run Autonomous End-to-End Video Production Wave (CLI):${NC}"
echo -e "     .venv/bin/python orchestration/multi_agent_studio.py \"GTA VI Launch Day Survival Guide\""
echo -e ""
echo -e "  4. ${BOLD}Open with Claude Code / Codex / Antigravity:${NC}"
echo -e "     All $SKILL_COUNT skills linked in .claude/skills/ and indexed in AGENTS.md"
echo -e "${BOLD}${BLUE}==============================================================================${NC}\n"
