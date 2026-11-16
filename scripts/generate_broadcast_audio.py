#!/usr/bin/env python3
"""
Broadcast Audio Engine for CreatorRadar Studio Ads
Generates studio-grade neural voiceover with parametric EQ, dynamic compression,
and precise scene synchronization.
"""

import os
import sys
import json
import subprocess
from pathlib import Path

VENV_BIN = Path("/home/varad/Videos/youtube/.venv/bin")
EDGE_TTS = VENV_BIN / "edge-tts"
FFMPEG = "ffmpeg"

def generate_voice_clip(text: str, out_path: Path, voice: str = "en-US-ChristopherNeural", rate: str = "+8%"):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(EDGE_TTS),
        "--voice", voice,
        "--rate", rate,
        "--text", text,
        "--write-media", str(out_path)
    ]
    subprocess.run(cmd, check=True)
    return out_path

def master_vocal_track(input_path: Path, output_path: Path):
    """
    Applies broadcast-standard audio mastering:
    - 75Hz high-pass filter to eliminate sub-bass rumble
    - 120Hz bell boost (+2.5dB) for warm proximity effect
    - 350Hz narrow cut (-2.0dB) to remove boxiness/mud
    - 4.5kHz presence boost (+3.0dB) for crisp vocal intelligibility
    - Studio optical compression (threshold -18dB, ratio 3.5:1, attack 15ms, release 100ms)
    - EBU R128 loudness normalization (-14 LUFS, TP -1.5dB)
    """
    filter_chain = (
        "highpass=f=75,"
        "equalizer=f=120:width_type=o:width=1.0:g=2.5,"
        "equalizer=f=350:width_type=o:width=1.5:g=-2.0,"
        "equalizer=f=4500:width_type=o:width=1.2:g=3.0,"
        "acompressor=threshold=-18dB:ratio=3.5:attack=15:release=100,"
        "loudnorm=I=-14:LRA=7:TP=-1.5"
    )
    cmd = [
        FFMPEG, "-y",
        "-i", str(input_path),
        "-af", filter_chain,
        "-ar", "48000",
        "-ac", "2",
        str(output_path)
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_path

def build_timeline_audio(beats, total_duration: float, output_path: Path, voice: str = "en-US-ChristopherNeural", rate: str = "+8%"):
    """
    beats: list of dicts: [{"text": str, "start": float, "id": str}]
    """
    temp_dir = Path("/tmp/studio_audio_build")
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    inputs = []
    filter_complex = []
    
    # Generate each beat
    for i, b in enumerate(beats):
        raw_clip = temp_dir / f"beat_{i}_raw.mp3"
        mastered_clip = temp_dir / f"beat_{i}_master.wav"
        print(f"Generating Beat {i+1}: '{b['text']}'...")
        generate_voice_clip(b["text"], raw_clip, voice=voice, rate=rate)
        master_vocal_track(raw_clip, mastered_clip)
        
        inputs.extend(["-i", str(mastered_clip)])
        # Delay to start time in ms
        delay_ms = int(b["start"] * 1000)
        filter_complex.append(f"[{i}]adelay={delay_ms}|{delay_ms}[a{i}];")

    mix_inputs = "".join(f"[a{i}]" for i in range(len(beats)))
    silence_cmd = f"aevalsrc=0:d={total_duration}:s=48000:c=stereo[silence];"
    mix_filter = f"{''.join(filter_complex)}{silence_cmd}[silence]{mix_inputs}amix=inputs={len(beats)+1}:duration=longest:dropout_transition=0,loudnorm=I=-14:LRA=7:TP=-1.5[out]"

    cmd = [
        FFMPEG, "-y",
        *inputs,
        "-filter_complex", mix_filter,
        "-map", "[out]",
        "-ar", "48000",
        "-ac", "2",
        str(output_path)
    ]
    subprocess.run(cmd, check=True)
    print(f"Successfully rendered synchronized audio master: {output_path}")
    return output_path

if __name__ == "__main__":
    print("Broadcast Audio Engine loaded.")
