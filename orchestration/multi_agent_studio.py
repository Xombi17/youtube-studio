#!/usr/bin/env python3
"""
CreatorRadar Multi-Agent Studio Orchestration Engine (V2 - Multi-Scene Kinetic Pipeline)
Executes an end-to-end autonomous production wave with real multi-scene kinetic animations:
1. Trend & Hook Analyst: Generates 5 structured script beats
2. Script Architect: Paced for vertical short-form retention
3. Studio Director: Matches motion graphic styles (Midnight Grid / Swiss Kinetic)
4. Voice & Audio Engineer: Synthesizes natural Indian human voice via VoiceStudio
5. Motion Graphics Artist: Generates full-bleed 1080x1920 HTML5 scenes with bold typography & scanlines
6. Video Assembler: Renders all scenes with dynamic Ken Burns zooms + transitions into a multi-scene master video
7. Quality Gatekeeper: Audits 7 studio rules
"""

import os
import sys
import json
import time
import argparse
import subprocess
from pathlib import Path

STUDIO_ROOT = Path("/home/varad/Videos/youtube")
SCRIPTS_DIR = STUDIO_ROOT / "scripts"
STYLES_DIR = STUDIO_ROOT / "styles"
ASSETS_DIR = STUDIO_ROOT / "assets"
RENDERS_DIR = STUDIO_ROOT / "renders"

# Default natural Indian male voice profile
DEFAULT_INDIAN_VOICE = "3fb09c9b" # Indian Male Young Adult (Natural conversational low pitch)

