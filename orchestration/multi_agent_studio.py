#!/usr/bin/env python3
"""
CreatorRadar Multi-Agent Studio Orchestration Engine (v2)
End-to-end, topic-agnostic autonomous production pipeline:
1. Trend & Hook Analyst (hook formulation + hookscore.py scoring)
2. Script Architect (parses custom script/beats or drafts verified structured script)
3. Studio Director (selects optimal style & real color tokens from 120 styles)
4. Voice & Audio Engineer (VoiceStudio clone / neural fallback + -14 LUFS mastering + SFX)
5. Motion Graphics Artist (kinetic HTML5/GSAP + studio.js scene synced to exact beat timestamps)
6. Video Assembler (Playwright/Chrome deterministic render via NVENC + FFmpeg muxing)
7. Quality & Compliance Gatekeeper (real ffprobe, EBU R128 loudness, motion check, metadata & checklist)
"""

import argparse
import datetime
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

STUDIO_ROOT = Path(os.environ.get("WORKSPACE_ROOT", Path(__file__).resolve().parent.parent))
SCRIPTS_DIR = STUDIO_ROOT / "scripts"
RENDERS_DIR = STUDIO_ROOT / "renders"
EXPORTS_DIR = STUDIO_ROOT / "exports"
PROJECTS_DIR = STUDIO_ROOT / "projects"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from generate_broadcast_audio import build_synced_beat_audio  # noqa: E402
from render_scene import render_scene  # noqa: E402
from select_style import select_style  # noqa: E402
from video_review_agent import REQUIRED_DISCLOSURE, VideoReviewerAgent  # noqa: E402
from voice_studio_client import DEFAULT_EDGE_VOICE, DEFAULT_PROFILE_ID  # noqa: E402

GTA6_OFFICIAL_SOURCES = [
    ("Rockstar Games — GTA VI Official", "https://www.rockstargames.com/VI"),
    ("Rockstar Games Support — GTA VI", "https://support.rockstargames.com/VI"),
    ("PlayStation — GTA VI Support", "https://www.playstation.com/en-in/support/games/gta-vi-support/"),
    ("Xbox Support — GTA VI", "https://support.xbox.com"),
]


def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return s[:64] or "untitled-project"


def extract_headline(text: str, fallback: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9\s\.\$\+\-\?]", "", fallback or text).strip()
    words = cleaned.split()
    if len(words) <= 4 and words:
        return " ".join(words).upper()
    # Pick high-signal words from text
    tokens = re.findall(r"[A-Za-z0-9\$\.\+%]+", text)
    stop = {"the", "and", "for", "that", "with", "this", "from", "your", "are", "you", "will", "not", "have", "into", "before", "about"}
    picked = [t for t in tokens if t.lower() not in stop][:3]
    return (" ".join(picked) if picked else " ".join(tokens[:3])).upper() or "KEY INSIGHT"


