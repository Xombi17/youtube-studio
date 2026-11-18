#!/usr/bin/env python3
"""
CreatorRadar Vox Paper-Collage Scene Builder
Builds a living, tactile 9:16 (or 16:9) Vox-style paper-collage HTML5/GSAP + studio.js
scene using transparent die-cut PNG paper cutouts, torn kraft/newsprint layers,
masking tape strips, 12fps stop-motion sticker wobble, animated SVG editorial charts,
paper-tear beat transitions, and word-by-word kinetic cutout captions.
"""

import html
import json
import shutil
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


def build_vox_scene(
    project_dir: Path,
    timed_beats: list[dict],
    total_duration: float,
    title: str,
    width: int = 1080,
    height: int = 1920,
) -> Path:
    scene_dir = project_dir / "scene"
    cutouts_dst = scene_dir / "cutouts"
    cutouts_dst.mkdir(parents=True, exist_ok=True)

    # Copy studio.js and cutout PNGs into scene directory so local HTTP server serves them cleanly
    shutil.copy2(WORKSPACE_ROOT / "scripts" / "studio.js", scene_dir / "studio.js")
    cutouts_src = project_dir / "cutouts"
    for p in cutouts_src.glob("*.png"):
        shutil.copy2(p, cutouts_dst / p.name)

    beats_json = json.dumps(timed_beats, ensure_ascii=False)
    safe_title = html.escape(title.upper())

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width={width}, height={height}" />
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Anton&family=Space+Grotesk:wght@600;700&family=IBM+Plex+Mono:wght@600;700&display=swap" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<script src="studio.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{
    width: {width}px; height: {height}px; overflow: hidden;
    background: #F3EBD8; color: #141413;
    font-family: 'Space Grotesk', sans-serif;
  }}
  #root {{
    position: relative; width: {width}px; height: {height}px; overflow: hidden;
    background: #F3EBD8;
  }}

  /* Full-bleed paper background with continuous slow Ken Burns drift */
  #paper-bg {{
    position: absolute; inset: -80px;
    background-color: #F3EBD8;
    will-change: transform, background-color;
  }}

  /* Halftone Ben-Day dot print texture overlay */
  #halftone {{
    position: absolute; inset: -40px; pointer-events: none; z-index: 4;
    background-image: radial-gradient(circle, rgba(20, 20, 19, 0.13) 1.6px, transparent 1.9px);
    background-size: 16px 16px;
    mix-blend-mode: multiply;
  }}

  /* Subtle archival paper fiber grid & creases */
  #paper-grain {{
    position: absolute; inset: 0; pointer-events: none; z-index: 45;
    background-image:
      repeating-linear-gradient(0deg, rgba(0,0,0,0.018) 0px, rgba(0,0,0,0.018) 1px, transparent 1px, transparent 3px),
      repeating-linear-gradient(90deg, rgba(255,255,255,0.025) 0px, rgba(255,255,255,0.025) 1px, transparent 1px, transparent 5px);
    opacity: 0.7;
  }}

  /* Decorative torn newsprint collage strip across background */
  #newsprint-strip {{
    position: absolute; left: -60px; right: -60px; top: 430px; height: 420px;
    background: #EDE3CC;
    opacity: 0.32;
    transform: rotate(-3.5deg);
    clip-path: polygon(
      0% 4%, 6% 1%, 13% 5%, 22% 2%, 31% 6%, 41% 1%, 52% 4%, 63% 1%, 74% 5%, 86% 2%, 95% 4%, 100% 2%,
      100% 96%, 92% 99%, 81% 94%, 70% 98%, 58% 95%, 47% 99%, 36% 95%, 24% 98%, 12% 95%, 4% 99%, 0% 96%
    );
    z-index: 3;
    border-top: 3px dashed rgba(20,20,19,0.22);
    border-bottom: 3px dashed rgba(20,20,19,0.22);
  }}

  /* Torn-Paper Headline Banner (Full-Bleed Canvas — Zero Masthead Chrome) */
  #headline-banner {{
    position: absolute; top: 96px; left: 56px; right: 56px; z-index: 22;
    display: flex; flex-direction: column; align-items: flex-start; gap: 14px;
    will-change: transform, opacity;
  }}
  #headline-strip {{
    display: inline-block;
    background: #141413; color: #FAF6EC;
    padding: 18px 36px 14px 36px;
    font-family: 'Anton', sans-serif; font-size: 98px; line-height: 0.96;
    letter-spacing: 0.02em; text-transform: uppercase;
    box-shadow: 10px 10px 0 rgba(20, 20, 19, 0.28);
    clip-path: polygon(
      0% 3%, 8% 0%, 19% 3%, 33% 0%, 48% 2%, 66% 0%, 82% 3%, 94% 0%, 100% 3%,
      99% 97%, 88% 100%, 73% 97%, 55% 100%, 37% 97%, 18% 100%, 6% 97%, 0% 99%
    );
  }}
  #stat-badge {{
    display: inline-flex; align-items: baseline; gap: 14px;
    background: #E6392E; color: #FAF6EC;
    padding: 10px 24px;
    font-family: 'IBM Plex Mono', monospace;
    box-shadow: 6px 6px 0 rgba(20,20,19,0.28);
    transform: rotate(1.4deg);
  }}
  #stat-val {{ font-family: 'Anton', sans-serif; font-size: 46px; letter-spacing: 0.03em; }}
  #stat-label {{ font-size: 20px; font-weight: 700; letter-spacing: 0.08em; }}

  /* Hero Paper Cutout Stage */
  #cutout-stage {{
    position: absolute; left: 0; right: 0; top: 410px; height: 730px;
    display: flex; align-items: center; justify-content: center;
    z-index: 16; pointer-events: none;
  }}
  #cutout-wrap {{
    position: relative; display: flex; align-items: center; justify-content: center;
    will-change: transform, opacity;
  }}
  #hero-cutout {{
    max-width: 740px; max-height: 670px; width: auto; height: auto;
    display: block; user-select: none;
  }}

  /* Translucent Masking Tape Corners */
  .tape {{
    position: absolute; width: 148px; height: 42px;
    background: rgba(246, 232, 184, 0.72);
    border-left: 2px dashed rgba(130, 110, 70, 0.28);
    border-right: 2px dashed rgba(130, 110, 70, 0.28);
    box-shadow: 0 3px 6px rgba(0,0,0,0.12);
    z-index: 20;
  }}
  #tape-tl {{ top: 18px; left: 46px; transform: rotate(-28deg); }}
  #tape-br {{ bottom: 26px; right: 42px; transform: rotate(-24deg); }}

  /* Editorial Data Chart Card (shown on data beats) */
  #chart-card {{
    position: absolute; left: 66px; right: 66px; top: 1125px;
    background: #FAF6EC; color: #141413;
    border: 4px solid #141413;
    box-shadow: 10px 10px 0 rgba(20, 20, 19, 0.35);
    padding: 24px 28px; z-index: 24;
    display: none; will-change: transform, opacity;
  }}
  .chart-title {{
    font-family: 'IBM Plex Mono', monospace; font-size: 19px; font-weight: 700;
    letter-spacing: 0.08em; margin-bottom: 16px; color: #141413;
    border-bottom: 2px solid #141413; padding-bottom: 8px;
  }}
  .bar-row {{
    display: flex; align-items: center; gap: 14px; margin-bottom: 12px;
  }}
  .bar-row:last-child {{ margin-bottom: 0; }}
  .bar-lbl {{
    width: 140px; font-family: 'IBM Plex Mono', monospace; font-size: 20px; font-weight: 700;
  }}
  .bar-track {{
    flex: 1; height: 34px; background: #E4DAC4; border: 2px solid #141413; position: relative; overflow: hidden;
  }}
  .bar-fill {{
    height: 100%; width: 0%; background: #E6392E;
  }}
  .bar-num {{
    width: 96px; text-align: right; font-family: 'Anton', sans-serif; font-size: 30px;
  }}

  /* Kinetic Cutout Captions (Lower Safe Area) */
  #caption-stage {{
    position: absolute; left: 52px; right: 52px; bottom: 135px;
    z-index: 30;
    display: flex; flex-wrap: wrap; justify-content: center; align-items: center;
    gap: 10px 12px; padding: 24px 26px;
    background: rgba(20, 20, 19, 0.92);
    border: 4px solid #FAF6EC;
    box-shadow: 10px 10px 0 rgba(0, 0, 0, 0.32);
    min-height: 175px;
  }}
  .cword {{
    font-family: 'Space Grotesk', sans-serif; font-size: 48px; font-weight: 700;
    line-height: 1.15; color: #9CA3AF; padding: 2px 6px;
    display: inline-block;
  }}
  .cword.spoken {{ color: #FAF6EC; }}
  .cword.active {{
    background: #F7D046; color: #141413;
    transform: rotate(-1.5deg) scale(1.08);
    box-shadow: 4px 4px 0 #E6392E;
  }}

  /* Paper-Tear Wipe Transition Overlay */
  #tear-wipe {{
    position: absolute; inset: -40px; z-index: 40; pointer-events: none;
    background: #FAF6EC;
    clip-path: polygon(
      0% 0%, 100% 0%, 100% 94%, 91% 99%, 81% 93%, 70% 99%, 58% 94%, 46% 99%, 34% 93%, 22% 99%, 11% 94%, 0% 98%
    );
    transform: translateY(-120%);
  }}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{total_duration:.3f}" data-width="{width}" data-height="{height}">
  <div id="paper-bg"></div>
  <div id="newsprint-strip"></div>
  <div id="halftone"></div>

  <div id="headline-banner">
    <div id="headline-strip">{safe_title}</div>
    <div id="stat-badge">
      <span id="stat-val"></span>
      <span id="stat-label"></span>
    </div>
  </div>

  <div id="cutout-stage">
    <div id="cutout-wrap">
      <div class="tape" id="tape-tl"></div>
      <img id="hero-cutout" src="cutouts/{timed_beats[0]['cutout']}" alt="collage cutout" />
      <div class="tape" id="tape-br"></div>
    </div>
  </div>

  <div id="chart-card"></div>

  <div id="caption-stage"></div>

  <div id="tear-wipe"></div>
  <div id="paper-grain"></div>
