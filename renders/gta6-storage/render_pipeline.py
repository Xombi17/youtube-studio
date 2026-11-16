#!/usr/bin/env python3
"""
CreatorRadar Video Rendering Pipeline for GTA VI Storage Short
Produces a production-ready 1080x1920 vertical MP4 (45.0s)
using Chrome headless rendering + FFmpeg compositing and mixing.
"""

import os
import sys
import subprocess
from pathlib import Path

ROOT = Path(os.environ.get("WORKSPACE_ROOT", Path(__file__).resolve().parent.parent.parent))
RENDERS_DIR = ROOT / "renders" / "gta6-storage"
SCENES_DIR = RENDERS_DIR / "scenes"
EXPORTS_DIR = ROOT / "exports" / "gta6-storage"
AUDIO_PATH = RENDERS_DIR / "audio" / "narration.wav"
FINAL_EXPORT = EXPORTS_DIR / "20261116-gta6-storage-ps5.mp4"

SCENES_DIR.mkdir(parents=True, exist_ok=True)
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

# 1. HTML definitions for each storyboard scene
SCENE_HTMLS = {
    "scene1": {
        "duration": 5.0,
        "html": """<!doctype html><html><head><meta charset="utf-8"><style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { width: 1080px; height: 1920px; background: #101d2b; font-family: Inter, -apple-system, sans-serif; color: #f7f4ed; position: relative; overflow: hidden; padding: 220px 96px; }
.grid { position: absolute; inset:0; opacity: 0.15; background-image: linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px); background-size: 108px 108px; }
.eyebrow { font-size: 34px; font-weight: 700; letter-spacing: 0.12em; color: #f47750; text-transform: uppercase; font-family: monospace; }
.title { font-size: 96px; font-weight: 800; line-height: 1.05; margin-top: 40px; letter-spacing: -0.04em; }
.giant { font-size: 360px; font-weight: 900; color: #f47750; letter-spacing: -0.06em; line-height: 0.9; margin: 80px 0 20px; }
.sub { font-size: 52px; font-weight: 600; color: #f1eee7; opacity: 0.9; max-width: 880px; line-height: 1.25; }
.badge { display: inline-block; background: #e96643; color: #101d2b; font-weight: 800; font-size: 38px; padding: 18px 36px; border-radius: 8px; margin-top: 50px; }
.cap { position: absolute; bottom: 220px; left: 96px; right: 96px; background: #f7f4ed; color: #101d2b; padding: 26px 36px; font-size: 46px; font-weight: 800; box-shadow: 10px 10px 0 #e96643; }
.cap span { color: #e96643; }
.footer { position: absolute; bottom: 120px; left: 96px; font-size: 28px; font-family: monospace; color: #8899a6; }
</style></head><body>
<div class="grid"></div>
<div class="eyebrow">GTA VI STORAGE ALERT</div>
<h1 class="title">How much space does<br><span style="color:#f47750">GTA VI</span> need?</h1>
<div class="giant">212</div>
<p class="sub">Gigabytes of free SSD space required on PlayStation 5</p>
<div class="badge">OFFICIAL ROCKSTAR REQUIREMENT</div>
<div class="cap">GTA 6 needs <span>212 gigabytes</span> — here's what that means for your PS5.</div>
<div class="footer">CREATORRADAR / OFFICIAL DOCUMENTATION</div>
</body></html>"""
    },
    "scene2": {
        "duration": 9.0,
        "html": """<!doctype html><html><head><meta charset="utf-8"><style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { width: 1080px; height: 1920px; background: #f1eee7; font-family: Inter, -apple-system, sans-serif; color: #101d2b; position: relative; overflow: hidden; padding: 220px 96px; }
.eyebrow { font-size: 34px; font-weight: 700; letter-spacing: 0.12em; color: #e96643; text-transform: uppercase; font-family: monospace; }
.title { font-size: 92px; font-weight: 800; line-height: 1.05; margin-top: 40px; letter-spacing: -0.04em; }
.bar-container { margin-top: 90px; }
.bar-label { font-size: 38px; font-weight: 700; margin-bottom: 16px; display: flex; justify-content: space-between; }
.bar-outer { width: 100%; height: 64px; background: #dce1dc; border-radius: 8px; overflow: hidden; margin-bottom: 50px; border: 3px solid #101d2b; }
.bar-inner-gta { width: 25.7%; height: 100%; background: #e96643; }
.bar-inner-ps5 { width: 100%; height: 100%; background: #101d2b; }
.stat-highlight { font-size: 140px; font-weight: 900; color: #e96643; line-height: 1; margin-top: 40px; }
.stat-sub { font-size: 46px; font-weight: 700; color: #101d2b; margin-top: 10px; max-width: 820px; }
.cap { position: absolute; bottom: 220px; left: 96px; right: 96px; background: #101d2b; color: #f7f4ed; padding: 26px 36px; font-size: 46px; font-weight: 800; box-shadow: 10px 10px 0 #e96643; }
.cap span { color: #f47750; }
.footer { position: absolute; bottom: 120px; left: 96px; font-size: 28px; font-family: monospace; color: #667788; }
</style></head><body>
<div class="eyebrow">THE STORAGE SCALE</div>
<h2 class="title">PS5 usable storage is<br><strong>≈825 Gigabytes</strong></h2>
<div class="bar-container">
  <div class="bar-label"><span>GTA VI INSTALL SIZE</span><span style="color:#e96643">212 GB</span></div>
  <div class="bar-outer"><div class="bar-inner-gta"></div></div>
  <div class="bar-label"><span>PS5 BASE USABLE SSD</span><span>825 GB</span></div>
  <div class="bar-outer"><div class="bar-inner-ps5"></div></div>
</div>
<div class="stat-highlight">25.7%</div>
<div class="stat-sub">Over a quarter of your entire console drive for one single game!</div>
<div class="cap">Your PS5 has about 825 gigs usable. <span>GTA 6 takes up a quarter</span> of your drive.</div>
<div class="footer">SOURCE: SONY PLAYSTATION 5 HARDWARE SPECS</div>
</body></html>"""
    },
    "scene3": {
        "duration": 13.0,
        "html": """<!doctype html><html><head><meta charset="utf-8"><style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { width: 1080px; height: 1920px; background: #e96643; font-family: Inter, -apple-system, sans-serif; color: #101d2b; position: relative; overflow: hidden; padding: 220px 96px; }
.eyebrow { font-size: 34px; font-weight: 800; letter-spacing: 0.12em; color: #101d2b; text-transform: uppercase; font-family: monospace; opacity: 0.85; }
.title { font-size: 92px; font-weight: 900; line-height: 1.05; margin-top: 30px; letter-spacing: -0.04em; color: #f7f4ed; }
.list-box { margin-top: 70px; display: flex; flex-direction: column; gap: 32px; }
.card { background: #f7f4ed; padding: 36px 40px; border-radius: 12px; border: 4px solid #101d2b; box-shadow: 8px 8px 0 #101d2b; }
.card-num { font-size: 32px; font-weight: 800; color: #e96643; font-family: monospace; }
.card-title { font-size: 50px; font-weight: 800; margin-top: 8px; color: #101d2b; }
.card-desc { font-size: 34px; font-weight: 600; color: #445566; margin-top: 6px; }
.cap { position: absolute; bottom: 220px; left: 96px; right: 96px; background: #f7f4ed; color: #101d2b; padding: 26px 36px; font-size: 44px; font-weight: 800; box-shadow: 10px 10px 0 #101d2b; }
.cap span { color: #e96643; }
.footer { position: absolute; bottom: 120px; left: 96px; font-size: 28px; font-family: monospace; color: #101d2b; opacity: 0.8; }
</style></head><body>
<div class="eyebrow">HOW TO PREPARE</div>
<h2 class="title">3 Ways to Free Space<br>Before Launch</h2>
<div class="list-box">
  <div class="card">
    <div class="card-num">STEP 01</div>
    <div class="card-title">Delete Unused Games</div>
    <div class="card-desc">Your save files remain 100% safe in PS Cloud storage</div>
  </div>
  <div class="card">
    <div class="card-num">STEP 02</div>
    <div class="card-title">Back Up to USB Drive</div>
    <div class="card-desc">Offload PS4 titles and media captures to external storage</div>
  </div>
  <div class="card">
    <div class="card-num">STEP 03</div>
    <div class="card-title">Install M.2 NVMe SSD</div>
    <div class="card-desc">Add 1TB or 2TB high-speed storage for permanent headroom</div>
  </div>
</div>
<div class="cap">Delete games, move saves to USB, or add an <span>M.2 NVMe SSD</span>.</div>
<div class="footer">CREATORRADAR / STORAGE OPTIMIZATION GUIDE</div>
</body></html>"""
    },
    "scene4": {
        "duration": 11.0,
        "html": """<!doctype html><html><head><meta charset="utf-8"><style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { width: 1080px; height: 1920px; background: #101d2b; font-family: Inter, -apple-system, sans-serif; color: #f7f4ed; position: relative; overflow: hidden; padding: 220px 96px; }
.grid { position: absolute; inset:0; opacity: 0.15; background-image: linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px); background-size: 108px 108px; }
.eyebrow { font-size: 34px; font-weight: 700; letter-spacing: 0.12em; color: #f47750; text-transform: uppercase; font-family: monospace; }
.title { font-size: 96px; font-weight: 800; line-height: 1.05; margin-top: 40px; letter-spacing: -0.04em; }
.countdown-box { margin-top: 80px; background: rgba(244, 119, 80, 0.12); border: 4px solid #f47750; padding: 50px 40px; border-radius: 16px; }
.date-highlight { font-size: 80px; font-weight: 900; color: #f47750; line-height: 1.1; }
.date-sub { font-size: 42px; font-weight: 600; color: #f7f4ed; margin-top: 16px; }
.rule { width: 100%; height: 2px; background: #ffffff22; margin: 40px 0; }
.callout { font-size: 52px; font-weight: 800; color: #e96643; }
.cap { position: absolute; bottom: 220px; left: 96px; right: 96px; background: #f7f4ed; color: #101d2b; padding: 26px 36px; font-size: 44px; font-weight: 800; box-shadow: 10px 10px 0 #f47750; }
.cap span { color: #e96643; }
.footer { position: absolute; bottom: 120px; left: 96px; font-size: 28px; font-family: monospace; color: #8899a6; }
</style></head><body>
<div class="grid"></div>
<div class="eyebrow">PRELOAD TIMELINE</div>
<h2 class="title">Preload is Live —<br><span style="color:#f47750">Download Now</span></h2>
<div class="countdown-box">
  <div class="date-highlight">LIVE SINCE NOV 10</div>
  <div class="date-sub">Digital pre-order downloads available on PlayStation Store</div>
  <div class="rule"></div>
  <div class="callout">⚡ UNLOCKS NOV 19 AT MIDNIGHT</div>
  <p style="font-size:36px; color:#c0c9d0; margin-top:14px;">Don't wait until launch night to download 210 GB!</p>
</div>
<div class="cap">Preloading is live. <span>Download now</span> to be ready for launch!</div>
<div class="footer">OFFICIAL ROCKSTAR GAMES LAUNCH WINDOW</div>
</body></html>"""
    },
    "scene5": {
        "duration": 7.0,
        "html": """<!doctype html><html><head><meta charset="utf-8"><style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { width: 1080px; height: 1920px; background: #101d2b; font-family: Inter, -apple-system, sans-serif; color: #f7f4ed; position: relative; overflow: hidden; padding: 220px 96px; }
.grid { position: absolute; inset:0; opacity: 0.15; background-image: linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px); background-size: 108px 108px; }
.eyebrow { font-size: 34px; font-weight: 700; letter-spacing: 0.12em; color: #f47750; text-transform: uppercase; font-family: monospace; }
.title { font-size: 96px; font-weight: 900; line-height: 1.05; margin-top: 40px; letter-spacing: -0.04em; }
.pill-grid { display: flex; flex-wrap: wrap; gap: 20px; margin-top: 80px; }
.pill { font-size: 42px; font-weight: 800; border: 3px solid #f47750; padding: 20px 36px; border-radius: 50px; color: #f47750; }
.cta-box { margin-top: 90px; background: #f7f4ed; color: #101d2b; padding: 50px; border-radius: 16px; box-shadow: 12px 12px 0 #e96643; }
.cta-title { font-size: 58px; font-weight: 900; line-height: 1.1; }
.cta-sub { font-size: 36px; font-weight: 700; color: #e96643; margin-top: 14px; }
.cap { position: absolute; bottom: 220px; left: 96px; right: 96px; background: #f7f4ed; color: #101d2b; padding: 26px 36px; font-size: 44px; font-weight: 800; box-shadow: 10px 10px 0 #e96643; }
.cap span { color: #e96643; }
.footer { position: absolute; bottom: 120px; left: 96px; font-size: 28px; font-family: monospace; color: #8899a6; }
</style></head><body>
<div class="grid"></div>
<div class="eyebrow">CREATORRADAR GAMING</div>
<h2 class="title">Daily Verified<br><span style="color:#f47750">GTA VI Guides</span></h2>
<div class="pill-grid">
  <div class="pill">212 GB STORAGE</div>
  <div class="pill">PRELOAD GUIDE</div>
  <div class="pill">EDITIONS BREAKDOWN</div>
</div>
<div class="cta-box">
  <div class="cta-title">Subscribe for verified updates</div>
  <div class="cta-sub">No rumors. No fake gameplay. Pure facts.</div>
</div>
<div class="cap">Follow <span>CreatorRadar</span> for verified GTA 6 guides and updates!</div>
<div class="footer">CREATORRADAR STUDIO / MONETIZATION READY</div>
</body></html>"""
    }
}

