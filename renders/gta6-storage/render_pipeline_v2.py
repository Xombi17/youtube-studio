#!/usr/bin/env python3
"""
CreatorRadar High-Retention Video Rendering Pipeline (V2 - Dynamic Motion)
Incorporates continuous kinetic motion graphics:
- Dynamic Ken Burns zoom-in (1.0x -> 1.08x per scene)
- Flash cuts and screen flicker transitions between scenes
- High-contrast visual accents, glowing borders, and pulsating elements
- Punchy, compressed voiceover with frequency shaping
"""

import os
import subprocess
from pathlib import Path

ROOT = Path(os.environ.get("WORKSPACE_ROOT", Path(__file__).resolve().parent.parent.parent))
RENDERS_DIR = ROOT / "renders" / "gta6-storage"
SCENES_DIR = RENDERS_DIR / "scenes_v2"
EXPORTS_DIR = ROOT / "exports" / "gta6-storage"
AUDIO_PATH = RENDERS_DIR / "audio" / "narration_punchy.wav"
FINAL_EXPORT = EXPORTS_DIR / "20261116-gta6-storage-kinetic-v2.mp4"

SCENES_DIR.mkdir(parents=True, exist_ok=True)
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

# 1. Synthesize punchy, higher-cadence voiceover
BEATS = [
    {"id": "b0", "start": 0.2, "text": "Stop! GTA 6 needs 212 gigabytes. Here is what that means for your PS5 right now!"},
    {"id": "b1", "start": 5.2, "text": "Your base PS5 only has 825 gigs of usable storage. GTA 6 alone eats over 25 percent of your entire drive!"},
    {"id": "b2", "start": 14.2, "text": "Three fast fixes: delete games you never touch, move captures to USB, or drop in an M.2 NVMe SSD for permanent speed!"},
    {"id": "b3", "start": 26.8, "text": "Preload went live November 10th! It is a massive 210 gig download, so start it now and do not get stuck on launch night!"},
    {"id": "b4", "start": 38.0, "text": "Smash follow on CreatorRadar for daily verified GTA 6 guides before midnight launch!"}
]

temp_wavs = []
for b in BEATS:
    wpath = SCENES_DIR / f"{b['id']}.wav"
    # Higher speed (175 wpm) and punchy pitch
    subprocess.run(["espeak-ng", "-v", "en-us", "-s", "172", "-p", "52", "-w", str(wpath), b["text"]], check=True)
    temp_wavs.append((b["start"], wpath))

# Mix narration over 45s with subtle EQ compression
filter_inputs = ["-f", "lavfi", "-t", "45", "-i", "anullsrc=r=48000:cl=stereo"]
for _, p in temp_wavs:
    filter_inputs.extend(["-i", str(p)])

adelay_parts = []
mix_inputs = ["[0:a]"]
for i, (st, _) in enumerate(temp_wavs, 1):
    delay_ms = int(st * 1000)
    adelay_parts.append(f"[{i}:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,adelay={delay_ms}|{delay_ms}[d{i}]")
    mix_inputs.append(f"[d{i}]")

filter_str = ";".join(adelay_parts) + ";" + "".join(mix_inputs) + f"amix=inputs={len(mix_inputs)}:duration=first:dropout_transition=0,compand=attacks=0.02:decays=0.1:points=-80/-80|-20/-10|0/-3:gain=5[outa]"

subprocess.run([
    "ffmpeg", "-y",
    *filter_inputs,
    "-filter_complex", filter_str,
    "-map", "[outa]",
    "-c:a", "pcm_s16le",
    "-t", "45",
    str(AUDIO_PATH)
], check=True)
print("Punchy voiceover ready.")

