#!/usr/bin/env python3
"""
Broadcast Audio Engine for CreatorRadar Studio
Synthesizes per-beat narration via VoiceStudio (with neural Edge-TTS fallback),
measures exact beat durations, applies broadcast mastering (-14 LUFS), and
mixes synchronized SFX transitions from assets/sfx/.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

WORKSPACE_ROOT = Path(os.environ.get("WORKSPACE_ROOT", Path(__file__).resolve().parent.parent))
SFX_DIR = WORKSPACE_ROOT / "assets" / "sfx"

# Ensure sibling imports work whether run as script or imported as module
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from voice_studio_client import (  # noqa: E402
    DEFAULT_EDGE_RATE,
    DEFAULT_EDGE_VOICE,
    DEFAULT_PROFILE_ID,
    generate_narration,
    master_audio,
)


def probe_duration(audio_path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(res.stdout.strip())


def build_synced_beat_audio(
    beats: list[dict],
    output_path: Path,
    voice_id: str = DEFAULT_PROFILE_ID,
    edge_voice: str = DEFAULT_EDGE_VOICE,
    rate: str = DEFAULT_EDGE_RATE,
    gap_sec: float = 0.22,
    lead_in_sec: float = 0.25,
    tail_sec: float = 0.65,
    include_sfx: bool = True,
    sfx_gain_db: float = -12.0,
) -> dict:
    """
    Synthesize each beat individually so we know exact start/end timestamps
    for frame-accurate visual cuts, kinetic captions, and SFX hits.

    beats: list of dicts with at least {"text": str} and optional {"id", "sfx"}
    Returns dict with output path, total_duration, engine, and timed_beats list.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    sfx_cycle = ["impact.wav", "whoosh.wav", "click.wav", "whoosh.wav", "riser.wav"]

    with tempfile.TemporaryDirectory(prefix="creatorradar_audio_") as tmp:
        tmp_dir = Path(tmp)
        inputs: list[str] = []
        filter_parts: list[str] = []
        mix_labels: list[str] = []
        timed_beats: list[dict] = []
        engines_used: set[str] = set()

        cursor = lead_in_sec
        input_idx = 0

        for i, beat in enumerate(beats):
            text = beat["text"].strip()
            clip_path = tmp_dir / f"beat_{i:02d}.wav"
            res = generate_narration(
                text,
                clip_path,
                voice_name=voice_id,
                edge_voice=edge_voice,
                rate=rate,
            )
            engines_used.add(res["engine"])
            dur = probe_duration(clip_path)

            start_t = round(cursor, 3)
            end_t = round(cursor + dur, 3)

            timed_entry = dict(beat)
            timed_entry["start"] = start_t
            timed_entry["end"] = end_t
            timed_entry["duration"] = round(dur, 3)
            timed_beats.append(timed_entry)

            inputs.extend(["-i", str(clip_path)])
            delay_ms = int(round(start_t * 1000))
            filter_parts.append(f"[{input_idx}:a]adelay={delay_ms}|{delay_ms}[v{i}];")
            mix_labels.append(f"[v{i}]")
            input_idx += 1

            # Optional SFX transition accent at beat entry
            if include_sfx and SFX_DIR.exists():
                sfx_name = beat.get("sfx") or sfx_cycle[i % len(sfx_cycle)]
                sfx_file = SFX_DIR / sfx_name
                if sfx_file.exists():
                    sfx_t = max(0.0, start_t - 0.06)
                    sfx_ms = int(round(sfx_t * 1000))
                    inputs.extend(["-i", str(sfx_file)])
                    filter_parts.append(
                        f"[{input_idx}:a]aresample=48000,aformat=channel_layouts=stereo,"
                        f"volume={sfx_gain_db}dB,adelay={sfx_ms}|{sfx_ms}[s{i}];"
                    )
                    mix_labels.append(f"[s{i}]")
                    input_idx += 1

            cursor = end_t + gap_sec

        total_duration = round(cursor + tail_sec, 3)

        silence = f"aevalsrc=0:d={total_duration}:s=48000:c=stereo[base];"
        all_labels = "[base]" + "".join(mix_labels)
        n_inputs = len(mix_labels) + 1

        # normalize=0 prevents amix from dividing voice volume by N inputs; loudnorm masters to -14 LUFS
        filter_complex = (
            "".join(filter_parts)
            + silence
            + f"{all_labels}amix=inputs={n_inputs}:duration=first:dropout_transition=0:normalize=0,"
            + "alimiter=limit=0.92,loudnorm=I=-14:LRA=7:TP=-1.5[out]"
        )

        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-ar", "48000",
            "-ac", "2",
            str(output_path),
        ]
        subprocess.run(cmd, check=True)

    actual_duration = probe_duration(output_path)
    return {
        "audio_path": str(output_path),
        "duration": round(actual_duration, 3),
        "engines": sorted(engines_used),
        "sfx_enabled": include_sfx,
        "beats": timed_beats,
    }


def main():
    parser = argparse.ArgumentParser(description="Build mastered beat-synced broadcast audio with SFX")
    parser.add_argument("beats_json", help="Path to JSON file containing a list of beat objects")
    parser.add_argument("output_wav", help="Output master WAV file")
    parser.add_argument("--voice", default=DEFAULT_PROFILE_ID)
    parser.add_argument("--edge-voice", default=DEFAULT_EDGE_VOICE)
    parser.add_argument("--no-sfx", action="store_true")
    args = parser.parse_args()

    beats = json.loads(Path(args.beats_json).read_text(encoding="utf-8"))
    result = build_synced_beat_audio(
        beats=beats,
        output_path=Path(args.output_wav),
        voice_id=args.voice,
        edge_voice=args.edge_voice,
        include_sfx=not args.no_sfx,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
