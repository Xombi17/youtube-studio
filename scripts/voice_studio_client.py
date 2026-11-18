#!/usr/bin/env python3
"""
VoiceStudio Local API Client for CreatorRadar
Connects to VoiceStudio at http://localhost:3900 to synthesize speech
using the channel owner's cloned voice profile, with automatic fallback to
local neural Edge-TTS and broadcast audio mastering (-14 LUFS).
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

VOICE_STUDIO_URL = os.environ.get("VOICESTUDIO_URL", "http://localhost:3900").rstrip("/")
WORKSPACE_ROOT = Path(os.environ.get("WORKSPACE_ROOT", Path(__file__).resolve().parent.parent))
VOICE_SAMPLE_DIR = Path(os.environ.get("VOICE_SAMPLE_DIR", WORKSPACE_ROOT / "assets" / "voices"))
VOICE_SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_PROFILE_ID = os.environ.get("CREATOR_VOICE_PROFILE", "creator_default")
DEFAULT_EDGE_VOICE = os.environ.get("CREATOR_EDGE_VOICE", "en-IN-PrabhatNeural")
DEFAULT_EDGE_RATE = os.environ.get("CREATOR_EDGE_RATE", "+10%")

BROADCAST_FILTER_CHAIN = (
    "highpass=f=75,"
    "equalizer=f=120:width_type=o:width=1.0:g=2.5,"
    "equalizer=f=350:width_type=o:width=1.5:g=-2.0,"
    "equalizer=f=4500:width_type=o:width=1.2:g=3.0,"
    "acompressor=threshold=-18dB:ratio=3.5:attack=15:release=100,"
    "loudnorm=I=-14:LRA=7:TP=-1.5"
)


def _auth_headers(extra: dict | None = None) -> dict[str, str]:
    headers = {"User-Agent": "CreatorRadar/2.0"}
    api_key = os.environ.get("OMNIVOICE_API_KEY") or os.environ.get("VOICESTUDIO_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if extra:
        headers.update(extra)
    return headers


def is_voicestudio_running(timeout: float = 2.0) -> bool:
    for path in ("/health", "/api/health", "/v1/models"):
        try:
            req = urllib.request.Request(f"{VOICE_STUDIO_URL}{path}", headers=_auth_headers())
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            continue
    return False


def list_voicestudio_profiles(timeout: float = 3.0) -> list[dict]:
    for path in ("/api/voices", "/voices", "/profiles", "/v1/audio/voices"):
        try:
            req = urllib.request.Request(f"{VOICE_STUDIO_URL}{path}", headers=_auth_headers())
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    payload = json.loads(resp.read().decode("utf-8", errors="replace"))
                    if isinstance(payload, list):
                        return payload
                    if isinstance(payload, dict):
                        for key in ("voices", "profiles", "items", "data"):
                            if isinstance(payload.get(key), list):
                                return payload[key]
        except Exception:
            continue
    return []


def resolve_edge_tts_cmd() -> list[str] | None:
    venv_bin = WORKSPACE_ROOT / ".venv" / "bin" / "edge-tts"
    if venv_bin.exists():
        return [str(venv_bin)]
    system_bin = shutil.which("edge-tts")
    if system_bin:
        return [system_bin]
    venv_py = WORKSPACE_ROOT / ".venv" / "bin" / "python"
    if venv_py.exists():
        return [str(venv_py), "-m", "edge_tts"]
    return None


def master_audio(input_path: Path, output_path: Path) -> Path:
    """Apply broadcast EQ, compression, and -14 LUFS loudness normalization."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = output_path.with_suffix(".master.tmp.wav")
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(input_path),
        "-af", BROADCAST_FILTER_CHAIN,
        "-ar", "48000",
        "-ac", "2",
        str(tmp_out),
    ]
    subprocess.run(cmd, check=True)
    tmp_out.replace(output_path)
    return output_path