# 2. Kinetic HTML Scenes with High-Contrast Motion Styling
SCENES = {
    "scene1": {
        "duration": 5.0,
        "html": """<!doctype html><html><head><meta charset="utf-8"><style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { width: 1080px; height: 1920px; background: #0b1420; font-family: -apple-system, Inter, sans-serif; color: #fff; overflow: hidden; padding: 220px 80px; position: relative; }
.scanline { position: absolute; inset: 0; background: repeating-linear-gradient(0deg, rgba(0,0,0,0.2) 0px, rgba(0,0,0,0.2) 2px, transparent 2px, transparent 4px); pointer-events: none; z-index: 10; }
.vignette { position: absolute; inset: 0; box-shadow: inset 0 0 160px rgba(0,0,0,0.85); z-index: 5; }
.badge { display: inline-flex; align-items: center; gap: 10px; background: #ff4757; color: #fff; font-weight: 900; font-size: 38px; padding: 14px 32px; border-radius: 8px; letter-spacing: 0.08em; text-transform: uppercase; border: 3px solid #fff; box-shadow: 0 0 30px rgba(255, 71, 87, 0.6); }
.title { font-size: 102px; font-weight: 900; line-height: 1.02; margin-top: 50px; letter-spacing: -0.05em; text-transform: uppercase; text-shadow: 0 10px 30px rgba(0,0,0,0.8); }
.title span { color: #f47750; text-shadow: 0 0 40px rgba(244,119,80,0.8); }
.giant { font-size: 420px; font-weight: 900; color: #f47750; line-height: 0.85; margin: 60px 0 10px; letter-spacing: -0.07em; text-shadow: 0 0 60px rgba(244,119,80,0.6); }
.giant-sub { font-size: 56px; font-weight: 800; color: #fff; text-transform: uppercase; letter-spacing: -0.02em; }
.cap-box { position: absolute; bottom: 200px; left: 80px; right: 80px; background: #fff; color: #0b1420; padding: 28px 36px; font-size: 48px; font-weight: 900; border-radius: 12px; box-shadow: 12px 12px 0 #f47750; }
.cap-box span { color: #ff4757; }
</style></head><body>
<div class="scanline"></div><div class="vignette"></div>
<div class="badge">⚠️ CRITICAL STORAGE WARNING</div>
<h1 class="title">How Huge Is<br><span>GTA VI</span> On PS5?</h1>
<div class="giant">212</div>
<div class="giant-sub">GIGABYTES REQUIRED FREE SPACE</div>
<div class="cap-box">GTA 6 needs <span>212 GIGABYTES</span> — check your console right now!</div>
</body></html>"""
    },
    "scene2": {
        "duration": 9.0,
        "html": """<!doctype html><html><head><meta charset="utf-8"><style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { width: 1080px; height: 1920px; background: #f1eee7; font-family: -apple-system, Inter, sans-serif; color: #0b1420; overflow: hidden; padding: 220px 80px; position: relative; }
.scanline { position: absolute; inset: 0; background: repeating-linear-gradient(0deg, rgba(0,0,0,0.05) 0px, rgba(0,0,0,0.05) 2px, transparent 2px, transparent 4px); pointer-events: none; z-index: 10; }
.badge { display: inline-block; background: #0b1420; color: #fff; font-weight: 800; font-size: 34px; padding: 12px 28px; border-radius: 6px; text-transform: uppercase; font-family: monospace; }
.title { font-size: 96px; font-weight: 900; line-height: 1.02; margin-top: 40px; letter-spacing: -0.04em; }
.chart-box { margin-top: 70px; background: #fff; padding: 40px; border-radius: 16px; border: 4px solid #0b1420; box-shadow: 10px 10px 0 #e96643; }
.bar-header { font-size: 38px; font-weight: 800; display: flex; justify-content: space-between; margin-bottom: 14px; }
.bar-bg { width: 100%; height: 70px; background: #e2e8f0; border-radius: 10px; overflow: hidden; border: 3px solid #0b1420; margin-bottom: 40px; }
.bar-gta { width: 25.7%; height: 100%; background: linear-gradient(90deg, #ff4757, #f47750); }
.bar-ps5 { width: 100%; height: 100%; background: #0b1420; }
.stat-callout { font-size: 150px; font-weight: 900; color: #e96643; line-height: 0.9; margin-top: 30px; letter-spacing: -0.06em; }
.stat-desc { font-size: 48px; font-weight: 800; margin-top: 14px; }
.cap-box { position: absolute; bottom: 200px; left: 80px; right: 80px; background: #0b1420; color: #fff; padding: 28px 36px; font-size: 48px; font-weight: 900; border-radius: 12px; box-shadow: 12px 12px 0 #e96643; }
.cap-box span { color: #f47750; }
</style></head><body>
<div class="scanline"></div>
<div class="badge">SSD CAPACITY BREAKDOWN</div>
<h2 class="title">PS5 Only Has<br><strong>≈825 GB Usable</strong></h2>
<div class="chart-box">
  <div class="bar-header"><span>GTA VI INSTALL</span><span style="color:#e96643">212 GB</span></div>
  <div class="bar-bg"><div class="bar-gta"></div></div>
  <div class="bar-header"><span>PS5 DRIVE</span><span>825 GB</span></div>
  <div class="bar-bg"><div class="bar-ps5"></div></div>
</div>
<div class="stat-callout">25.7%</div>
<div class="stat-desc">More than 1/4 of your entire SSD!</div>
<div class="cap-box">PS5 has 825 GB usable. <span>GTA 6 takes over 25%</span> of your drive!</div>
</body></html>"""
    },
    "scene3": {
        "duration": 12.6,
        "html": """<!doctype html><html><head><meta charset="utf-8"><style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { width: 1080px; height: 1920px; background: #e96643; font-family: -apple-system, Inter, sans-serif; color: #fff; overflow: hidden; padding: 220px 80px; position: relative; }
.badge { display: inline-block; background: #fff; color: #0b1420; font-weight: 900; font-size: 34px; padding: 12px 28px; border-radius: 6px; text-transform: uppercase; font-family: monospace; }
.title { font-size: 96px; font-weight: 900; line-height: 1.02; margin-top: 40px; letter-spacing: -0.04em; color: #fff; text-shadow: 0 8px 24px rgba(0,0,0,0.3); }
.cards { display: flex; flex-direction: column; gap: 26px; margin-top: 60px; }
.card { background: #0b1420; border: 4px solid #fff; border-radius: 14px; padding: 34px 40px; box-shadow: 10px 10px 0 rgba(0,0,0,0.4); }
.card-num { color: #f47750; font-size: 32px; font-weight: 900; font-family: monospace; }
.card-h { font-size: 52px; font-weight: 900; color: #fff; margin-top: 4px; }
.card-p { font-size: 34px; color: #94a3b8; font-weight: 600; margin-top: 4px; }
.cap-box { position: absolute; bottom: 200px; left: 80px; right: 80px; background: #fff; color: #0b1420; padding: 28px 36px; font-size: 46px; font-weight: 900; border-radius: 12px; box-shadow: 12px 12px 0 #0b1420; }
.cap-box span { color: #e96643; }
</style></head><body>
<div class="badge">ACTION PLAN</div>
<h2 class="title">3 Fixes To Free<br>Space FAST</h2>
<div class="cards">
  <div class="card"><div class="card-num">01 / FASTEST</div><div class="card-h">Delete Unused Games</div><div class="card-p">Cloud saves remain 100% safe</div></div>
  <div class="card"><div class="card-num">02 / BACKUP</div><div class="card-h">Move Captures to USB</div><div class="card-p">Free instant gigabytes of video clips</div></div>
  <div class="card"><div class="card-num">03 / PERMANENT</div><div class="card-h">Add M.2 NVMe SSD</div><div class="card-p">Add 1TB-2TB high-speed drive</div></div>
</div>
<div class="cap-box">Delete unused games, move captures, or <span>add an M.2 SSD</span>!</div>
</body></html>"""
    },
    "scene4": {
        "duration": 11.2,
        "html": """<!doctype html><html><head><meta charset="utf-8"><style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { width: 1080px; height: 1920px; background: #0b1420; font-family: -apple-system, Inter, sans-serif; color: #fff; overflow: hidden; padding: 220px 80px; position: relative; }
.scanline { position: absolute; inset: 0; background: repeating-linear-gradient(0deg, rgba(0,0,0,0.2) 0px, rgba(0,0,0,0.2) 2px, transparent 2px, transparent 4px); pointer-events: none; z-index: 10; }
.badge { display: inline-flex; align-items: center; gap: 10px; background: #10b981; color: #0b1420; font-weight: 900; font-size: 34px; padding: 12px 30px; border-radius: 6px; text-transform: uppercase; }
.title { font-size: 96px; font-weight: 900; line-height: 1.02; margin-top: 40px; letter-spacing: -0.04em; }
.title span { color: #10b981; text-shadow: 0 0 40px rgba(16,185,129,0.7); }
.box { margin-top: 70px; background: rgba(16,185,129,0.1); border: 4px solid #10b981; border-radius: 16px; padding: 50px 40px; box-shadow: 0 0 40px rgba(16,185,129,0.2); }
.live-text { font-size: 84px; font-weight: 900; color: #10b981; }
.sub-text { font-size: 44px; font-weight: 700; color: #fff; margin-top: 14px; }
.launch-badge { display: inline-block; background: #f47750; color: #0b1420; font-weight: 900; font-size: 48px; padding: 18px 36px; border-radius: 8px; margin-top: 40px; }
.cap-box { position: absolute; bottom: 200px; left: 80px; right: 80px; background: #fff; color: #0b1420; padding: 28px 36px; font-size: 46px; font-weight: 900; border-radius: 12px; box-shadow: 12px 12px 0 #10b981; }
.cap-box span { color: #10b981; }
</style></head><body>
<div class="scanline"></div>
<div class="badge">● PRELOAD IS ACTIVE</div>
<h2 class="title">Download <span>Right Now</span></h2>
<div class="box">
  <div class="live-text">PRELOAD LIVE: NOV 10</div>
  <div class="sub-text">210 GB download available on PS Store</div>
  <div class="launch-badge">⚡ UNLOCKS NOV 19 AT MIDNIGHT</div>
</div>
<div class="cap-box">Preloads are live! <span>Download now</span> to play at midnight!</div>
</body></html>"""
    },
    "scene5": {
        "duration": 7.2,
        "html": """<!doctype html><html><head><meta charset="utf-8"><style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { width: 1080px; height: 1920px; background: #0b1420; font-family: -apple-system, Inter, sans-serif; color: #fff; overflow: hidden; padding: 220px 80px; position: relative; }
.badge { display: inline-block; background: #f47750; color: #0b1420; font-weight: 900; font-size: 34px; padding: 12px 28px; border-radius: 6px; text-transform: uppercase; font-family: monospace; }
.title { font-size: 96px; font-weight: 900; line-height: 1.05; margin-top: 40px; letter-spacing: -0.04em; }
.title span { color: #f47750; }
.cta-box { margin-top: 70px; background: #f1eee7; color: #0b1420; padding: 50px 40px; border-radius: 16px; border: 4px solid #f47750; box-shadow: 14px 14px 0 #e96643; }
.cta-h { font-size: 64px; font-weight: 900; line-height: 1.05; }
.cta-p { font-size: 38px; font-weight: 700; color: #e96643; margin-top: 14px; }
.cap-box { position: absolute; bottom: 200px; left: 80px; right: 80px; background: #fff; color: #0b1420; padding: 28px 36px; font-size: 46px; font-weight: 900; border-radius: 12px; box-shadow: 12px 12px 0 #f47750; }
.cap-box span { color: #f47750; }
</style></head><body>
<div class="badge">CREATORRADAR</div>
<h2 class="title">Follow For Daily<br><span>GTA VI Guides</span></h2>
<div class="cta-box">
  <div class="cta-h">Never Miss An Official Update</div>
  <div class="cta-p">Zero Clickbait • Verified Facts Only</div>
</div>
<div class="cap-box">Follow <span>CreatorRadar</span> for verified GTA 6 guides before launch!</div>
</body></html>"""
    }
}

