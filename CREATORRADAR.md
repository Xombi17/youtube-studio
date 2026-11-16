# CreatorRadar — YouTube Studio Master Guide

> [!IMPORTANT]
> **Human approval required before any upload.** No video may be published to YouTube without explicit channel owner sign-off. See [§10 Creating New Videos](#10-creating-new-videos) for the full workflow.

---

## 1. What is CreatorRadar

CreatorRadar is an AI-assisted YouTube monetization studio built around a ~11,000-subscriber channel working toward re-monetization through the YouTube Partner Program. The studio produces GTA VI tutorials, gaming news, AI stories, green-screen commentary, and tech/AI explainers using a local skill layer of 17 agent skills that covers every stage from trend discovery through final export. All factual content is sourced from primary official documentation; no claim is published without a verified source ledger. The studio prioritises fast Shorts output (30–60 s vertical) alongside longer explainers, targeting 3–5 Shorts and 1–2 long-form videos per week to accumulate watch hours and unlock monetization.

---

## 2. Quick Start

Start a new agent session in this directory and say: *"Create a 45-second GTA VI tutorial about [topic]."* The agent will read `AGENTS.md` (or `CLAUDE.md` for Claude Code), load the **production-pipeline** skill, and run all stages automatically — trend check, research, script, storyboard, render, quality review, SEO metadata — stopping at the three human-approval gates before proceeding. No manual skill invocation needed; the pipeline orchestrates everything.

---

## 3. Studio Structure

```
youtube/
├── AGENTS.md               # Codex / Antigravity skill routing table + studio rules
├── CLAUDE.md               # Claude Code skill routing table (same content)
├── CREATORRADAR.md         # This file — master studio guide
├── README.md               # Existing workspace README
├── config/                 # Channel strategy, production rules, model routing, GTA VI source registry
│   ├── channel-strategy.md
│   ├── production-rules.md
│   ├── model-routing.md
│   └── gta6-sources.md
├── skills/                 # 17 local agent skills (see §4)
├── .claude/
│   └── skills/             # Symlinks → ../../skills/* for Claude Code discovery
├── research/               # One subdirectory per topic; claims.md = verified ledger
│   ├── gta6-core/
│   ├── gta6-storage/
│   ├── gta6-preload/
│   └── gta6-editions/
├── scripts/                # Written scripts and storyboards per topic
│   ├── gta6-storage/
│   ├── gta6-preload/
│   └── gta6-editions/
├── renders/                # Scene MP4s and narration WAV files per topic (pre-QA)
├── exports/                # Final MP4s after quality review + metadata + checklists
├── dashboard/              # Trend queue, ideas backlog, production status tracker
│   ├── README.md
│   └── ideas-queue.md
└── gta-vi-event/           # Working HyperFrames project — reference implementation
    └── gta6-storage-short/ # First tutorial: storage requirements short
```

---

## 4. Skills Reference Table

| Skill | Directory | When to Use |
|---|---|---|
| `trend-scout` | `skills/trend-scout/` | Discover timely YouTube Shorts ideas from current evidence |
| `source-researcher` | `skills/source-researcher/` | Verify claims and collect primary sources for any topic |
| `gta6-researcher` | `skills/gta6-researcher/` | Research GTA VI facts from official Rockstar/PlayStation/Xbox sources only |
| `shorts-scriptwriter` | `skills/shorts-scriptwriter/` | Write a timed 30–60 s vertical Short script from a verified premise |
| `tutorial-scriptwriter` | `skills/tutorial-scriptwriter/` | Write factual GTA VI tutorial scripts (30–60 s vertical format) |
| `visual-director` | `skills/visual-director/` | Plan shot list, typography and motion for footage or green-screen |
| `video-director` | `skills/video-director/` | Shot-by-shot visual execution plan for GTA VI tutorials and gaming content |
| `indian-art-styles` | `skills/indian-art-styles/` | Direct animation influenced by Indian art traditions with accurate attribution |
| `clip-rights-checker` | `skills/clip-rights-checker/` | Clear third-party footage, music and images before production |
| `copyright-checker` | `skills/copyright-checker/` | Verify all assets cleared for YouTube; GTA VI–specific guidance |
| `ai-video-generator` | `skills/ai-video-generator/` | Generate video assets via HyperFrames HTML+GSAP and FFmpeg compositing |
| `video-editor` | `skills/video-editor/` | Assemble final video from scenes and audio using FFmpeg |
| `video-quality-reviewer` | `skills/video-quality-reviewer/` | Review rendered video: technical, visual, audio, factual, rights |
| `channel-analyst` | `skills/channel-analyst/` | Interpret channel and Shorts analytics; recommend experiments |
| `youtube-seo` | `skills/youtube-seo/` | Generate title, description, tags, thumbnail concept, chapter markers |
| `production-pipeline` | `skills/production-pipeline/` | Orchestrate the full TOPIC → PUBLISHED VIDEO pipeline automatically |
| `lemo-opuscar` | `skills/lemo-opuscar/` *(linked to Claude plugin)* | Create a Lemo-Opuscar–styled film (oil paint, watercolor, ukiyo-e, etc.) |

---

## 5. Production Pipeline

The pipeline has **11 stages** and **3 human-approval gates** (marked 🔐).

| # | Stage | Skill | Output |
|---|---|---|---|
| 1 | **Trend Discovery** | `trend-scout` | Ranked list of timely ideas |
| 2 | **Research & Claim Verification** | `gta6-researcher` / `source-researcher` | `research/<topic>/claims.md` |
| 3 🔐 | **Human: Approve Claim Ledger** | *(manual review)* | Go / No-go on facts |
| 4 | **Script Writing** | `tutorial-scriptwriter` / `shorts-scriptwriter` | `scripts/<topic>/script.md` |
| 5 | **Visual Direction & Storyboard** | `video-director` / `visual-director` | `scripts/<topic>/storyboard.md` |
| 6 | **Rights Clearance** | `copyright-checker` / `clip-rights-checker` | `scripts/<topic>/rights.md` |
| 7 | **Asset Generation** | `ai-video-generator` | `renders/<topic>/scene-N.mp4` |
| 8 | **Video Assembly** | `video-editor` | `renders/<topic>/final-draft.mp4` |
| 9 🔐 | **Human: Quality Review** | `video-quality-reviewer` *(flags issues)* | Approve or request revision |
| 10 | **SEO Metadata** | `youtube-seo` | `exports/<topic>/metadata.md` |
| 11 🔐 | **Human: Final Approval & Upload** | *(manual)* | Published to YouTube |

> [!NOTE]
> The `production-pipeline` skill orchestrates stages 1–2, 4–8 and 10 automatically. It stops at each 🔐 gate and waits for explicit human approval before continuing.

---

## 6. GTA VI Content Rules

> [!CAUTION]
> Violating these rules can damage channel credibility and trigger content strikes. They apply to every agent in this workspace and cannot be overridden by task briefs.

1. **No first-hand gameplay claims.** The studio does not own a PS5 or Xbox Series X|S. Never say "we played", "in our experience", or imply personal gameplay.
2. **Official sources only.** Every GTA VI factual claim must be backed by one of these:
   - `https://www.rockstargames.com/VI`
   - `https://support.rockstargames.com/VI`
   - `https://www.playstation.com/en-in/support/games/gta-vi-support/`
   - Official Xbox Support pages for GTA VI
3. **Label AI-generated content.** Every video or Short that includes AI-generated graphics, animation, voiceover, or narration must include in its YouTube description: *"Graphics created with AI assistance. All facts sourced from official documentation."*
4. **Never fabricate.** Do not invent gameplay mechanics, cheat codes, missions, in-game details, stats, or solutions that are not independently verified from the sources above.

See `config/gta6-sources.md` for the full source registry with confidence levels.

---

## 7. Verified GTA VI Facts

Quick-reference table of confirmed facts (as of November 2026). Do not use facts not listed here without running `gta6-researcher` first.

| Fact | Confirmed Value | Source |
|---|---|---|
| Launch date | 19 November 2026 | Rockstar Games official |
| Platforms at launch | PS5, Xbox Series X\|S only (no PC at launch) | Rockstar Games official |
| File size (download) | ~210 GB | PlayStation / Rockstar support |
| Storage space required | ~212 GB (includes OS buffer) | PlayStation support page |
| Preload start date | 10 November 2026 | Rockstar Games official |
| Standard Edition price | USD $79.99 | Rockstar / PlayStation Store |
| Ultimate Edition price | USD $99.99 | Rockstar / PlayStation Store |
| Setting | Leonida (fictional Florida) | Rockstar Games official |
| Protagonists | Lucia + Jason (dual protagonists) | Rockstar Games official trailer |

> [!WARNING]
> In-game mechanics, cheat codes, mission walkthroughs, and post-launch DLC details are **not** in this table because they were unverified at studio setup time. Run `gta6-researcher` before making any claim not listed above.

---

## 8. Tools Status

| Tool | Type | Status | Notes |
|---|---|---|---|
| FFmpeg 8.0.1 | Local binary | ✅ Verified | Full feature build; used by `video-editor` and `ai-video-generator` |
| Node.js 24.21.0 | Local runtime | ✅ Verified | Required for HyperFrames rendering |
| Python 3.14.4 | Local runtime | ✅ Verified | Scripts, automation, and data processing |
| HyperFrames | Skill + Framework | ✅ Configured | HTML/GSAP → MP4 video engine; working example in `gta-vi-event/` |
| Lemo-Opuscar | Plugin (Claude) | ⚠️ Pending | First-use library download still required before first run |
| Manim | Python framework | ⏳ Pending | `uv pip install manim` needed before use |
| Remotion | Node framework | ⏳ Pending | `npm install` needed before use |
| MotionClone | Desktop app | ❌ Incompatible | Windows-only; not available on this Linux system |
| ElevenLabs TTS | External API | 🔑 Needs key | Optional paid TTS API; never invoke without user confirmation |

---

## 9. Monetization Tracker

| Metric | Current Status | Threshold | Notes |
|---|---|---|---|
| Subscribers | ~11,000 | 1,000 ✅ | Well above minimum |
| Watch hours (last 12 months) | *Check YouTube Studio* | 4,000 hours | Path A to monetization |
| Shorts views (last 12 months) | *Check YouTube Studio* | 10,000,000 views | Path B to monetization |
| YouTube Partner Program | **Pending** | Either path above | Apply once threshold met |
| Content policy violations | None noted | Zero strikes | ✅ OK |
| AdSense account | Required at application | — | Set up before applying |

> [!TIP]
> Run `channel-analyst` with an exported YouTube Studio CSV to get a data-driven estimate of how many more Shorts are needed to hit the watch-hours or Shorts-views threshold.

---

## 10. Creating New Videos

Step-by-step process for the channel owner:

1. **Add idea** → `dashboard/ideas-queue.md` (Topic, Category, Evidence link, Priority)
2. **Research** → Tell the agent: *"Research [topic] for a GTA VI Short"* → runs `gta6-researcher` or `source-researcher` → outputs `research/<topic>/claims.md`
3. 🔐 **Human: Review claim ledger** — read `research/<topic>/claims.md`; approve or flag incorrect facts before proceeding
4. **Script** → Agent runs `tutorial-scriptwriter` or `shorts-scriptwriter` → outputs `scripts/<topic>/script.md`
5. **Storyboard** → Agent runs `video-director` → outputs `scripts/<topic>/storyboard.md`
6. **Rights check** → Agent runs `copyright-checker` → outputs `scripts/<topic>/rights.md`
7. **Render scenes** → Agent runs `ai-video-generator` → outputs `renders/<topic>/scene-N.mp4`
8. **Assemble** → Agent runs `video-editor` → outputs `renders/<topic>/final-draft.mp4`
9. 🔐 **Human: Quality review** — watch `final-draft.mp4`; agent runs `video-quality-reviewer` to flag issues; approve or request revision
10. **SEO metadata** → Agent runs `youtube-seo` → outputs `exports/<topic>/metadata.md`
11. 🔐 **Human: Final review & upload** — review title, description, tags, thumbnail; upload manually in YouTube Studio

---

## 11. Costs and API Keys

| Resource | Cost | Notes |
|---|---|---|
| FFmpeg | Free | Local, open-source |
| Node.js / Python | Free | Local runtimes |
| HyperFrames | Free | Local rendering via browser + FFmpeg |
| All 17 local skills | Free | No API calls required |
| ElevenLabs TTS | Paid (per character) | Optional; never invoke without user confirmation |
| YouTube Data API v3 | Free quota / paid overage | Optional analytics; needs Google Cloud project |
| Google Cloud TTS | Paid (per character) | Optional voice alternative to ElevenLabs |
| Lemo-Opuscar library | Free download, one-time | Library assets download at first run |

> [!IMPORTANT]
> Never invoke a paid API (ElevenLabs, Google Cloud TTS, etc.) without explicit user confirmation. All core production workflows run entirely on local free tools.

---

## 12. First Three Tutorial Outputs

| Tutorial | Research | Script | Storyboard | HyperFrames Project | Export Dir | Status |
|---|---|---|---|---|---|---|
| GTA VI Storage Requirements | `research/gta6-storage/` | `scripts/gta6-storage/` | ✅ Done | `gta6-storage-short/` | `exports/gta6-storage/` | Ready for render |
| GTA VI Preload on PS5 | `research/gta6-preload/` | `scripts/gta6-preload/` | ✅ Done | ⏳ Pending | `exports/gta6-preload/` | Script ready |
| Standard vs Ultimate Edition | `research/gta6-editions/` | `scripts/gta6-editions/` | ✅ Done | ⏳ Pending | `exports/gta6-editions/` | Script ready |

---

## 13. Skills Audit

Output of `find /home/varad/Videos/youtube/skills -name "SKILL.md" | sort | xargs -I{} sh -c 'echo "---" && head -3 {}'` run at studio setup:

```
---
---
name: ai-video-generator
description: Generate video assets using available local tools — HyperFrames HTML+GSAP, FFmpeg compositing, Python scripts.
---
---
name: channel-analyst
description: Interpret YouTube channel and Shorts performance from real exported or connected analytics and recommend focused experiments.
---
---
name: clip-rights-checker
description: Check whether proposed video, audio, image and gameplay assets can be used and document the evidence before publication.
---
---
name: copyright-checker
description: Verify all assets are cleared for YouTube use before export. Extends clip-rights-checker with GTA VI specific guidance.
---
---
name: gta6-researcher
description: Research GTA VI facts using only official Rockstar, PlayStation and Xbox sources.
---
---
name: indian-art-styles
description: Research and direct an animation influenced by a specific Indian art tradition with accurate attribution and respectful context.
---
---
name: production-pipeline
description: Orchestrate the full TOPIC→PUBLISHED VIDEO pipeline for GTA VI tutorials and gaming content.
---
---
name: shorts-scriptwriter
description: Write a concise, timed YouTube Shorts script from a verified premise and a defined audience.
---
---
name: source-researcher
description: Research and verify claims for gaming, AI and explainer videos with traceable primary sources.
---
---
name: trend-scout
description: Find timely, relevant YouTube Shorts ideas for a channel using current evidence and a practical production filter.
---
---
name: tutorial-scriptwriter
description: Write factual GTA VI tutorial scripts using verified claims only. Builds on shorts-scriptwriter for 30-60s vertical format.
---
---
name: video-director
description: Plan shot-by-shot visual execution for GTA VI tutorials and gaming content. Extends visual-director with gaming-specific patterns.
---
---
name: video-editor
description: Assemble final video from rendered scenes, audio, captions using FFmpeg. Applies quality-checked edits.
---
---
name: video-quality-reviewer
description: Review a rendered short video for technical playback, visual clarity, audio, factual consistency and rights readiness.
---
---
name: visual-director
description: Turn a short video script into a coherent shot and motion plan for footage, animation, or green screen.
---
---
name: youtube-seo
description: Generate YouTube-optimized title, description, tags, thumbnail concept and chapter markers for gaming content.
```

> [!NOTE]
> `lemo-opuscar` has a `SKILL.md` but is linked to the cached Claude plugin; it is not discovered by this `find` command because its SKILL.md path resolves differently. Total skills: **17** (16 local + 1 plugin-linked).

---

*Last updated: November 2026 — CreatorRadar studio setup. Run `channel-analyst` monthly and update §9 with fresh numbers.*