def synthesize_with_voicestudio(text: str, out_path: Path, voice_id: str = DEFAULT_PROFILE_ID, speed: float = 1.05) -> bool:
    raw_wav = out_path.with_suffix(".vs_raw.wav")
    # 1. OpenAI-compatible /v1/audio/speech
    payload = json.dumps({
        "model": "omnivoice",
        "input": text,
        "voice": voice_id,
        "response_format": "wav",
        "speed": speed,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{VOICE_STUDIO_URL}/v1/audio/speech",
        data=payload,
        headers=_auth_headers({"Content-Type": "application/json"}),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
            if len(data) > 1000 and not data.startswith(b'{"detail"'):
                raw_wav.write_bytes(data)
                master_audio(raw_wav, out_path)
                raw_wav.unlink(missing_ok=True)
                return True
    except Exception as e:
        print(f"[VoiceStudio] /v1/audio/speech attempt failed: {e}", flush=True)

    # 2. Multipart /generate fallback
    boundary = "----CreatorRadarVoiceStudioBoundary"
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="text"\r\n\r\n{text}\r\n',
        f'--{boundary}\r\nContent-Disposition: form-data; name="profile_id"\r\n\r\n{voice_id}\r\n',
        f'--{boundary}\r\nContent-Disposition: form-data; name="speed"\r\n\r\n{speed}\r\n',
        f"--{boundary}--\r\n",
    ]
    data_bytes = "".join(parts).encode("utf-8")
    req2 = urllib.request.Request(
        f"{VOICE_STUDIO_URL}/generate",
        data=data_bytes,
        headers=_auth_headers({"Content-Type": f"multipart/form-data; boundary={boundary}"}),
        method="POST",
    )
    with urllib.request.urlopen(req2, timeout=120) as resp:
        data = resp.read()
        if len(data) > 1000 and not data.startswith(b'{"detail"'):
            raw_wav.write_bytes(data)
            master_audio(raw_wav, out_path)
            raw_wav.unlink(missing_ok=True)
            return True
        raise RuntimeError(f"VoiceStudio returned invalid audio: {data[:200]!r}")


def fallback_local_tts(text: str, out_path: Path, edge_voice: str = DEFAULT_EDGE_VOICE, rate: str = DEFAULT_EDGE_RATE) -> str:
    edge_cmd = resolve_edge_tts_cmd()
    if edge_cmd:
        temp_mp3 = out_path.with_suffix(".edge.tmp.mp3")
        try:
            cmd = [
                *edge_cmd,
                "--voice", edge_voice,
                "--rate", rate,
                "--text", text,
                "--write-media", str(temp_mp3),
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            master_audio(temp_mp3, out_path)
            temp_mp3.unlink(missing_ok=True)
            return f"edge-tts ({edge_voice})"
        except Exception as e:
            print(f"[Fallback TTS] Edge-TTS failed ({e}); falling back to espeak-ng.", flush=True)
            temp_mp3.unlink(missing_ok=True)

    espeak = shutil.which("espeak-ng") or shutil.which("espeak")
    if not espeak:
        raise RuntimeError("No TTS backend available (VoiceStudio offline, edge-tts failed, espeak-ng missing).")

    raw_wav = out_path.with_suffix(".espeak.tmp.wav")
    subprocess.run([espeak, "-v", "en-us", "-s", "165", "-p", "48", "-w", str(raw_wav), text], check=True)
    master_audio(raw_wav, out_path)
    raw_wav.unlink(missing_ok=True)
    return "espeak-ng"


def generate_narration(
    text: str,
    out_path: str | Path,
    voice_name: str = DEFAULT_PROFILE_ID,
    edge_voice: str = DEFAULT_EDGE_VOICE,
    rate: str = DEFAULT_EDGE_RATE,
    speed: float = 1.05,
) -> dict:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    engine_used = None
    if is_voicestudio_running():
        try:
            print(f"[VoiceStudio] Synthesizing cloned speech via profile '{voice_name}'...", flush=True)
            synthesize_with_voicestudio(text, out_path, voice_id=voice_name, speed=speed)
            engine_used = f"voicestudio ({voice_name})"
            print(f"[VoiceStudio] Generated & mastered cloned voice: {out_path}", flush=True)
        except Exception as e:
            print(f"[VoiceStudio] Synthesis failed ({e}). Falling back to local neural TTS.", flush=True)
    else:
        print(f"[VoiceStudio] Not reachable at {VOICE_STUDIO_URL}. Using local neural TTS fallback.", flush=True)

    if not engine_used:
        engine_used = fallback_local_tts(text, out_path, edge_voice=edge_voice, rate=rate)
        print(f"[TTS] Generated & mastered narration via {engine_used}: {out_path}", flush=True)

    return {"path": str(out_path), "engine": engine_used, "voicestudio_active": engine_used.startswith("voicestudio")}


def main():
    parser = argparse.ArgumentParser(description="CreatorRadar VoiceStudio Client")
    parser.add_argument("text", nargs="?", help="Text to synthesize")
    parser.add_argument("out_path", nargs="?", help="Output WAV path")
    parser.add_argument("voice_id", nargs="?", default=DEFAULT_PROFILE_ID, help="VoiceStudio profile ID")
    parser.add_argument("--edge-voice", default=DEFAULT_EDGE_VOICE)
    parser.add_argument("--rate", default=DEFAULT_EDGE_RATE)
    parser.add_argument("--health", action="store_true", help="Check VoiceStudio health & profiles as JSON")
    args = parser.parse_args()

    if args.health:
        running = is_voicestudio_running()
        profiles = list_voicestudio_profiles() if running else []
        sample = VOICE_SAMPLE_DIR / "creator_sample.wav"
        print(json.dumps({
            "url": VOICE_STUDIO_URL,
            "running": running,
            "profiles": profiles,
            "has_creator_sample": sample.exists() and sample.stat().st_size > 1000,
            "creator_sample_path": str(sample),
            "edge_tts_available": resolve_edge_tts_cmd() is not None,
        }, indent=2))
        return

    if not args.text or not args.out_path:
        parser.print_help()
        sys.exit(1)

    generate_narration(args.text, args.out_path, voice_name=args.voice_id, edge_voice=args.edge_voice, rate=args.rate)


if __name__ == "__main__":
    main()