def parse_markdown_script(script_text: str, topic: str) -> list[dict]:
    """Parse ## Beat N: Title sections or plain paragraphs into structured beats."""
    sections = re.split(r"^##\s+", script_text, flags=re.MULTILINE)
    beats: list[dict] = []

    for idx, sec in enumerate(sections[1:], start=1):
        lines = [ln.strip() for ln in sec.strip().splitlines() if ln.strip()]
        if not lines:
            continue
        header = lines[0]
        if header.lower().startswith(("sources", "references", "notes", "metadata")):
            continue
        body_lines = [
            ln for ln in lines[1:]
            if not ln.startswith(("#", ">", "---", "|")) and not re.match(r"^(visual|on-screen|sfx|caption)\s*:", ln, re.I)
        ]
        spoken = " ".join(re.sub(r"\*\*|\*|`|_", "", ln) for ln in body_lines).strip()
        if not spoken:
            continue

        # Clean heading like "Beat 1: Hook (0-3s)" -> tag "BEAT 01 // HOOK", headline extracted
        clean_header = re.sub(r"^beat\s*\d+\s*[:\-—]*\s*", "", header, flags=re.I)
        clean_header = re.sub(r"\([^)]*\)", "", clean_header).strip()
        tag = f"BEAT {idx:02d} // {(clean_header or 'SEGMENT').upper()}"
        headline = extract_headline(spoken, clean_header)
        beats.append({
            "id": f"beat_{idx:02d}",
            "tag": tag[:44],
            "headline": headline[:28],
            "text": spoken,
        })

    if beats:
        return beats

    # Fallback: split plain text into sentences/paragraphs (3-5 beats)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", script_text) if p.strip() and not p.strip().startswith("#")]
    if len(paragraphs) == 1:
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", paragraphs[0]) if s.strip()]
        chunk_size = max(1, (len(sentences) + 4) // 5)
        paragraphs = [" ".join(sentences[i:i + chunk_size]) for i in range(0, len(sentences), chunk_size)]

    for idx, para in enumerate(paragraphs[:7], start=1):
        clean = re.sub(r"\*\*|\*|`|_", "", para)
        beats.append({
            "id": f"beat_{idx:02d}",
            "tag": f"BEAT {idx:02d} // {topic[:24].upper()}",
            "headline": extract_headline(clean, ""),
            "text": clean,
        })
    return beats


def generate_default_beats(topic: str, hook: str, is_gta6: bool) -> list[dict]:
    """
    Generate a concise, high-cadence 5-beat script.
    For GTA VI topics, strictly cites only verified facts from config/gta6-sources.md.
    """
    t_lower = topic.lower()
    if is_gta6:
        if any(k in t_lower for k in ("edition", "ultimate", "price", "standard", "buy")):
            return [
                {"id": "beat_01", "tag": "BEAT 01 // HOOK", "headline": "STANDARD VS ULTIMATE", "text": hook, "sfx": "impact.wav"},
                {"id": "beat_02", "tag": "BEAT 02 // OFFICIAL PRICING", "headline": "$79.99 VS $99.99", "text": "Rockstar Games and the PlayStation Store list Standard Edition at seventy-nine ninety-nine and Ultimate Edition at ninety-nine ninety-nine.", "sfx": "whoosh.wav"},
                {"id": "beat_03", "tag": "BEAT 03 // LAUNCH PLATFORMS", "headline": "PS5 & XBOX ONLY", "text": "Both editions launch November nineteenth, twenty twenty-six on PlayStation Five and Xbox Series X and S, with no PC release confirmed at launch.", "sfx": "click.wav"},
                {"id": "beat_04", "tag": "BEAT 04 // STORAGE & PRELOAD", "headline": "212 GB REQUIRED", "text": "Preload opened November tenth, and PlayStation Support confirms you need around two hundred and twelve gigabytes of free SSD space.", "sfx": "whoosh.wav"},
                {"id": "beat_05", "tag": "BEAT 05 // COMMUNITY POLL", "headline": "WHICH EDITION?", "text": "Are you going Standard or Ultimate for launch day? Drop your console and edition choice in the comments.", "sfx": "riser.wav"},
            ]
        if any(k in t_lower for k in ("preload", "download", "launch", "survival", "midnight")):
            return [
                {"id": "beat_01", "tag": "BEAT 01 // LAUNCH ALERT", "headline": "NOV 19 LAUNCH", "text": hook, "sfx": "impact.wav"},
                {"id": "beat_02", "tag": "BEAT 02 // PRELOAD STATUS", "headline": "PRELOAD LIVE", "text": "Official PlayStation and Rockstar Support confirm GTA Six preloads opened November tenth ahead of the November nineteenth console launch.", "sfx": "whoosh.wav"},
                {"id": "beat_03", "tag": "BEAT 03 // STORAGE CHECK", "headline": "212 GB FREE SPACE", "text": "PlayStation Support lists roughly two hundred and ten gigabytes to download and two hundred and twelve gigabytes of free space required.", "sfx": "click.wav"},
                {"id": "beat_04", "tag": "BEAT 04 // PLATFORM CHECK", "headline": "PS5 & SERIES X|S", "text": "GTA Six launches on PS5 and Xbox Series X and S only, so double-check your internal SSD space and automatic updates before midnight.", "sfx": "whoosh.wav"},
                {"id": "beat_05", "tag": "BEAT 05 // READY CHECK", "headline": "PRELOAD DONE?", "text": "Is your console preloaded and ready for November nineteenth? Tell us your setup in the comments below.", "sfx": "riser.wav"},
            ]
        # Default verified GTA VI hardware/storage facts
        return [
            {"id": "beat_01", "tag": "BEAT 01 // HOOK", "headline": "GTA VI PREP", "text": hook, "sfx": "impact.wav"},
            {"id": "beat_02", "tag": "BEAT 02 // VERIFIED SPECS", "headline": "212 GB ON PS5", "text": "PlayStation Support confirms GTA Six is roughly a two hundred and ten gigabyte download requiring around two hundred and twelve gigabytes of space.", "sfx": "whoosh.wav"},
            {"id": "beat_03", "tag": "BEAT 03 // RELEASE WINDOW", "headline": "NOV 19 CONSOLES", "text": "Rockstar officially confirmed launch for November nineteenth, twenty twenty-six on PS5 and Xbox Series X and S, with preload starting November tenth.", "sfx": "click.wav"},
            {"id": "beat_04", "tag": "BEAT 04 // ACTION STEP", "headline": "CLEAR YOUR SSD", "text": "Check your console storage manager early, clear unused installs, and verify your Standard or Ultimate digital preload is complete.", "sfx": "whoosh.wav"},
            {"id": "beat_05", "tag": "BEAT 05 // COMMUNITY CTA", "headline": "UPGRADE OR CLEAR?", "text": "Are you clearing old games or upgrading your SSD before launch? Let us know in the comments.", "sfx": "riser.wav"},
        ]

    # General-purpose creator explainer template (any niche)
    short_topic = extract_headline(topic, topic)
    return [
        {"id": "beat_01", "tag": "BEAT 01 // HOOK", "headline": short_topic, "text": hook, "sfx": "impact.wav"},
        {"id": "beat_02", "tag": "BEAT 02 // CORE CONTEXT", "headline": "WHY IT MATTERS", "text": f"Most people miss the key detail behind {topic}, and that single oversight is where time and quality get lost.", "sfx": "whoosh.wav"},
        {"id": "beat_03", "tag": "BEAT 03 // BREAKDOWN", "headline": "THE REAL MECHANISM", "text": f"Break {topic} down into three verified checkpoints: confirm primary specs, cut the fluff, and focus on measurable results.", "sfx": "click.wav"},
        {"id": "beat_04", "tag": "BEAT 04 // ACTIONABLE FIX", "headline": "DO THIS FIRST", "text": f"Start with the highest-leverage step right away so your workflow around {topic} stays fast, repeatable, and verified.", "sfx": "whoosh.wav"},
        {"id": "beat_05", "tag": "BEAT 05 // COMMUNITY CTA", "headline": "YOUR TAKE?", "text": f"What is your biggest question about {topic}? Drop it in the comments and we will break it down next.", "sfx": "riser.wav"},
    ]


def build_kinetic_scene_html(
    topic: str,
    style_data: dict,
    timed_beats: list[dict],
    total_duration: float,
    width: int,
    height: int,
) -> str:
    """
    Build a high-retention, deterministic HTML5/GSAP + studio.js scene driven by:
    - Real selected style color tokens (bg, surface, border, text, muted, accent, accent2)
    - Exact measured beat timestamps (start, end, duration)
    - Continuous Ken Burns camera drift, dot/grid parallax, cut flashes, and kinetic word-by-word captions
    """
    tokens = style_data.get("metadata", {}).get("tokens", {})
    bg = tokens.get("bg", "#0B1220")
    surface = tokens.get("surface", "#111A2E")
    border = tokens.get("border", "#22304D")
    text_col = tokens.get("text", "#E8EDF7")
    muted = tokens.get("muted", "#8C98B3")
    accent = tokens.get("accent", "#3D8BFF")
    accent2 = tokens.get("accent2", "#F47750")

    style_name = style_data.get("metadata", {}).get("name", style_data.get("selected_style", "Midnight Grid"))
    style_id = style_data.get("selected_style", "midnight-grid")
    is_vertical = height > width

    beats_payload = []
    accents_cycle = [accent, accent2, "#34C759", "#FF9F0A", accent]
    for i, b in enumerate(timed_beats):
        beats_payload.append({
            "index": i,
            "tag": b.get("tag", f"BEAT {i + 1:02d}"),
            "headline": b.get("headline", f"POINT {i + 1}"),
            "text": b["text"],
            "start": b["start"],
            "end": b["end"],
            "duration": b["duration"],
            "color": accents_cycle[i % len(accents_cycle)],
        })

    beats_json = json.dumps(beats_payload, ensure_ascii=False)
    safe_topic = html.escape(topic.upper()[:46])
    safe_style = html.escape(f"{style_name} ({style_id})".upper()[:40])

    # Layout tuning for 9:16 vs 16:9
    pad_x = 72 if is_vertical else 110
    card_top = 260 if is_vertical else 170
    card_h = 740 if is_vertical else 470
    headline_size = 94 if is_vertical else 88
    caption_top = 1120 if is_vertical else 690
    caption_font = 52 if is_vertical else 44

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width={width}, height={height}" />
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@500;700;800;900&family=JetBrains+Mono:wght@600;700&display=swap" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<script src="studio.js"></script>
<style>
  :root {{
    --bg: {bg};
    --surface: {surface};
    --border: {border};
    --text: {text_col};
    --muted: {muted};
    --accent: {accent};
    --accent2: {accent2};
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{
    width: {width}px; height: {height}px; overflow: hidden;
    background: var(--bg); color: var(--text);
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  }}
  #root {{
    position: relative; width: {width}px; height: {height}px; overflow: hidden;
    background: radial-gradient(circle at 20% 15%, color-mix(in srgb, var(--accent) 18%, var(--bg)), var(--bg) 62%);
  }}
  #bg-stage {{
    position: absolute; inset: -60px;
    transform-origin: center center;
    will-change: transform;
  }}
  #dot-grid {{
    position: absolute; inset: 0;
    background-image: radial-gradient(circle at 20px 20px, var(--border) 2px, transparent 2.5px);
    background-size: 44px 44px;
    opacity: 0.72;
  }}
  #ambient-orb {{
    position: absolute; width: 680px; height: 680px; border-radius: 50%;
    filter: blur(110px); opacity: 0.24; pointer-events: none;
    background: var(--accent);
  }}
  #scanlines {{
    position: absolute; inset: 0; pointer-events: none; z-index: 40;
    background: repeating-linear-gradient(
      to bottom,
      rgba(255,255,255,0.02) 0px,
      rgba(255,255,255,0.02) 1px,
      transparent 1px,
      transparent 4px
    );
    opacity: 0.45;
  }}
  #flash {{
    position: absolute; inset: 0; background: #FFFFFF; opacity: 0; pointer-events: none; z-index: 50;
  }}

  /* Top Broadcast Header */
  .hud-top {{
    position: absolute; top: 56px; left: {pad_x}px; right: {pad_x}px;
    display: flex; justify-content: space-between; align-items: center;
    padding-bottom: 20px; border-bottom: 2px solid var(--border); z-index: 20;
  }}
  .hud-pill {{
    display: inline-flex; align-items: center; gap: 12px;
    background: var(--surface); border: 2px solid var(--accent);
    color: var(--accent); font-family: 'JetBrains Mono', monospace;
    font-size: 20px; font-weight: 700; padding: 10px 22px; border-radius: 999px;
    letter-spacing: 0.06em;
  }}
  .hud-dot {{
    width: 12px; height: 12px; border-radius: 50%; background: var(--accent);
    box-shadow: 0 0 14px var(--accent);
  }}
  .hud-topic {{
    font-family: 'JetBrains Mono', monospace; font-size: 20px; font-weight: 700;
    color: var(--muted); letter-spacing: 0.08em; text-align: right;
  }}

  /* Main Kinetic Stage Card */
  #stage-card {{
    position: absolute; left: {pad_x}px; right: {pad_x}px; top: {card_top}px; height: {card_h}px;
    background: color-mix(in srgb, var(--surface) 92%, transparent);
    border: 2px solid var(--border); border-radius: 28px;
    padding: 52px 56px; overflow: hidden;
    box-shadow: 0 28px 80px rgba(0, 0, 0, 0.45);
    display: flex; flex-direction: column; justify-content: space-between;
    z-index: 10; will-change: transform;
  }}
  #card-accent-bar {{
    position: absolute; top: 0; left: 0; right: 0; height: 8px; background: var(--accent);
  }}
  .card-meta {{
    display: flex; justify-content: space-between; align-items: center;
  }}
  #beat-tag {{
    font-family: 'JetBrains Mono', monospace; font-size: 24px; font-weight: 700;
    letter-spacing: 0.1em; color: var(--accent);
  }}
  #beat-counter {{
    font-family: 'JetBrains Mono', monospace; font-size: 24px; font-weight: 700;
    color: var(--muted);
  }}
  .headline-wrap {{
    overflow: hidden; padding: 16px 0;
  }}
  #beat-headline {{
    font-size: {headline_size}px; font-weight: 900; line-height: 1.02;
    letter-spacing: -0.04em; text-transform: uppercase;
    will-change: transform, opacity;
  }}
  .beat-pills {{
    display: flex; gap: 14px; align-items: center;
  }}
  .step-seg {{
    flex: 1; height: 10px; border-radius: 999px; background: var(--border); overflow: hidden;
  }}
  .step-fill {{
    height: 100%; width: 0%; border-radius: 999px; background: var(--accent);
  }}

  /* Kinetic Word-by-Word Caption Stage */
  #caption-box {{
    position: absolute; left: {pad_x}px; right: {pad_x}px; top: {caption_top}px;
    background: rgba(8, 12, 22, 0.86);
    border: 2px solid var(--border); border-radius: 24px;
    padding: 36px 42px; z-index: 25;
    min-height: 220px; display: flex; flex-wrap: wrap; align-content: center;
    justify-content: center; gap: 14px 16px;
    box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5);
  }}
  .cap-word {{
    font-size: {caption_font}px; font-weight: 800; line-height: 1.18;
    letter-spacing: -0.02em; color: var(--muted);
    transition: none; display: inline-block;
  }}
  .cap-word.spoken {{ color: var(--text); }}
  .cap-word.active {{
    color: var(--accent);
    transform: scale(1.09) translateY(-3px);
    text-shadow: 0 0 24px color-mix(in srgb, var(--accent) 55%, transparent);
  }}

  /* Bottom Timeline Progress Rail */
  .hud-bottom {{
    position: absolute; left: {pad_x}px; right: {pad_x}px; bottom: 52px; z-index: 20;
    display: flex; flex-direction: column; gap: 14px;
  }}
  .hud-bottom-row {{
    display: flex; justify-content: space-between; align-items: center;
    font-family: 'JetBrains Mono', monospace; font-size: 18px; color: var(--muted);
  }}
  .global-track {{
    width: 100%; height: 8px; border-radius: 999px; background: var(--border); overflow: hidden;
  }}
  #global-fill {{
    height: 100%; width: 0%; background: linear-gradient(90deg, var(--accent), var(--accent2));
  }}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{total_duration:.3f}" data-width="{width}" data-height="{height}">
  <div id="bg-stage">
    <div id="dot-grid"></div>
    <div id="ambient-orb"></div>
  </div>
  <div id="scanlines"></div>
  <div id="flash"></div>

  <div class="hud-top">
    <div class="hud-pill"><span class="hud-dot" id="hud-dot"></span>{safe_style}</div>
    <div class="hud-topic">{safe_topic}</div>
  </div>

  <div id="stage-card">
    <div id="card-accent-bar"></div>
    <div class="card-meta">
      <div id="beat-tag">BEAT 01</div>
      <div id="beat-counter">01 / {len(beats_payload):02d}</div>
    </div>
    <div class="headline-wrap">
      <div id="beat-headline">LOADING</div>
    </div>
    <div class="beat-pills" id="beat-pills"></div>
  </div>

  <div id="caption-box"></div>

  <div class="hud-bottom">
    <div class="hud-bottom-row">
      <span>CREATORRADAR STUDIO</span>
      <span id="timecode">00:00.0 / 00:{total_duration:04.1f}</span>
    </div>
    <div class="global-track"><div id="global-fill"></div></div>
  </div>