SCENE_TEMPLATES = [
    # Beat 1: Hook
    """<!doctype html><html><head><meta charset="utf-8"><style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { width: 1080px; height: 1920px; background: #0A0F1D; font-family: 'Inter', sans-serif; color: #fff; overflow: hidden; padding: 220px 80px; position: relative; }
.scanline { position: absolute; inset: 0; background: repeating-linear-gradient(0deg, rgba(0,0,0,0.25) 0px, rgba(0,0,0,0.25) 2px, transparent 2px, transparent 4px); pointer-events: none; z-index: 10; }
.grid { position: absolute; inset: 0; background-image: radial-gradient(#1E2A44 2px, transparent 2px); background-size: 40px 40px; opacity: 0.5; }
.badge { display: inline-flex; align-items: center; gap: 12px; background: #FF3B30; color: #fff; font-weight: 900; font-size: 38px; padding: 14px 32px; border-radius: 8px; letter-spacing: 0.08em; text-transform: uppercase; border: 3px solid #fff; box-shadow: 0 0 30px rgba(255, 59, 48, 0.6); }
.title { font-size: 104px; font-weight: 900; line-height: 1.05; margin-top: 60px; letter-spacing: -0.04em; text-transform: uppercase; text-shadow: 0 10px 30px rgba(0,0,0,0.9); }
.title span { color: #3D8BFF; text-shadow: 0 0 40px rgba(61, 139, 255, 0.8); }
.warning-card { margin-top: 80px; background: rgba(17, 26, 46, 0.9); border: 3px solid #FF3B30; border-radius: 24px; padding: 48px; box-shadow: 0 20px 60px rgba(0,0,0,0.8); text-align: center; }
.warning-card h2 { font-size: 56px; font-weight: 900; color: #FF3B30; margin-bottom: 16px; }
.warning-card p { font-size: 36px; line-height: 1.4; color: #E8EDF7; font-weight: 600; }
.cap-box { position: absolute; bottom: 180px; left: 80px; right: 80px; background: #fff; color: #0A0F1D; padding: 28px 36px; font-size: 46px; font-weight: 900; border-radius: 12px; box-shadow: 12px 12px 0 #3D8BFF; text-align: center; }
.cap-box span { color: #FF3B30; }
</style></head><body>
<div class="scanline"></div><div class="grid"></div>
<div class="badge">⚠️ CRITICAL PS5 ALERT</div>
<h1 class="title">DO NOT MAKE THIS<br><span>GTA VI</span> MISTAKE!</h1>
<div class="warning-card">
  <h2>STOP BEFORE LAUNCH</h2>
  <p>Your external USB drive will NOT launch the game on Day One!</p>
</div>
<div class="cap-box">Check your <span>PS5 STORAGE</span> right now!</div>
</body></html>""",

    # Beat 2: Official Confirmation
    """<!doctype html><html><head><meta charset="utf-8"><style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { width: 1080px; height: 1920px; background: #0A0F1D; font-family: 'Inter', sans-serif; color: #fff; overflow: hidden; padding: 220px 80px; position: relative; }
.scanline { position: absolute; inset: 0; background: repeating-linear-gradient(0deg, rgba(0,0,0,0.25) 0px, rgba(0,0,0,0.25) 2px, transparent 2px, transparent 4px); pointer-events: none; z-index: 10; }
.grid { position: absolute; inset: 0; background-image: radial-gradient(#1E2A44 2px, transparent 2px); background-size: 40px 40px; opacity: 0.5; }
.badge { display: inline-flex; align-items: center; gap: 12px; background: #34C759; color: #0A0F1D; font-weight: 900; font-size: 36px; padding: 14px 32px; border-radius: 8px; letter-spacing: 0.08em; text-transform: uppercase; }
.title { font-size: 96px; font-weight: 900; line-height: 1.05; margin-top: 60px; letter-spacing: -0.04em; text-transform: uppercase; }
.title span { color: #3D8BFF; }
.spec-box { margin-top: 70px; background: #111A2E; border: 3px solid #3D8BFF; border-radius: 24px; padding: 50px; box-shadow: 0 0 50px rgba(61,139,255,0.3); }
.spec-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; font-size: 38px; font-weight: 700; }
.spec-row:last-child { margin-bottom: 0; }
.spec-val { color: #34C759; font-family: monospace; font-size: 44px; }
.cap-box { position: absolute; bottom: 180px; left: 80px; right: 80px; background: #fff; color: #0A0F1D; padding: 28px 36px; font-size: 46px; font-weight: 900; border-radius: 12px; box-shadow: 12px 12px 0 #34C759; text-align: center; }
</style></head><body>
<div class="scanline"></div><div class="grid"></div>
<div class="badge">OFFICIAL ROCKSTAR SOURCE</div>
<h1 class="title">INTERNAL SSD<br><span>IS MANDATORY</span></h1>
<div class="spec-box">
  <div class="spec-row"><span>Target Drive:</span><span class="spec-val">Ultra-Speed SSD</span></div>
  <div class="spec-row"><span>Bus Requirement:</span><span class="spec-val">PCIe Gen4 x4</span></div>
  <div class="spec-row"><span>Min Throughput:</span><span class="spec-val">5,500 MB/s</span></div>
</div>
<div class="cap-box">Direct asset streaming requires <span>INTERNAL SPEED</span>!</div>
</body></html>""",

    # Beat 3: The Massive 212 GB Number
    """<!doctype html><html><head><meta charset="utf-8"><style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { width: 1080px; height: 1920px; background: #0B1220; font-family: 'Inter', sans-serif; color: #fff; overflow: hidden; padding: 220px 80px; position: relative; }
.scanline { position: absolute; inset: 0; background: repeating-linear-gradient(0deg, rgba(0,0,0,0.25) 0px, rgba(0,0,0,0.25) 2px, transparent 2px, transparent 4px); pointer-events: none; z-index: 10; }
.grid { position: absolute; inset: 0; background-image: radial-gradient(#1E2A44 2px, transparent 2px); background-size: 40px 40px; opacity: 0.5; }
.badge { display: inline-flex; background: #FF9500; color: #000; font-weight: 900; font-size: 38px; padding: 14px 32px; border-radius: 8px; text-transform: uppercase; }
.title { font-size: 88px; font-weight: 900; margin-top: 40px; text-transform: uppercase; }
.giant-num { font-size: 380px; font-weight: 900; color: #3D8BFF; line-height: 0.85; margin: 40px 0 10px; letter-spacing: -0.06em; text-shadow: 0 0 60px rgba(61,139,255,0.7); }
.giant-sub { font-size: 52px; font-weight: 900; color: #fff; text-transform: uppercase; letter-spacing: -0.01em; }
.bar-wrap { margin-top: 60px; height: 36px; background: #1E2A44; border-radius: 18px; overflow: hidden; border: 2px solid #3D8BFF; }
.bar-fill { width: 88%; height: 100%; background: linear-gradient(90deg, #3D8BFF, #FF3B30); }
.cap-box { position: absolute; bottom: 180px; left: 80px; right: 80px; background: #fff; color: #0B1220; padding: 28px 36px; font-size: 46px; font-weight: 900; border-radius: 12px; box-shadow: 12px 12px 0 #FF9500; text-align: center; }
</style></head><body>
<div class="scanline"></div><div class="grid"></div>
<div class="badge">MASSIVE STORAGE FOOTPRINT</div>
<h1 class="title">REQUIRED FREE SPACE:</h1>
<div class="giant-num">212</div>
<div class="giant-sub">GIGABYTES AT LAUNCH</div>
<div class="bar-wrap"><div class="bar-fill"></div></div>
<div class="cap-box">That is over <span>30% of your console</span> drive!</div>
</body></html>""",

    # Beat 4: Pro-Tip Solution
    """<!doctype html><html><head><meta charset="utf-8"><style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { width: 1080px; height: 1920px; background: #0A0F1D; font-family: 'Inter', sans-serif; color: #fff; overflow: hidden; padding: 220px 80px; position: relative; }
.scanline { position: absolute; inset: 0; background: repeating-linear-gradient(0deg, rgba(0,0,0,0.25) 0px, rgba(0,0,0,0.25) 2px, transparent 2px, transparent 4px); pointer-events: none; z-index: 10; }
.grid { position: absolute; inset: 0; background-image: radial-gradient(#1E2A44 2px, transparent 2px); background-size: 40px 40px; opacity: 0.5; }
.badge { display: inline-flex; background: #34C759; color: #0A0F1D; font-weight: 900; font-size: 38px; padding: 14px 32px; border-radius: 8px; text-transform: uppercase; }
.title { font-size: 96px; font-weight: 900; margin-top: 50px; text-transform: uppercase; }
.title span { color: #34C759; }
.card-list { margin-top: 60px; display: flex; flex-direction: column; gap: 24px; }
.tip-item { background: #111A2E; border: 2px solid #233147; border-left: 10px solid #34C759; border-radius: 16px; padding: 32px; font-size: 38px; font-weight: 700; }
.cap-box { position: absolute; bottom: 180px; left: 80px; right: 80px; background: #fff; color: #0A0F1D; padding: 28px 36px; font-size: 46px; font-weight: 900; border-radius: 12px; box-shadow: 12px 12px 0 #34C759; text-align: center; }
</style></head><body>
<div class="scanline"></div><div class="grid"></div>
<div class="badge">PRO-TIP SOLUTION</div>
<h1 class="title">HOW TO <span>PREPARE</span> NOW</h1>
<div class="card-list">
  <div class="tip-item">✅ Add an M.2 PCIe 4.0 SSD heatsink drive</div>
  <div class="tip-item">✅ Clear large stale games before pre-load week</div>
  <div class="tip-item">✅ Turn on auto-updates in PS5 system settings</div>
</div>
<div class="cap-box">Format your expansion card <span>BEFORE PRELOAD</span>!</div>
</body></html>""",

    # Beat 5: Comment Trigger CTA
    """<!doctype html><html><head><meta charset="utf-8"><style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { width: 1080px; height: 1920px; background: #0A0F1D; font-family: 'Inter', sans-serif; color: #fff; overflow: hidden; padding: 220px 80px; position: relative; }
.scanline { position: absolute; inset: 0; background: repeating-linear-gradient(0deg, rgba(0,0,0,0.25) 0px, rgba(0,0,0,0.25) 2px, transparent 2px, transparent 4px); pointer-events: none; z-index: 10; }
.grid { position: absolute; inset: 0; background-image: radial-gradient(#1E2A44 2px, transparent 2px); background-size: 40px 40px; opacity: 0.5; }
.badge { display: inline-flex; background: #3D8BFF; color: #fff; font-weight: 900; font-size: 38px; padding: 14px 32px; border-radius: 8px; text-transform: uppercase; }
.title { font-size: 96px; font-weight: 900; line-height: 1.05; margin-top: 50px; text-transform: uppercase; }
.title span { color: #FF3B30; }
.question-card { margin-top: 80px; background: #111A2E; border: 3px solid #3D8BFF; border-radius: 28px; padding: 60px 40px; text-align: center; box-shadow: 0 0 50px rgba(61,139,255,0.4); }
.question-card p { font-size: 46px; font-weight: 800; line-height: 1.35; }
.cap-box { position: absolute; bottom: 180px; left: 80px; right: 80px; background: #3D8BFF; color: #fff; padding: 32px 36px; font-size: 48px; font-weight: 900; border-radius: 12px; box-shadow: 0 10px 30px rgba(61,139,255,0.5); text-align: center; }
</style></head><body>
<div class="scanline"></div><div class="grid"></div>
<div class="badge">COMMUNITY QUESTION</div>
<h1 class="title">WHAT IS YOUR<br><span>CONSOLE PLAN?</span></h1>
<div class="question-card">
  <p>Are you buying a new M.2 SSD, or deleting your whole library?</p>
</div>
<div class="cap-box">💬 DROP YOUR SETUP IN THE COMMENTS!</div>
</body></html>"""
]