</div>

<script>
  const S = STUDIO;
  const BEATS = {beats_json};
  const TOTAL = {total_duration:.3f};

  // Preload all cutout images so switching beats is instant on deterministic frame capture
  const PRELOADED = BEATS.map((b) => {{
    const im = new Image();
    im.src = 'cutouts/' + b.cutout;
    return im;
  }});

  const root = document.getElementById('root');
  const paperBg = document.getElementById('paper-bg');
  const newsStrip = document.getElementById('newsprint-strip');
  const halftone = document.getElementById('halftone');
  const headlineBanner = document.getElementById('headline-banner');
  const headlineStrip = document.getElementById('headline-strip');
  const statBadge = document.getElementById('stat-badge');
  const statVal = document.getElementById('stat-val');
  const statLabel = document.getElementById('stat-label');
  const cutoutStage = document.getElementById('cutout-stage');
  const cutoutWrap = document.getElementById('cutout-wrap');
  const heroCutout = document.getElementById('hero-cutout');
  const chartCard = document.getElementById('chart-card');
  const captionStage = document.getElementById('caption-stage');
  const tearWipe = document.getElementById('tear-wipe');

  let activeBeatIndex = -1;
  let wordNodes = [];
  let barFillNodes = [];
  let cliffPath = null;

  function mountBeat(beat, idx) {{
    paperBg.style.backgroundColor = beat.bg;
    root.style.backgroundColor = beat.bg;

    headlineStrip.textContent = beat.headline;
    headlineStrip.style.backgroundColor = beat.ink === '#FAF6EC' ? '#FAF6EC' : '#141413';
    headlineStrip.style.color = beat.ink === '#FAF6EC' ? '#141413' : '#FAF6EC';

    statBadge.style.backgroundColor = beat.accent;
    statBadge.style.color = beat.accent === '#F7D046' ? '#141413' : '#FAF6EC';
    statVal.textContent = beat.stat;
    statLabel.textContent = beat.stat_label;

    heroCutout.src = 'cutouts/' + beat.cutout;

    // Position cutout higher when chart card is visible on data beats
    if (beat.chart) {{
      cutoutStage.style.top = '385px';
      cutoutStage.style.height = '650px';
      heroCutout.style.maxHeight = '560px';
      heroCutout.style.maxWidth = '640px';
      renderChartMarkup(beat.chart, beat.accent, beat.accent2);
      chartCard.style.display = 'block';
    }} else {{
      cutoutStage.style.top = '455px';
      cutoutStage.style.height = '810px';
      heroCutout.style.maxHeight = '720px';
      heroCutout.style.maxWidth = '780px';
      chartCard.style.display = 'none';
      barFillNodes = [];
      cliffPath = null;
    }}

    // Mount caption words
    captionStage.innerHTML = '';
    const words = beat.text.split(/\\s+/).filter(Boolean);
    wordNodes = words.map((w) => {{
      const s = document.createElement('span');
      s.className = 'cword';
      s.textContent = w;
      captionStage.appendChild(s);
      return s;
    }});
  }}

  function renderChartMarkup(chart, accent, accent2) {{
    barFillNodes = [];
    cliffPath = null;
    if (chart.type === 'bars') {{
      let rows = chart.items.map((it, i) => `
        <div class="bar-row">
          <div class="bar-lbl">${{it.label}}</div>
          <div class="bar-track"><div class="bar-fill" data-target="${{(it.val / it.max) * 100}}" style="background:${{i === 1 ? '#E6392E' : '#141413'}}"></div></div>
          <div class="bar-num">${{it.display}}</div>
        </div>
      `).join('');
      chartCard.innerHTML = `<div class="chart-title">${{chart.title}}</div>${{rows}}`;
      barFillNodes = Array.from(chartCard.querySelectorAll('.bar-fill'));
    }} else if (chart.type === 'cliff') {{
      chartCard.innerHTML = `
        <div class="chart-title">${{chart.title}}</div>
        <svg viewBox="0 0 880 140" width="100%" height="140">
          <line x1="20" y1="30" x2="860" y2="30" stroke="#D1C7B0" stroke-width="2" stroke-dasharray="6 6"/>
          <line x1="20" y1="115" x2="860" y2="115" stroke="#141413" stroke-width="3"/>
          <path id="cliff-line" d="M 30 34 L 280 36 L 470 32 L 540 35 L 620 112 L 840 108"
                fill="none" stroke="#E6392E" stroke-width="10" stroke-linecap="round" stroke-linejoin="round"
                stroke-dasharray="950" stroke-dashoffset="950" />
          <text x="30" y="135" font-family="IBM Plex Mono" font-size="18" font-weight="700" fill="#141413">${{chart.before}}</text>
          <text x="580" y="135" font-family="IBM Plex Mono" font-size="18" font-weight="700" fill="#E6392E">${{chart.after}}</text>
        </svg>
      `;
      cliffPath = document.getElementById('cliff-line');
    }} else if (chart.type === 'compare') {{
      chartCard.innerHTML = `
        <div class="chart-title">${{chart.title}}</div>
        <div class="bar-row">
          <div class="bar-lbl" style="width:210px">${{chart.a_label}}</div>
          <div class="bar-track"><div class="bar-fill" data-target="${{chart.a_pct}}" style="background:#E6392E"></div></div>
          <div class="bar-num">${{chart.a_val}}</div>
        </div>
        <div class="bar-row">
          <div class="bar-lbl" style="width:210px">${{chart.b_label}}</div>
          <div class="bar-track"><div class="bar-fill" data-target="${{chart.b_pct}}" style="background:#16A34A"></div></div>
          <div class="bar-num">${{chart.b_val}}</div>
        </div>
      `;
      barFillNodes = Array.from(chartCard.querySelectorAll('.bar-fill'));
    }}
  }}

  STUDIO.play(function render(t) {{
    let idx = 0;
    for (let i = 0; i < BEATS.length; i++) {{
      if (t >= BEATS[i].start) idx = i;
    }}
    const beat = BEATS[idx];
    if (idx !== activeBeatIndex) {{
      mountBeat(beat, idx);
      activeBeatIndex = idx;
    }}

    const localT = Math.max(0, t - beat.start);
    const dur = Math.max(0.2, beat.duration);
    const beatP = Math.min(1, localT / dur);

    // 12fps quantized stop-motion clock (authentic Vox hand-animated paper feel!)
    const step12 = Math.floor(t * 12);
    const jitterAngle = ((step12 % 4) - 1.5) * 0.85;
    const jitterY = ((step12 % 3) - 1) * 3.0;

    // Slow continuous paper background zoom + subtle parallax
    const kb = 1.0 + 0.06 * beatP;
    const bgX = Math.sin(t * 0.55) * 14;
    paperBg.style.transform = `translate(${{bgX.toFixed(1)}}px, 0px) scale(${{kb.toFixed(4)}})`;
    halftone.style.transform = `translate(${{(-bgX * 0.6).toFixed(1)}}px, ${{(Math.cos(t * 0.4) * 8).toFixed(1)}}px)`;
    newsStrip.style.transform = `rotate(${{(-3.5 + Math.sin(idx * 1.7) * 2.5).toFixed(2)}}deg) translateX(${{(Math.sin(t * 0.35) * 22).toFixed(1)}}px)`;

    // Paper-tear wipe flash at beat transition (except frame 0)
    if (idx > 0 && localT < 0.24) {{
      const wp = localT / 0.24;
      tearWipe.style.transform = `translateY(${{S.mix(-10, 115, wp).toFixed(1)}}%)`;
      tearWipe.style.opacity = (1 - wp * 0.6).toFixed(3);
    }} else {{
      tearWipe.style.transform = 'translateY(-130%)';
      tearWipe.style.opacity = '0';
    }}

    // Headline stamp-in
    const headIn = S.seg(localT, 0.02, 0.30, 'back.out(1.4)');
    const headTilt = -1.2 + ((step12 % 2) ? 0.35 : -0.35);
    headlineBanner.style.transform = `translateY(${{S.mix(-55, 0, headIn).toFixed(1)}}px) rotate(${{headTilt.toFixed(2)}}deg)`;
    headlineBanner.style.opacity = Math.min(1, localT / 0.14).toFixed(3);

    // Hero paper cutout pop-in + Ken Burns drift + 12fps tactile stop-motion sticker wobble!
    const cutIn = S.seg(localT, 0.06, 0.36, 'back.out(1.5)');
    const cutScale = S.mix(0.68, 1.0, cutIn) * (1.0 + 0.065 * beatP);
    const cutY = S.mix(120, 0, cutIn) + jitterY;
    const baseTilt = (idx % 2 === 0 ? -1.8 : 1.8) + jitterAngle;
    cutoutWrap.style.transform = `translateY(${{cutY.toFixed(1)}}px) scale(${{cutScale.toFixed(4)}}) rotate(${{baseTilt.toFixed(2)}}deg)`;
    cutoutWrap.style.opacity = Math.min(1, localT / 0.18).toFixed(3);

    // Animate editorial chart card if active on this beat
    if (beat.chart) {{
      const chIn = S.seg(localT, 0.25, 0.35, 'power3.out');
      chartCard.style.transform = `translateY(${{S.mix(60, 0, chIn).toFixed(1)}}px)`;
      chartCard.style.opacity = chIn.toFixed(3);

      const barP = S.seg(localT, 0.45, 0.95, 'power3.out');
      barFillNodes.forEach((el, bi) => {{
        const target = Number(el.dataset.target || 0);
        const staggerP = S.seg(localT, 0.42 + bi * 0.14, 0.72, 'power3.out');
        el.style.width = `${{(target * staggerP).toFixed(1)}}%`;
      }});
      if (cliffPath) {{
        cliffPath.style.strokeDashoffset = `${{S.mix(950, 0, barP).toFixed(1)}}`;
      }}
    }}

    // Kinetic word-by-word captions (focused window of 7 words for bold phone readability)
    const totalWords = wordNodes.length;
    if (totalWords > 0) {{
      const activeW = Math.min(totalWords - 1, Math.floor(beatP * totalWords));
      const winSize = 7;
      const wStart = Math.floor(activeW / winSize) * winSize;
      const wEnd = Math.min(totalWords, wStart + winSize);
      for (let w = 0; w < totalWords; w++) {{
        const node = wordNodes[w];
        if (w < wStart || w >= wEnd) {{
          node.style.display = 'none';
          continue;
        }}
        node.style.display = 'inline-block';
        if (w === activeW) {{
          node.className = 'cword active';
          node.style.backgroundColor = beat.accent;
          node.style.color = beat.accent === '#F7D046' ? '#141413' : '#FAF6EC';
        }} else if (w < activeW) {{
          node.className = 'cword spoken';
          node.style.backgroundColor = 'transparent';
          node.style.color = '#FAF6EC';
        }} else {{
          node.className = 'cword';
          node.style.backgroundColor = 'transparent';
          node.style.color = '#9CA3AF';
        }}
      }}
    }}

  }}, {{ loop: false }});
</script>
</body>
</html>
"""
    (scene_dir / "index.html").write_text(html_doc, encoding="utf-8")
    return scene_dir