</div>

<script>
  const S = STUDIO;
  const BEATS = {beats_json};
  const TOTAL = {total_duration:.3f};

  const bgStage = document.getElementById('bg-stage');
  const orb = document.getElementById('ambient-orb');
  const flash = document.getElementById('flash');
  const stageCard = document.getElementById('stage-card');
  const accentBar = document.getElementById('card-accent-bar');
  const hudDot = document.getElementById('hud-dot');
  const beatTag = document.getElementById('beat-tag');
  const beatCounter = document.getElementById('beat-counter');
  const beatHeadline = document.getElementById('beat-headline');
  const captionBox = document.getElementById('caption-box');
  const globalFill = document.getElementById('global-fill');
  const timecode = document.getElementById('timecode');
  const pillsWrap = document.getElementById('beat-pills');

  const stepFills = BEATS.map(() => {{
    const seg = document.createElement('div');
    seg.className = 'step-seg';
    const fill = document.createElement('div');
    fill.className = 'step-fill';
    seg.appendChild(fill);
    pillsWrap.appendChild(seg);
    return fill;
  }});

  let lastBeatIdx = -1;
  let wordNodes = [];

  function mountCaptionWords(beat) {{
    captionBox.innerHTML = '';
    const words = beat.text.split(/\\s+/).filter(Boolean);
    wordNodes = words.map((w) => {{
      const span = document.createElement('span');
      span.className = 'cap-word';
      span.textContent = w;
      captionBox.appendChild(span);
      return span;
    }});
  }}

  STUDIO.play(function render(t) {{
    // 1. Find active beat for current timestamp t
    let activeIdx = 0;
    for (let i = 0; i < BEATS.length; i++) {{
      if (t >= BEATS[i].start) activeIdx = i;
    }}
    const beat = BEATS[activeIdx];
    const localT = Math.max(0, t - beat.start);
    const beatDur = Math.max(0.2, beat.duration);
    const beatProgress = Math.min(1, localT / beatDur);

    // 2. Continuous Ken Burns zoom + subtle parallax drift (zero static frames)
    const kbScale = 1.0 + 0.08 * (t / TOTAL);
    const driftX = Math.sin(t * 0.7) * 18;
    const driftY = Math.cos(t * 0.5) * 14 - activeIdx * 10;
    bgStage.style.transform = `translate(${{driftX.toFixed(2)}}px, ${{driftY.toFixed(2)}}px) scale(${{kbScale.toFixed(4)}})`;

    const orbX = ({width} * 0.5 - 340) + Math.sin(t * 0.9) * 210;
    const orbY = ({height} * 0.36 - 340) + Math.cos(t * 0.65) * 160;
    orb.style.transform = `translate(${{orbX.toFixed(1)}}px, ${{orbY.toFixed(1)}}px)`;
    orb.style.background = beat.color;

    // 3. Beat cut flash punctuation (short crisp white flash on every cut)
    const cutAge = Math.abs(t - beat.start);
    const flashOpacity = cutAge < 0.14 ? (1 - cutAge / 0.14) * 0.22 : 0;
    flash.style.opacity = flashOpacity.toFixed(3);

    // 4. Card kinetic entrance + subtle continuous breathing zoom
    const enter = S.seg(localT, 0, 0.34, 'power3.out');
    const cardScale = S.mix(0.955, 1.0, enter) + beatProgress * 0.022;
    const cardY = S.mix(38, 0, enter);
    stageCard.style.transform = `translateY(${{cardY.toFixed(2)}}px) scale(${{cardScale.toFixed(4)}})`;
    stageCard.style.borderColor = beat.color;
    accentBar.style.background = beat.color;
    hudDot.style.background = beat.color;
    hudDot.style.boxShadow = `0 0 16px ${{beat.color}}`;

    // 5. Update text & headline kinetic reveal
    if (activeIdx !== lastBeatIdx) {{
      beatTag.textContent = beat.tag;
      beatTag.style.color = beat.color;
      beatCounter.textContent = `${{String(activeIdx + 1).padStart(2, '0')}} / ${{String(BEATS.length).padStart(2, '0')}}`;
      beatHeadline.textContent = beat.headline;
      mountCaptionWords(beat);
      lastBeatIdx = activeIdx;
    }}
    const headReveal = S.seg(localT, 0.04, 0.36, 'power3.out');
    beatHeadline.style.transform = `translateY(${{S.mix(96, 0, headReveal).toFixed(2)}}px)`;
    beatHeadline.style.opacity = headReveal.toFixed(3);

    // 6. Step progress bars
    stepFills.forEach((fill, idx) => {{
      if (idx < activeIdx) {{
        fill.style.width = '100%';
        fill.style.background = BEATS[idx].color;
      }} else if (idx === activeIdx) {{
        fill.style.width = `${{(beatProgress * 100).toFixed(1)}}%`;
        fill.style.background = beat.color;
      }} else {{
        fill.style.width = '0%';
      }}
    }});

    // 7. Kinetic word-by-word caption highlighting synced to beat speech progress
    const totalWords = wordNodes.length;
    if (totalWords > 0) {{
      const activeWordIdx = Math.min(totalWords - 1, Math.floor(beatProgress * totalWords));
      // Show a focused window of up to 10 words around the active word for readability
      const windowSize = {8 if is_vertical else 12};
      const winStart = Math.floor(activeWordIdx / windowSize) * windowSize;
      const winEnd = Math.min(totalWords, winStart + windowSize);
      for (let w = 0; w < totalWords; w++) {{
        const node = wordNodes[w];
        if (w < winStart || w >= winEnd) {{
          node.style.display = 'none';
          continue;
        }}
        node.style.display = 'inline-block';
        if (w === activeWordIdx) {{
          node.className = 'cap-word active';
          node.style.color = beat.color;
        }} else if (w < activeWordIdx) {{
          node.className = 'cap-word spoken';
          node.style.color = '';
        }} else {{
          node.className = 'cap-word';
          node.style.color = '';
        }}
      }}
    }}

    // 8. Global progress bar & live timecode
    globalFill.style.width = `${{(Math.min(1, t / TOTAL) * 100).toFixed(2)}}%`;
    const mins = String(Math.floor(t / 60)).padStart(2, '0');
    const secs = (t % 60).toFixed(1).padStart(4, '0');
    const tMins = String(Math.floor(TOTAL / 60)).padStart(2, '0');
    const tSecs = (TOTAL % 60).toFixed(1).padStart(4, '0');
    timecode.textContent = `${{mins}}:${{secs}} / ${{tMins}}:${{tSecs}}`;
  }}, {{ loop: false }});
