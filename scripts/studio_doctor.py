#!/usr/bin/env python3
"""
CreatorRadar Studio Doctor / Pre-Flight Environment Audit
Checks hardware, encoders, browsers, Python/Node environments, local AI engines,
model caches, and studio governance assets.
"""

import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run_cmd(cmd: list[str], timeout: int = 8) -> tuple[int, str]:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = (res.stdout or res.stderr or "").strip()
        return res.returncode, out
    except Exception as e:
        return 1, str(e)


def check_nvenc() -> tuple[bool, str]:
    rc, _ = run_cmd(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.1",
            "-c:v", "h264_nvenc", "-f", "null", "-",
        ]
    )
    return rc == 0, "h264_nvenc live encode OK" if rc == 0 else "NVENC unavailable (will use CPU libx264)"


def check_voicestudio_http(url: str = "http://127.0.0.1:3900") -> bool:
    for path in ("/health", "/api/health", "/v1/models"):
        try:
            with urllib.request.urlopen(f"{url}{path}", timeout=1.5) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            continue
    return False


def check_python_import(py_path: Path, imports: str) -> tuple[bool, str]:
    if not py_path.exists():
        return False, f"missing venv: {py_path.relative_to(ROOT)}"
    rc, out = run_cmd([str(py_path), "-c", imports], timeout=12)
    return rc == 0, out.splitlines()[-1] if out else ("OK" if rc == 0 else "import failed")


def check_hf_cache() -> list[str]:
    hub = Path.home() / ".cache" / "huggingface" / "hub"
    if not hub.exists():
        return []
    return sorted(p.name for p in hub.iterdir() if p.is_dir() and p.name.startswith("models--"))


