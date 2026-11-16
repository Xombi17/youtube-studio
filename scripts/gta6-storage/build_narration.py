#!/usr/bin/env python3
"""
Synthesizes and mixes a 45-second timed voiceover for GTA VI Storage Requirements.
Uses espeak-ng and ffmpeg to assemble precisely timed beats.
"""

import os
import subprocess
from pathlib import Path

ROOT = Path(os.environ.get("WORKSPACE_ROOT", Path(__file__).resolve().parent.parent.parent))
OUT_DIR = ROOT / "gta6-storage-short" / "assets"
OUT_DIR.mkdir(parents=True, exist_ok=True)
RENDERS_AUDIO_DIR = ROOT / "renders" / "gta6-storage" / "audio"
RENDERS_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

BEATS = [
    {
        "id": "beat0",
        "start": 0.5,
        "text": "GTA 6 needs 212 gigabytes. Here is what that means for your PS5."
    },
    {
        "id": "beat1",
        "start": 5.5,
        "text": "Your PS5 has about 825 gigs of usable storage. GTA 6 alone takes up over a quarter of your entire drive."
    },
    {
        "id": "beat2",
        "start": 14.8,
        "text": "Three ways to free space fast. One: delete unused games. Two: move saves to USB or cloud. Three: install an M.2 NVMe SSD."
    },
    {
        "id": "beat3",
        "start": 27.5,
        "text": "Preloading started November 10th. It is 210 gigs, so start your download now and be ready for midnight launch."
    },
    {
        "id": "beat4",
        "start": 38.5,
        "text": "Follow CreatorRadar for daily verified GTA 6 guides before launch day."
    }
]

TOTAL_DURATION = 45.0
temp_files = []

# Generate each beat
for b in BEATS:
    wav_path = OUT_DIR / f"{b['id']}.wav"
    # Generate speech with espeak-ng en-us voice, natural pacing
    cmd = [
        "espeak-ng",
        "-v", "en-us",
        "-s", "150",
        "-p", "50",
        "-w", str(wav_path),
        b["text"]
    ]
    subprocess.run(cmd, check=True)
    temp_files.append((b["start"], wav_path))

# Now create an ffmpeg complex filter to position each clip at its exact timestamp
# over a 45s silent background
filter_inputs = ["-f", "lavfi", "-t", str(TOTAL_DURATION), "-i", "anullsrc=r=48000:cl=stereo"]
for _, path in temp_files:
    filter_inputs.extend(["-i", str(path)])

# Build filter_complex graph
adelay_parts = []
mix_inputs = ["[0:a]"]
for i, (start_sec, _) in enumerate(temp_files, 1):
    delay_ms = int(start_sec * 1000)
    adelay_parts.append(f"[{i}:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,adelay={delay_ms}|{delay_ms}[d{i}]")
    mix_inputs.append(f"[d{i}]")

filter_str = ";".join(adelay_parts) + ";" + "".join(mix_inputs) + f"amix=inputs={len(mix_inputs)}:duration=first:dropout_transition=0[outa]"

final_wav = OUT_DIR / "voiceover_tts.wav"
render_wav = RENDERS_AUDIO_DIR / "narration.wav"

ffmpeg_cmd = [
    "ffmpeg", "-y",
    *filter_inputs,
    "-filter_complex", filter_str,
    "-map", "[outa]",
    "-c:a", "pcm_s16le",
    "-t", str(TOTAL_DURATION),
    str(final_wav)
]

subprocess.run(ffmpeg_cmd, check=True)

# Copy to renders directory as well
subprocess.run(["cp", str(final_wav), str(render_wav)], check=True)
print(f"Generated 45s voiceover at {final_wav} and {render_wav}")