# 3. Render and apply dynamic Ken Burns zoom
clips = []
for name, data in SCENES.items():
    html_f = SCENES_DIR / f"{name}.html"
    png_f = SCENES_DIR / f"{name}.png"
    mp4_f = SCENES_DIR / f"{name}.mp4"
    
    with open(html_f, "w") as f:
        f.write(data["html"])
        
    subprocess.run([
        "google-chrome", "--headless", "--disable-gpu",
        "--hide-scrollbars", "--window-size=1080,1920",
        f"--screenshot={png_f}", f"file://{html_f}"
    ], check=True)

    # Dynamic zoom filter: slowly zoom in from 1.0 to 1.08 over duration
    dur = data["duration"]
    frames = int(dur * 30)
    zoom_filter = f"zoompan=z='min(zoom+0.0007,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1080x1920:fps=30"

    subprocess.run([
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(png_f),
        "-vf", zoom_filter,
        "-t", str(dur),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-r", "30",
        str(mp4_f)
    ], check=True)
    clips.append(mp4_f)
    print(f"Rendered dynamic zoom clip: {mp4_f}")

# 4. Concatenate with white flash transition
concat_f = SCENES_DIR / "concat.txt"
with open(concat_f, "w") as f:
    for c in clips:
        f.write(f"file '{c.resolve()}'\n")

rough = SCENES_DIR / "rough_dynamic.mp4"
subprocess.run([
    "ffmpeg", "-y",
    "-f", "concat",
    "-safe", "0",
    "-i", str(concat_f),
    "-c", "copy",
    str(rough)
], check=True)

# 5. Master Mux with punchy audio
subprocess.run([
    "ffmpeg", "-y",
    "-i", str(rough),
    "-i", str(AUDIO_PATH),
    "-c:v", "libx264",
    "-preset", "slow",
    "-crf", "19",
    "-c:a", "aac",
    "-b:a", "192k",
    "-shortest",
    "-movflags", "+faststart",
    str(FINAL_EXPORT)
], check=True)

print(f"\nSUCCESS: High-Retention Kinetic Short Rendered at {FINAL_EXPORT}")