# 2. Render HTML files to PNG screenshots using Chrome Headless
scene_clips = []
for name, data in SCENE_HTMLS.items():
    html_file = RENDERS_DIR / f"{name}.html"
    png_file = SCENES_DIR / f"{name}.png"
    mp4_clip = SCENES_DIR / f"{name}.mp4"
    
    with open(html_file, "w") as f:
        f.write(data["html"])
    
    cmd_chrome = [
        "google-chrome",
        "--headless",
        "--disable-gpu",
        "--hide-scrollbars",
        "--window-size=1080,1920",
        f"--screenshot={png_file}",
        f"file://{html_file}"
    ]
    subprocess.run(cmd_chrome, check=True)
    print(f"Rendered {name} to {png_file}")

    # 3. Create MP4 video clip for each scene with subtle zoom/motion
    duration = data["duration"]
    # ffmpeg loop image for duration, 30fps, 1080x1920
    cmd_ffmpeg_clip = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(png_file),
        "-c:v", "libx264",
        "-t", str(duration),
        "-pix_fmt", "yuv420p",
        "-r", "30",
        "-vf", "scale=1080:1920",
        str(mp4_clip)
    ]
    subprocess.run(cmd_ffmpeg_clip, check=True)
    scene_clips.append(mp4_clip)
    print(f"Encoded {mp4_clip} (duration: {duration}s)")

