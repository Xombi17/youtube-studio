#!/usr/bin/env bash
# ==============================================================================
# CreatorRadar Studio :: Automated Environment Setup & Hardware Configuration
# One-click bootstrap script for Linux / WSL2 / NVIDIA GPU Laptops
# ==============================================================================

set -e

# Terminal colors
BOLD='\033[1m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

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

# Python 3
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 is not installed. Please install Python 3.10+ (sudo apt install python3 python3-venv).${NC}"
    exit 1
fi
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo -e "  ✔ Python 3: ${GREEN}$PYTHON_VERSION${NC}"

# Node.js
if ! command -v node &> /dev/null; then
    echo -e "${YELLOW}Notice: node is not installed. Required for Next.js dashboard and HyperFrames rendering.${NC}"
else
    NODE_VERSION=$(node --version)
    echo -e "  ✔ Node.js: ${GREEN}$NODE_VERSION${NC}"
fi

# FFmpeg & FFprobe
if ! command -v ffmpeg &> /dev/null; then
    echo -e "${RED}Error: ffmpeg is not installed. Please install FFmpeg (sudo apt install ffmpeg).${NC}"
    exit 1
fi
FFMPEG_VERSION=$(ffmpeg -version 2>&1 | head -n1 | awk '{print $3}')
echo -e "  ✔ FFmpeg: ${GREEN}$FFMPEG_VERSION${NC}"

# Git
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
    # Check NVENC in ffmpeg
    if ffmpeg -encoders 2>/dev/null | grep -q "h264_nvenc"; then
        echo -e "  ${GREEN}✔ FFmpeg NVENC Hardware Acceleration: Available (h264_nvenc, hevc_nvenc)${NC}"
        export FF_HWACCEL="nvenc"
    else
        echo -e "  ${YELLOW}⚠ FFmpeg does not have NVENC compiled; falling back to CPU libx264.${NC}"
    fi
else
    echo -e "  ${YELLOW}⚠ No active NVIDIA GPU driver detected via nvidia-smi. Running in CPU mode.${NC}"
fi

# ------------------------------------------------------------------------------
# 3. Setup Top-Level Python Virtual Environment
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}[3/7] Setting up Studio Python Virtual Environment...${NC}"

if [ ! -d ".venv" ]; then
    echo "  Creating python3 virtual environment in .venv..."
    python3 -m venv .venv
fi

source .venv/bin/activate
pip install --upgrade pip --quiet

if [ -f "requirements.txt" ]; then
    echo "  Installing core requirements..."
    pip install -r requirements.txt --quiet
fi

# If NVIDIA GPU is present, install CUDA-accelerated PyTorch
if [ "$HAS_NVIDIA_GPU" = true ]; then
    echo "  Configuring PyTorch with CUDA 12.1 support for NVIDIA GPU..."
    pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121 --quiet || {
        echo "  Notice: Defaulting to standard torch installation."
        pip install torch torchaudio --quiet
    }
fi

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

# Setup VoiceStudio virtualenv if missing
if [ -d "$VOICE_STUDIO_DIR" ]; then
    if [ ! -d "$VOICE_STUDIO_DIR/.venv" ]; then
        echo "  Setting up VoiceStudio virtual environment (.venv)..."
        (
            cd "$VOICE_STUDIO_DIR"
            python3 -m venv .venv
            source .venv/bin/activate
            pip install --upgrade pip --quiet
            if [ -f "requirements.txt" ]; then
                pip install -r requirements.txt --quiet || true
            fi
            if [ "$HAS_NVIDIA_GPU" = true ]; then
                pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121 --quiet || true
            fi
        )
        echo -e "  ${GREEN}✔ VoiceStudio virtual environment initialized.${NC}"
    else
        echo -e "  ${GREEN}✔ VoiceStudio virtual environment ready.${NC}"
    fi
fi

# ------------------------------------------------------------------------------
# 5. Dashboard-Next (Next.js) Dependencies
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}[5/7] Setting up Dashboard-Next (UI Control Center)...${NC}"

if [ -d "dashboard-next" ] && command -v npm &> /dev/null; then
    if [ ! -d "dashboard-next/node_modules" ]; then
        echo "  Installing dashboard-next dependencies via npm..."
        (cd dashboard-next && npm install --quiet)
    else
        echo -e "  ${GREEN}✔ dashboard-next dependencies already installed.${NC}"
    fi
fi

# ------------------------------------------------------------------------------
# 6. Claude Code & Agent Skills Verification
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
SKILL_COUNT=$(ls -1 skills | wc -l)
echo -e "  ${GREEN}✔ Verified $SKILL_COUNT production skills linked to .claude/skills/${NC}"

# Ensure helper scripts are executable
chmod +x scripts/*.py scripts/**/*.py orchestration/*.py dashboard/*.py 2>/dev/null || true

# ------------------------------------------------------------------------------
# 7. Voice Profile Verification
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}[7/7] Verifying Voice Profile for Voice Cloning...${NC}"

VOICE_SAMPLE="$WORKSPACE_ROOT/assets/voices/creator_sample.wav"
if [ -f "$VOICE_SAMPLE" ]; then
    SAMPLE_SIZE=$(ls -lh "$VOICE_SAMPLE" | awk '{print $5}')
    echo -e "  ${GREEN}✔ Channel Owner voice profile found (${SAMPLE_SIZE}): assets/voices/creator_sample.wav${NC}"
else
    echo -e "  ${YELLOW}⚠ Voice sample not found. Record or place your voice sample at assets/voices/creator_sample.wav${NC}"
fi

# ------------------------------------------------------------------------------
# Finished!
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}${GREEN}==============================================================================${NC}"
echo -e "${BOLD}${GREEN}   Setup Complete! CreatorRadar Studio is ready on your machine.              ${NC}"
echo -e "${BOLD}${GREEN}==============================================================================${NC}"
echo -e "\n${BOLD}Quickstart Commands:${NC}"
echo -e "  1. ${BOLD}Start VoiceStudio Voice Cloning Service:${NC}"
echo -e "     cd VoiceStudio && source .venv/bin/activate && python app.py"
echo -e "     (Runs on http://localhost:3900 with GPU/CUDA acceleration)"
echo -e ""
echo -e "  2. ${BOLD}Launch Mission Control Dashboard:${NC}"
echo -e "     python3 dashboard/app.py"
echo -e "     (Open http://localhost:8080 in your browser)"
echo -e ""
echo -e "  3. ${BOLD}Run Autonomous End-to-End Video Production Wave:${NC}"
echo -e "     python3 orchestration/multi_agent_studio.py \"GTA VI Storage Requirements PS5\""
echo -e ""
echo -e "  4. ${BOLD}Open with Claude Code or Codex:${NC}"
echo -e "     claude   (all 19 skills loaded automatically from .claude/skills/)"
echo -e "${BOLD}${BLUE}==============================================================================${NC}\n"