</script>
</body>
</html>
"""


class MultiAgentStudio:
    def __init__(
        self,
        topic: str,
        output_slug: str | None = None,
        video_format: str = "short",
        style_preference: str = "auto",
        voice_profile: str = DEFAULT_PROFILE_ID,
        edge_voice: str = DEFAULT_EDGE_VOICE,
        script_path: str | None = None,
        beats_json: str | None = None,
        fps: int = 30,
        quality: str = "high",
        codec: str = "auto",
        include_sfx: bool = True,
    ):
        self.topic = topic.strip()
        self.slug = output_slug or slugify(self.topic)
        self.video_format = video_format
        self.width, self.height = (1080, 1920) if video_format == "short" else (1920, 1080)
        self.style_preference = style_preference
        self.voice_profile = voice_profile
        self.edge_voice = edge_voice
        self.script_path = Path(script_path) if script_path else None
        self.beats_json = Path(beats_json) if beats_json else None
        self.fps = fps
        self.quality = quality
        self.codec = codec
        self.include_sfx = include_sfx
        self.is_gta6 = bool(re.search(r"\bgta\s*(6|vi)\b", self.topic, re.I))

        self.work_dir = RENDERS_DIR / self.slug
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.export_dir = EXPORTS_DIR / self.slug
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.logs: list[str] = []

    def log(self, agent_name: str, message: str):
        entry = f"[{time.strftime('%H:%M:%S')}] [{agent_name}] {message}"
        print(entry, flush=True)
        self.logs.append(entry)

    def run_trend_and_hook_agent(self) -> tuple[str, dict | None]:
        self.log("Trend & Hook Analyst", f"Formulating retention hooks for: '{self.topic}'...")
        candidates = [
            f"Do not make this costly mistake before {self.topic} catches you off guard.",
            f"Stop scrolling: here is what actually matters about {self.topic} right now.",
            f"Almost everyone misses this critical detail about {self.topic}.",
        ]
        if self.is_gta6:
            candidates = [
                f"Do not wait until launch night to check {self.topic}.",
                f"Official Rockstar and console specs just confirmed what you need for {self.topic}.",
                f"Before GTA Six unlocks on November nineteenth, check this about {self.topic}.",
            ]

        # Score candidate hooks using the workspace's hookscore.py if present
        hookscore_py = STUDIO_ROOT / "skills" / "yt-script" / "hookscore.py"
        best_hook = candidates[0]
        score_info = None
        if hookscore_py.exists():
            try:
                scored = []
                for h in candidates:
                    res = subprocess.run(
                        [sys.executable, str(hookscore_py), "--hook", h, "--json"],
                        capture_output=True, text=True, timeout=10,
                    )
                    if res.returncode == 0 and res.stdout.strip():
                        parsed = json.loads(res.stdout)
                        entry = parsed[0] if isinstance(parsed, list) else parsed
                        scored.append((float(entry.get("verdict", entry.get("score", 0))), h, entry))
                if scored:
                    scored.sort(key=lambda x: x[0], reverse=True)
                    best_hook = scored[0][1]
                    score_info = scored[0][2]
            except Exception as e:
                self.log("Trend & Hook Analyst", f"hookscore.py skipped ({e})")

        self.log("Trend & Hook Analyst", f"Selected Hook: '{best_hook}'")
        return best_hook, score_info

    def run_script_architect_agent(self, hook: str) -> tuple[Path, list[dict]]:
        self.log("Script Architect", "Preparing structured production beats...")
        beats: list[dict] = []

        if self.beats_json and self.beats_json.exists():
            beats = json.loads(self.beats_json.read_text(encoding="utf-8"))
            self.log("Script Architect", f"Loaded {len(beats)} custom beats from {self.beats_json}")
        else:
            candidate_scripts = [
                self.script_path,
                PROJECTS_DIR / self.slug / "script.md",
                SCRIPTS_DIR / self.slug / "script.md",
            ]
            existing_script = next((p for p in candidate_scripts if p and p.exists()), None)
            if existing_script:
                raw = existing_script.read_text(encoding="utf-8")
                beats = parse_markdown_script(raw, self.topic)
                self.log("Script Architect", f"Parsed {len(beats)} beats from existing script: {existing_script}")
            else:
                beats = generate_default_beats(self.topic, hook, is_gta6=self.is_gta6)
                self.log("Script Architect", f"Drafted {len(beats)} structured beats for '{self.topic}'")

        script_file = self.work_dir / "script.md"
        sources_md = (
            "\n".join(f"- {name} — {url} — Accessed {datetime.date.today().isoformat()}" for name, url in GTA6_OFFICIAL_SOURCES)
            if self.is_gta6
            else f"- Primary documentation / creator research — Accessed {datetime.date.today().isoformat()} (verify before publish)"
        )
        beats_md = "\n\n".join(
            f"## {b.get('tag', f'Beat {i + 1}')}\n{b['text']}" for i, b in enumerate(beats)
        )
        script_content = f"# {self.topic} — Production Script\n\n{beats_md}\n\n## Sources\n{sources_md}\n"
        script_file.write_text(script_content, encoding="utf-8")
        (self.work_dir / "beats.json").write_text(json.dumps(beats, indent=2), encoding="utf-8")
        self.log("Script Architect", f"Saved script & beats to {self.work_dir}")
        return script_file, beats

    def run_studio_director_agent(self, script_file: Path) -> dict:
        self.log("Studio Director", f"Selecting visual language (preference: '{self.style_preference}') across 120 styles...")
        script_text = script_file.read_text(encoding="utf-8")
        style_data = select_style(script_text, preferred_style=self.style_preference)
        meta = style_data["metadata"]
        tokens = meta.get("tokens", {})

        self.log(
            "Studio Director",
            f"Selected Style: '{style_data['selected_style']}' ({meta.get('name', style_data['selected_style'])}) "
            f"| Mode: {style_data.get('selection_mode')} | Accent: {tokens.get('accent')}",
        )
        (self.work_dir / "director_plan.json").write_text(json.dumps(style_data, indent=2), encoding="utf-8")
        return style_data

    def run_voice_audio_engineer(self, beats: list[dict]) -> dict:
        self.log("Voice & Audio Engineer", f"Synthesizing & mastering {len(beats)} beats (SFX={'ON' if self.include_sfx else 'OFF'})...")
        audio_out = self.work_dir / "narration_master.wav"
        audio_info = build_synced_beat_audio(
            beats=beats,
            output_path=audio_out,
            voice_id=self.voice_profile,
            edge_voice=self.edge_voice,
            include_sfx=self.include_sfx,
        )
        timeline_file = self.work_dir / "audio_timeline.json"
        timeline_file.write_text(json.dumps(audio_info, indent=2), encoding="utf-8")
        self.log(
            "Voice & Audio Engineer",
            f"Mastered {audio_info['duration']:.2f}s audio via {', '.join(audio_info['engines'])} -> {audio_out.name}",
        )
        return audio_info

    def run_motion_graphics_artist(self, style_data: dict, audio_info: dict) -> Path:
        style_id = style_data["selected_style"]
        self.log("Motion Graphics Artist", f"Authoring {self.width}x{self.height} kinetic HTML5/GSAP scene in '{style_id}'...")
        scene_dir = self.work_dir / "scene"
        scene_dir.mkdir(parents=True, exist_ok=True)

        # Copy canonical studio.js
        canonical_js = SCRIPTS_DIR / "studio.js"
        shutil.copy2(canonical_js, scene_dir / "studio.js")

        html_code = build_kinetic_scene_html(
            topic=self.topic,
            style_data=style_data,
            timed_beats=audio_info["beats"],
            total_duration=audio_info["duration"],
            width=self.width,
            height=self.height,
        )
        (scene_dir / "index.html").write_text(html_code, encoding="utf-8")
        self.log("Motion Graphics Artist", f"Scene authored at {scene_dir / 'index.html'}")
        return scene_dir

    def run_video_assembler(self, scene_dir: Path, audio_info: dict) -> tuple[Path, dict]:
        self.log("Video Assembler", f"Rendering frames ({self.fps} fps, quality={self.quality}, codec={self.codec})...")
        raw_video = self.work_dir / "visual_raw.mp4"
        render_stats = render_scene(
            project_path=scene_dir,
            output_path=raw_video,
            fps=self.fps,
            quality=self.quality,
            codec=self.codec,
            width_override=self.width,
            height_override=self.height,
            duration_override=audio_info["duration"],
        )

        master_mp4 = self.work_dir / f"{self.slug}-master.mp4"
        self.log("Video Assembler", f"Muxing video + mastered audio -> {master_mp4.name}...")
        ffmpeg_cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(raw_video),
            "-i", str(audio_info["audio_path"]),
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            "-shortest",
            str(master_mp4),
        ]
        subprocess.run(ffmpeg_cmd, check=True)

        date_tag = datetime.date.today().strftime("%Y%m%d")
        export_file = self.export_dir / f"{date_tag}-{self.slug}.mp4"
        shutil.copy2(master_mp4, export_file)
        self.log("Video Assembler", f"Exported master video to {export_file}")
        return export_file, render_stats

    def run_packaging_and_qa(
        self,
        export_mp4: Path,
        style_data: dict,
        audio_info: dict,
        render_stats: dict,
        hook: str,
        hook_score: dict | None,
    ) -> dict:
        self.log("SEO & Packaging", "Generating metadata.md and human-approval checklist.md...")
        today = datetime.date.today().isoformat()
        sources_block = (
            "\n".join(f"- {name}: {url}" for name, url in GTA6_OFFICIAL_SOURCES)
            if self.is_gta6
            else "- Verify and link primary documentation sources before upload."
        )
        chapters_block = "\n".join(
            f"{int(b['start'] // 60):02d}:{int(b['start'] % 60):02d} — {b.get('headline', b.get('tag', 'Section'))}"
            for b in audio_info["beats"]
        )
        short_tag = "#Shorts " if self.video_format == "short" else ""
        if self.is_gta6:
            primary_hashtags = "#Shorts #GTA6 #RockstarGames #Gaming"
        else:
            clean_topic_tag = "".join(w.capitalize() for w in re.sub(r"[^a-zA-Z0-9 ]", "", self.topic).split()[:2])
            primary_hashtags = f"#Shorts #{clean_topic_tag} #CreatorRadar"

        clean_topic_short = self.topic[:45].strip()
        title_option_1 = f"What happens at the end of this {clean_topic_short} is wild"[:55]
        title_option_2 = f"Don't ignore this about {clean_topic_short}"[:55]
        title_option_3 = f"{hook[:55].strip()}"

        metadata_md = f"""# YouTube Metadata — {self.topic}