def main():
    as_json = "--json" in sys.argv
    checks: list[dict] = []

    def add(category: str, name: str, status: str, detail: str, fix: str = ""):
        checks.append({
            "category": category,
            "name": name,
            "status": status,  # READY | PENDING | WARN
            "detail": detail,
            "fix": fix,
        })

    # 1. Hardware & Disk
    rc, gpu = run_cmd(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"])
    add("Hardware", "NVIDIA GPU", "READY" if rc == 0 and gpu else "WARN", gpu or "No NVIDIA GPU detected")

    nvenc_ok, nvenc_msg = check_nvenc()
    add("Hardware", "FFmpeg NVENC", "READY" if nvenc_ok else "WARN", nvenc_msg)

    usage = shutil.disk_usage(ROOT)
    free_gb = usage.free / (1024 ** 3)
    disk_status = "READY" if free_gb >= 50 else ("WARN" if free_gb >= 15 else "PENDING")
    add(
        "Hardware",
        "Disk Space",
        disk_status,
        f"{free_gb:.1f} GB free on workspace filesystem",
        "Free up space before downloading multiple CUDA venvs / HF checkpoints" if free_gb < 50 else "",
    )

    # 2. Core Rendering Stack
    chrome = (
        os.environ.get("CHROME_PATH")
        or shutil.which("google-chrome-stable")
        or shutil.which("google-chrome")
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
    )
    add(
        "Core Stack",
        "Headless Browser",
        "READY" if chrome else "PENDING",
        chrome or "No system Chrome/Chromium found",
        ".venv/bin/playwright install chromium" if not chrome else "",
    )

    studio_py = ROOT / ".venv" / "bin" / "python"
    ok, msg = check_python_import(
        studio_py,
        "import playwright, edge_tts, numpy, scipy, soundfile; print('playwright + edge-tts + audio libs OK')",
    )
    add("Core Stack", "Studio .venv", "READY" if ok else "PENDING", msg, "./setup.sh" if not ok else "")

    ok, msg = check_python_import(
        studio_py,
        "import cactus, streamlink, pytchat, PIL; print(f'whistle + streamlink {streamlink.__version__} + pytchat OK')",
    )
    add(
        "Core Stack",
        "Live Clipper v2",
        "READY" if ok else "PENDING",
        msg,
        "uv pip install --python .venv/bin/python cactus-compute streamlink pytchat pillow" if not ok else "",
    )

    dash_nm = ROOT / "dashboard-next" / "node_modules"
    add(
        "Core Stack",
        "Next.js Studio UI",
        "READY" if dash_nm.exists() else "PENDING",
        "dashboard-next/node_modules installed" if dash_nm.exists() else "node_modules missing",
        "cd dashboard-next && npm install" if not dash_nm.exists() else "",
    )

    # 3. Voice & Audio AI Engines
    vs_py = ROOT / "VoiceStudio" / ".venv" / "bin" / "python"
    ok, msg = check_python_import(
        vs_py,
        "import torch, fastapi, uvicorn; print(f'torch {torch.__version__}, cuda={torch.cuda.is_available()}')",
    )
    add("Voice & Audio", "VoiceStudio CUDA venv", "READY" if ok else "PENDING", msg, "./setup.sh" if not ok else "")

    vs_running = check_voicestudio_http()
    add(
        "Voice & Audio",
        "VoiceStudio Server (:3900)",
        "READY" if vs_running else "WARN",
        "Online at http://127.0.0.1:3900" if vs_running else "Offline (pipeline falls back to Edge-TTS)",
        "./scripts/start_studio.sh --with-voicestudio" if not vs_running else "",
    )

    sample = ROOT / "assets" / "voices" / "creator_sample.wav"
    add(
        "Voice & Audio",
        "Creator Voice Sample",
        "READY" if sample.exists() and sample.stat().st_size > 1000 else "PENDING",
        f"{sample.name} ({sample.stat().st_size / 1024:.0f} KB)" if sample.exists() else "Missing assets/voices/creator_sample.wav",
        "Record via Studio UI -> Voice Studio tab" if not sample.exists() else "",
    )

    cb_py = ROOT / "external" / "chatterbox" / ".venv" / "bin" / "python"
    ok, msg = check_python_import(cb_py, "import torch, chatterbox; print(f'cuda={torch.cuda.is_available()}')")
    add(
        "Optional AI Engines",
        "Chatterbox TTS",
        "READY" if ok else "PENDING",
        msg if ok else "Empty venv (packages & HF weights not installed)",
        "See WORKFLOW.md Section 1B" if not ok else "",
    )

    tf_py = ROOT / "external" / "TangoFlux" / ".venv" / "bin" / "python"
    ok, msg = check_python_import(tf_py, "import torch, tangoflux; print(f'cuda={torch.cuda.is_available()}')")
    add(
        "Optional AI Engines",
        "TangoFlux SFX",
        "READY" if ok else "PENDING",
        msg if ok else "Empty venv (packages & HF weights not installed)",
        "See WORKFLOW.md Section 1C" if not ok else "",
    )

    hf_models = check_hf_cache()
    hf_token = bool(os.environ.get("HF_TOKEN") or (Path.home() / ".cache" / "huggingface" / "token").exists())
    add(
        "Optional AI Engines",
        "HuggingFace Cache & Auth",
        "READY" if hf_models else "PENDING",
        f"{len(hf_models)} cached model(s); token={'set' if hf_token else 'not set'}",
        "Run first synthesis to download weights; set HF_TOKEN for gated models (Chatterbox-Turbo)" if not hf_models else "",
    )

    # 4. External Video Engines
    hf_built = (ROOT / "external" / "hyperframes" / "node_modules").exists()
    add(
        "Optional Video Engines",
        "HyperFrames CLI/Studio",
        "READY" if hf_built else "PENDING",
        "Installed" if hf_built else "Cloned only (not required for scripts/render_scene.py)",
        "cd external/hyperframes && bun install && bun run build" if not hf_built else "",
    )

    lemo_installed = (ROOT / "external" / "lemo-opuscar" / ".venv").exists()
    add(
        "Optional Video Engines",
        "Lemo-Opuscar Standalone",
        "READY" if lemo_installed else "PENDING",
        "Installed" if lemo_installed else "Cloned only (99 style specs already usable via styles/lemo/)",
        "sh external/lemo-opuscar/plugin/skills/lemo-opuscar/scripts/setup.sh deps" if not lemo_installed else "",
    )

    # 5. Assets & Governance
    sfx_files = list((ROOT / "assets" / "sfx").glob("*.wav")) if (ROOT / "assets" / "sfx").exists() else []
    add("Assets & Governance", "SFX Library", "READY" if sfx_files else "PENDING", f"{len(sfx_files)} WAV files in assets/sfx/")

    music_dir = ROOT / "assets" / "music"
    music_files = list(music_dir.glob("*.*")) if music_dir.exists() else []
    add(
        "Assets & Governance",
        "Background Music Beds",
        "READY" if music_files else "WARN",
        f"{len(music_files)} tracks in assets/music/" if music_files else "No assets/music/ tracks yet",
        "Add YouTube Audio Library tracks to assets/music/" if not music_files else "",
    )

    clearance = ROOT / "assets" / "clearance-log.md"
    add(
        "Assets & Governance",
        "Copyright Clearance Log",
        "READY" if clearance.exists() else "WARN",
        "Present" if clearance.exists() else "Missing assets/clearance-log.md (Rule 5)",
        "Create assets/clearance-log.md before using third-party footage/music" if not clearance.exists() else "",
    )

    if as_json:
        print(json.dumps(checks, indent=2))
        return

    icons = {"READY": "[OK]     ", "WARN": "[WARN]   ", "PENDING": "[PENDING]"}
    current_cat = None
    for c in checks:
        if c["category"] != current_cat:
            current_cat = c["category"]
            print(f"\n=== {current_cat} ===")
        print(f"  {icons[c['status']]} {c['name']:<26} {c['detail']}")
        if c["fix"]:
            print(f"             -> Fix: {c['fix']}")

    ready = sum(1 for c in checks if c["status"] == "READY")
    warn = sum(1 for c in checks if c["status"] == "WARN")
    pending = sum(1 for c in checks if c["status"] == "PENDING")
    print(f"\nSummary: {ready} READY | {warn} WARN | {pending} PENDING")


if __name__ == "__main__":
    main()