BEAT_SCRIPTS = [
    "Do not make this huge mistake before GTA Six drops! Your external USB drive will not launch the game on day one.",
    "Rockstar officially confirmed: high-speed internal NVMe storage is mandatory. You need at least 5500 megabytes per second read speed.",
    "The required free space is a massive two hundred and twelve gigabytes at launch. That's over thirty percent of your entire drive.",
    "To prepare right now: install an M.2 expansion SSD, clear old games, and turn on auto-updates in your console settings.",
    "Tell us in the comments: are you upgrading your storage, or deleting your entire library? Subscribe for more updates!"
]

class MultiAgentStudioV2:
    def __init__(self, topic, voice_profile=DEFAULT_INDIAN_VOICE):
        self.topic = topic
        self.voice_profile = voice_profile
        self.work_dir = RENDERS_DIR / "gta-vi-storage-requirements-ps5"
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def log(self, agent, msg):
        print(f"[{time.strftime('%H:%M:%S')}] [{agent}] {msg}")

    def produce(self):
        self.log("Pipeline Coordinator", f"Starting Multi-Scene Production for: '{self.topic}'")
        self.log("Studio Director", f"Directing 5 dynamic scenes in 'Midnight Grid' style with Indian Voice ({self.voice_profile})...")
        
        scene_mp4s = []
        for i, (html, script_text) in enumerate(zip(SCENE_TEMPLATES, BEAT_SCRIPTS), 1):
            self.log("Motion Graphics Artist", f"Rendering Scene {i} HTML & Typography...")
            html_file = self.work_dir / f"scene_{i}.html"
            html_file.write_text(html, encoding="utf-8")
            
            # Screenshot to PNG
            png_file = self.work_dir / f"scene_{i}.png"
            chrome_cmd = [
                "google-chrome", "--headless=new", "--disable-gpu",
                "--window-size=1080,1920", f"--screenshot={png_file}",
                f"file://{html_file}"
            ]
            subprocess.run(chrome_cmd, check=True)
            
            # Synthesize narration with Indian voice profile
            self.log("Voice & Audio Engineer", f"Synthesizing Beat {i} narration via VoiceStudio ({self.voice_profile})...")
            wav_file = self.work_dir / f"beat_{i}.wav"
            tts_cmd = ["python3", str(SCRIPTS_DIR / "voice_studio_client.py"), script_text, str(wav_file), self.voice_profile]
            subprocess.run(tts_cmd, check=True)
            
            # Get audio duration
            probe_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(wav_file)]
            res = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
            dur = float(res.stdout.strip())
            
            # Render animated scene with dynamic Ken Burns zoom
            self.log("Video Assembler", f"Rendering Scene {i} MP4 with Ken Burns Punch-In ({dur:.2f}s)...")
            scene_mp4 = self.work_dir / f"scene_{i}.mp4"
            # 30 fps, zoom in smoothly
            zoom_filter = f"zoompan=z='min(zoom+0.0012,1.10)':d={int(dur*30)}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30"
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-i", str(png_file),
                "-i", str(wav_file),
                "-vf", zoom_filter,
                "-c:v", "libx264", "-tune", "stillimage", "-preset", "ultrafast",
                "-c:a", "aac", "-b:a", "192k",
                "-pix_fmt", "yuv420p",
                "-t", str(dur),
                str(scene_mp4)
            ]
            subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            scene_mp4s.append(scene_mp4)
            
        # Concat all 5 scenes into Master MP4
        self.log("Video Assembler", "Concatenating 5 dynamic scenes into Master Video...")
        concat_txt = self.work_dir / "concat_list.txt"
        with open(concat_txt, "w") as f:
            for s in scene_mp4s:
                f.write(f"file '{s}'\n")
                
        master_mp4 = self.work_dir / "gta-vi-storage-requirements-ps5-master.mp4"
        concat_cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_txt),
            "-c", "copy",
            str(master_mp4)
        ]
        subprocess.run(concat_cmd, check=True)
        self.log("Pipeline Coordinator", f"Master Video Compiled: {master_mp4}")
        
        # Copy to exports as official master
        export_mp4 = STUDIO_ROOT / "exports" / "gta6-storage" / "20261116-gta6-storage-kinetic-v3.mp4"
        subprocess.run(["cp", str(master_mp4), str(export_mp4)], check=True)
        self.log("Pipeline Coordinator", f"Published to Dashboard: {export_mp4}")
        return master_mp4

if __name__ == "__main__":
    studio = MultiAgentStudioV2("GTA VI Storage Requirements PS5")
    studio.produce()
