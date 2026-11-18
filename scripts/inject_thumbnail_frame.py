#!/usr/bin/env python3
"""
CreatorRadar — 2026 Shorts 1-Frame Thumbnail Injector

Injects a high-contrast thumbnail card into a vertical video (9:16, 1080x1920)
for exactly 1-2 frames (default: 0.04s) at the start or tail of the timeline.

This allows creators to pick a clickable custom thumbnail via the YouTube Mobile App
pencil icon, unlocking YouTube Browse Features (Home Tab) recommendations and 2x-5x views.

Usage:
    .venv/bin/python scripts/inject_thumbnail_frame.py input.mp4 thumbnail.png [output.mp4]
    .venv/bin/python scripts/inject_thumbnail_frame.py input.mp4 thumbnail.png --position start --frames 2
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path


def inject_thumbnail(
    video_path: Path,
    thumb_path: Path,
    output_path: Path | None = None,
    position: str = "start",
    duration_sec: float = 0.04,
) -> Path:
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")
    if not thumb_path.exists():
        raise FileNotFoundError(f"Thumbnail image not found: {thumb_path}")

    if output_path is None:
        output_path = video_path.with_name(f"{video_path.stem}_thumb_ready.mp4")

    # Probe input video FPS and resolution
    probe_cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate",
        "-of", "csv=p=0",
        str(video_path),
    ]
    res = subprocess.check_output(probe_cmd, text=True).strip().split(",")
    width = int(res[0]) if len(res) > 0 and res[0] else 1080
    height = int(res[1]) if len(res) > 1 and res[1] else 1920
    fps_raw = res[2] if len(res) > 2 and res[2] else "30/1"

    print(f"[*] Target video: {width}x{height} @ {fps_raw} fps")
    print(f"[*] Ingesting thumbnail: {thumb_path} ({duration_sec}s at {position})")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_thumb_video = Path(tmp_dir) / "thumb_clip.mp4"
        # 1. Render thumbnail image into matching video slice without audio
        render_thumb_cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-t", str(duration_sec),
            "-i", str(thumb_path),
            "-vf", f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1",
            "-r", fps_raw,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            str(tmp_thumb_video),
        ]
        subprocess.check_call(render_thumb_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # 2. Concat thumbnail slice with video using filter_complex
        if position == "start":
            filter_str = (
                f"[0:v][1:v]concat=n=2:v=1:a=0[v_out];"
                f"[1:a]apad=pad_dur={duration_sec}[a_shifted]"
            )
            concat_cmd = [
                "ffmpeg", "-y",
                "-i", str(tmp_thumb_video),
                "-i", str(video_path),
                "-filter_complex", filter_str,
                "-map", "[v_out]",
                "-map", "[a_shifted]",
                "-c:v", "libx264",
                "-crf", "18",
                "-preset", "fast",
                "-c:a", "aac",
                "-b:a", "192k",
                "-movflags", "+faststart",
                str(output_path),
            ]
        else:  # tail
            filter_str = "[0:v][1:v]concat=n=2:v=1:a=0[v_out]"
            concat_cmd = [
                "ffmpeg", "-y",
                "-i", str(video_path),
                "-i", str(tmp_thumb_video),
                "-filter_complex", filter_str,
                "-map", "[v_out]",
                "-map", "0:a?",
                "-c:v", "libx264",
                "-crf", "18",
                "-preset", "fast",
                "-c:a", "aac",
                "-b:a", "192k",
                "-movflags", "+faststart",
                str(output_path),
            ]

        subprocess.check_call(concat_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print(f"[OK] Injected thumbnail. Output ready for mobile upload: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="2026 Shorts 1-Frame Thumbnail Injector")
    parser.add_argument("video", type=Path, help="Input vertical MP4 file")
    parser.add_argument("thumbnail", type=Path, help="High-contrast 1080x1920 thumbnail image")
    parser.add_argument("output", type=Path, nargs="?", default=None, help="Output MP4 path")
    parser.add_argument("--position", choices=["start", "end"], default="start", help="Insert at start or end (default: start)")
    parser.add_argument("--duration", type=float, default=0.04, help="Duration in seconds (default: 0.04s ~ 1-2 frames)")
    args = parser.parse_args()

    inject_thumbnail(
        video_path=args.video,
        thumb_path=args.thumbnail,
        output_path=args.output,
        position=args.position,
        duration_sec=args.duration,
    )


if __name__ == "__main__":
    main()
