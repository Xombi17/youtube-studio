#!/usr/bin/env python3
"""
VoiceStudio Local API Client for CreatorRadar
Connects to VoiceStudio at http://localhost:3900 to synthesize speech
using your cloned voice, with automatic fallback to local TTS.
"""

import sys
import os
import json
import urllib.request
import urllib.error
import subprocess
from pathlib import Path

VOICE_STUDIO_URL = os.environ.get("VOICESTUDIO_URL", "http://localhost:3900")
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
VOICE_SAMPLE_DIR = Path(os.environ.get("VOICE_SAMPLE_DIR", WORKSPACE_ROOT / "assets" / "voices"))
VOICE_SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_PROFILE_ID = os.environ.get("CREATOR_VOICE_PROFILE", "cb77bfeb")

def is_voicestudio_running():
    try:
        req = urllib.request.Request(f"{VOICE_STUDIO_URL}/health", headers={"User-Agent": "CreatorRadar/1.0"})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            return resp.status == 200
    except Exception:
        return False

def synthesize_with_voicestudio(text, out_path, voice_id=DEFAULT_PROFILE_ID):
    # Try OpenAI-compatible /v1/audio/speech first
    payload = json.dumps({
        "model": "omnivoice",
        "input": text,
        "voice": voice_id,
        "response_format": "wav",
        "speed": 1.05
    }).encode("utf-8")
    
    req = urllib.request.Request(
        f"{VOICE_STUDIO_URL}/v1/audio/speech",
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "CreatorRadar/1.0"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
            if len(data) > 1000 and not data.startswith(b'{"detail"'):
                with open(out_path, "wb") as f:
                    f.write(data)
                return True
    except Exception as e:
        print(f"[VoiceStudio] /v1/audio/speech attempt failed: {e}")

    # Fallback to direct /generate endpoint
    boundary = "----VoiceStudioClientBoundary"
    body = []
    body.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"text\"\r\n\r\n{text}\r\n")
    body.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"profile_id\"\r\n\r\n{voice_id}\r\n")
    body.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"speed\"\r\n\r\n1.05\r\n")
    body.append(f"--{boundary}--\r\n")
    data_bytes = "".join(body).encode("utf-8")
    
    req2 = urllib.request.Request(
        f"{VOICE_STUDIO_URL}/generate",
        data=data_bytes,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "CreatorRadar/1.0"
        },
        method="POST"
    )
    with urllib.request.urlopen(req2, timeout=120) as resp:
        data = resp.read()
        if len(data) > 1000 and not data.startswith(b'{"detail"'):
            with open(out_path, "wb") as f:
                f.write(data)
            return True
        else:
            raise RuntimeError(f"VoiceStudio returned invalid audio: {data[:200]}")

def fallback_local_tts(text, out_path):
    cmd = ["espeak-ng", "-v", "en-us", "-s", "150", "-p", "50", "-w", str(out_path), text]
    subprocess.run(cmd, check=True)

def generate_narration(text, out_path, voice_name=DEFAULT_PROFILE_ID):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    if is_voicestudio_running():
        try:
            print(f"[VoiceStudio] Synthesizing cloned speech via profile '{voice_name}'...")
            synthesize_with_voicestudio(text, out_path, voice_id=voice_name)
            print(f"[VoiceStudio] Successfully generated cloned voice: {out_path}")
            return out_path
        except Exception as e:
            print(f"[VoiceStudio] Generation failed: {e}. Falling back to local TTS.")
    else:
        print("[VoiceStudio] Service not reachable at http://localhost:3900. Falling back to local TTS.")
        
    fallback_local_tts(text, out_path)
    print(f"[TTS] Generated fallback narration: {out_path}")
    return out_path

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: voice_studio_client.py <text> <out_path.wav> [voice_id]")
        sys.exit(1)
    text = sys.argv[1]
    out_path = sys.argv[2]
    voice = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_PROFILE_ID
    generate_narration(text, out_path, voice)