## 2026 High-CTR Title Options (< 55 chars for Mobile Browse)
1. `{title_option_1}` (End-Payoff Curiosity Hook)
2. `{title_option_2}` (Reverse-Psychology Friction Hook)
3. `{title_option_3}` (Core Hook Line)

## Description
{hook}

{primary_hashtags}

### Chapters
{chapters_block}

### Sources
{sources_block}

### 2026 Browse Funnel & Upload Checklist
- **Device:** Transfer MP4 to mobile (Google Drive/AirDrop) and upload via YouTube Mobile App.
- **Thumbnail:** Tap the pencil icon in the mobile app to pick the custom 1-frame thumbnail.
- **Related Video:** Link your flagship long-form video or series short to trigger channel binge loops.
- **Staging & Timing:** Set to **UNLISTED** first for Content ID clearance. Publish 60 min before peak audience hours.
- **Category:** Select explicit category (Gaming / Tech) — do NOT add > 5 hashtags.

---
{REQUIRED_DISCLOSURE}
"""
        metadata_file = self.export_dir / "metadata.md"
        metadata_file.write_text(metadata_md, encoding="utf-8")

        checklist_md = f"""# Pre-Upload Human Approval Checklist — {self.topic}

- **Export File:** `{export_mp4.name}`
- **Generated:** `{today}`
- **Style:** `{style_data['selected_style']}`
- **Audio Engine:** `{', '.join(audio_info['engines'])}`