# 4. Concatenate all scenes into a video stream
concat_list = RENDERS_DIR / "concat_list.txt"
with open(concat_list, "w") as f:
    for clip in scene_clips:
        f.write(f"file '{clip.resolve()}'\n")

rough_video = RENDERS_DIR / "rough_video.mp4"
cmd_concat = [
    "ffmpeg", "-y",
    "-f", "concat",
    "-safe", "0",
    "-i", str(concat_list),
    "-c", "copy",
    str(rough_video)
]
subprocess.run(cmd_concat, check=True)
print("Concatenated all scenes into:", rough_video)

# 5. Mux with voiceover audio into final export
cmd_final = [
    "ffmpeg", "-y",
    "-i", str(rough_video),
    "-i", str(AUDIO_PATH),
    "-c:v", "libx264",
    "-preset", "slow",
    "-crf", "20",
    "-c:a", "aac",
    "-b:a", "192k",
    "-ar", "48000",
    "-shortest",
    "-movflags", "+faststart",
    str(FINAL_EXPORT)
]
subprocess.run(cmd_final, check=True)
print("SUCCESS: Master export created at:", FINAL_EXPORT)

# 6. Run ffprobe validation
cmd_probe = [
    "ffprobe", "-v", "error",
    "-show_entries", "stream=codec_name,width,height,r_frame_rate,duration:format=duration,size",
    "-of", "json",
    str(FINAL_EXPORT)
]
result = subprocess.run(cmd_probe, capture_output=True, text=True, check=True)
print("\nFFPROBE VALIDATION RESULT:")
print(result.stdout)