## Required Quality Gates (Rule 4 — Human Sign-off Required)
- [ ] Fact-check sign-off: Every claim verified against primary sources
- [ ] No first-hand gameplay claims / no fabricated mechanics
- [ ] Visual & audio playback reviewed by human
- [ ] AI disclosure line verified in YouTube description
- [ ] Copyright clearance confirmed (all assets original or cleared)

## 2026 Million-View Mobile Upload Protocol (Browse Features Funnel)
- [ ] High-contrast thumbnail frame identified or baked in
- [ ] Staged as UNLISTED for Content ID clearance and HD 1080p60 processing
- [ ] Custom thumbnail frame selected via YouTube Mobile App pencil icon (enables Browse/Home traffic)
- [ ] Title uses curiosity / end-payoff hook (< 55 characters)
- [ ] Hashtags kept strictly to 3–5 niche tags (prevents algorithm spam filters)
- [ ] Related Video linked to channel long-form video/series
- [ ] Published/Scheduled 60 minutes prior to audience peak activity window
- [ ] **Final human approval** to publish
"""
        checklist_file = self.export_dir / "checklist.md"
        checklist_file.write_text(checklist_md, encoding="utf-8")

        # Run real VideoReviewerAgent on exported video
        self.log("Quality & Compliance Gatekeeper", "Running automated technical, loudness, motion, and compliance audit...")
        reviewer = VideoReviewerAgent(
            video_path=export_mp4,
            style_id=style_data["selected_style"],
            beats_file=self.work_dir / "audio_timeline.json",
            metadata_file=metadata_file,
        )
        reviewer.inspect_technical()
        reviewer.inspect_audio_loudness()
        reviewer.extract_and_verify_motion()
        reviewer.inspect_compliance()
        passed, review_data, _ = reviewer.generate_review_report()

        project_manifest = {
            "slug": self.slug,
            "topic": self.topic,
            "format": self.video_format,
            "resolution": f"{self.width}x{self.height}",
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "style": {
                "id": style_data["selected_style"],
                "name": style_data["metadata"].get("name"),
                "tokens": style_data["metadata"].get("tokens"),
            },
            "hook": hook,
            "hook_score": hook_score,
            "audio": {
                "duration": audio_info["duration"],
                "engines": audio_info["engines"],
                "sfx_enabled": audio_info["sfx_enabled"],
                "beats_count": len(audio_info["beats"]),
            },
            "render": render_stats,
            "export_video": export_mp4.name,
            "qa_passed": passed,
            "qa_verdict": review_data["verdict"],
            "human_approved": False,
        }
        (self.export_dir / "project.json").write_text(json.dumps(project_manifest, indent=2), encoding="utf-8")
        self.log(
            "Quality & Compliance Gatekeeper",
            f"QA Verdict: {review_data['verdict']} | Loudness: {review_data['metrics'].get('loudness_lufs')} LUFS | "
            f"Human Approval: PENDING",
        )
        return project_manifest

    def execute_pipeline(self) -> dict:
        self.log("Pipeline Coordinator", f"=== Starting CreatorRadar Production Wave: '{self.topic}' ({self.video_format}) ===")
        hook, hook_score = self.run_trend_and_hook_agent()
        script_file, beats = self.run_script_architect_agent(hook)
        style_data = self.run_studio_director_agent(script_file)
        audio_info = self.run_voice_audio_engineer(beats)
        scene_dir = self.run_motion_graphics_artist(style_data, audio_info)
        export_mp4, render_stats = self.run_video_assembler(scene_dir, audio_info)
        manifest = self.run_packaging_and_qa(export_mp4, style_data, audio_info, render_stats, hook, hook_score)
        self.log("Pipeline Coordinator", f"=== Production Wave Complete: {export_mp4} ===")
        return manifest


def main():
    parser = argparse.ArgumentParser(description="CreatorRadar Multi-Agent Production Studio")
    parser.add_argument("positional_topic", nargs="?", default=None, help="Video topic")
    parser.add_argument("--topic", dest="flag_topic", default=None, help="Video topic (flag form)")
    parser.add_argument("--slug", default=None, help="Output folder slug")
    parser.add_argument("--format", choices=["short", "long"], default="short", help="short (9:16) or long (16:9)")
    parser.add_argument("--style", default="auto", help="Visual style ID or 'auto'")
    parser.add_argument("--voice", default=DEFAULT_PROFILE_ID, help="VoiceStudio Profile ID")
    parser.add_argument("--edge-voice", default=DEFAULT_EDGE_VOICE, help="Fallback Edge-TTS voice name")
    parser.add_argument("--script", default=None, help="Optional path to custom script.md")
    parser.add_argument("--beats-json", default=None, help="Optional path to custom beats.json")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--quality", choices=["draft", "standard", "high"], default="high")
    parser.add_argument("--codec", choices=["auto", "nvenc", "cpu"], default="auto")
    parser.add_argument("--no-sfx", action="store_true")
    args = parser.parse_args()

    topic = args.flag_topic or args.positional_topic or "GTA VI Storage Requirements PS5"

    studio = MultiAgentStudio(
        topic=topic,
        output_slug=args.slug,
        video_format=args.format,
        style_preference=args.style,
        voice_profile=args.voice,
        edge_voice=args.edge_voice,
        script_path=args.script,
        beats_json=args.beats_json,
        fps=args.fps,
        quality=args.quality,
        codec=args.codec,
        include_sfx=not args.no_sfx,
    )
    manifest = studio.execute_pipeline()
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
