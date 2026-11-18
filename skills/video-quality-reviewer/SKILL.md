---
name: video-quality-reviewer
description: Audit a rendered YouTube Short or video for technical integrity, Shorts UI safe zones, viral retention craft, broadcast audio quality, factual accuracy, and rights clearance.
---

# Video quality reviewer

Inspect the actual rendered video with `ffprobe`, full decode check (`ffmpeg -v error -i <mp4> -f null -`), full-resolution sampled beat frames (`contact_sheet.jpg`), normal-speed playback review, Whisper ASR verification, and **direct audio listening** on `narration_master.wav`. A successful encode or passing `validate_plan.py` run alone is never sufficient visual or audio approval.

## Mandatory Pre-Publish QA Gates

### 1. Technical & Playback Integrity
- Exact resolution (`1080×1920` for Shorts), framerate (`30 fps`), H.264 (`BT.709` limited range, `yuv420p`, CRF 16–18) + `48 kHz` stereo `256k` AAC, `-movflags +faststart`.
- Zero black/frozen frames, zero decode errors (`DECODE_OK`), zero edge gaps, aliasing, missing font glyphs, or overlapping text/graphics on any beat.
- **PNG Alpha & Material Audit:** Inspect native-resolution PNG cutouts on light and dark backgrounds—flag rectangular haze, fuzzy halos, clipped edges, baked labels, or distorted logos as BLOCKER.

### 2. YouTube Shorts UI Safe-Zone Gate (BLOCKER if violated)
Inspect **full swept bounds** (including camera motion, overshoot, motion blur, drop shadows, and punctuation) against real mobile Shorts UI overlays (`1080×1920`):
- **Top Dead Zone (`y < 200px`):** No headline or critical label clipped by top status/search icons.
- **Right Rail (`x = 915–1080px`):** No key stat, stamp, callout, or caption buried under Like/Comment/Share buttons (`x <= 910px`).
- **Bottom Danger Zone (`y > 1350px`):** **BLOCKER** if captions or key graphics extend below `y = 1350px` (keep hero artwork in `x = 60–900, y = 220–1180` and captions in `x = 70–900, y = 1160–1340`). Only background atmosphere may extend into UI regions.
- **Zero Chrome (Rule 8):** **BLOCKER** if any masthead bar, `CATEGORY // SUBTITLE` kicker, top divider line, `01 / 09` counter box, bottom source/illustrative-example bar, timer, or progress bar appears on screen. (Story-relevant illustrated app metrics are permitted if explicitly marked illustrative in `metadata.md`.)

### 3. Visual Proof, Scene Craft & Timing Audit (v2 Standard)
- **Plan Structural Check:** If `premium_plan.json` is present, verify `python3 skills/codex-shorts-blueprint/scripts/validate_plan.py <plan.json>` passes (remembering structural pass != visual approval).
- **Frame-0 Hook:** Audio begins `<= 0.05s`; Frame 0 is already a composed story image in motion; opening hook (`<= 8–10` words in first 2.5s) opens a curiosity loop with personal/relatable stakes.
- **Visual Proof & Story Worlds:** Verify at least one genuine mechanism/proof sequence (occlusion reveal, cross-section, matched comparison, or causal chain) that communicates what changed and why **even with sound muted**. Flag >2 consecutive centered headline + floating-object slides or repeated title-card slideshows.
- **Meaningful Visual Cadence:** Verify a meaningful information change + persistent visual anchor every **1.2–2.0 seconds** (decorative jitter is not an event), with re-hooks every **10–12 seconds** (final stretch `<= 12s`).
- **Three-Clock Separation & Motion Blur:** For paper-collage Shorts, verify intrinsic paper poses run at **`12 fps`** while camera, mattes, world placement, typography, and captions run at **`30 fps`** (flag whole-comp Posterize Time as BLOCKER). Verify physically tied transform/shutter motion blur on fast moves while keeping captions and critical reading type crisp.
- **Kinetic Captions:** Frameless high-contrast **3–5 word chunks** (`64–72px`, max 2 lines, broken on spoken meaning), stable baseline, single emphasis color—flag wide dark subtitle boxes, constant per-word scale pumping/bounce, or unreadable type.
- **Zero Dead Air & Two-Cycle Loop:** Inter-beat gaps `0.06–0.12s` (at most one `0.18–0.24s` twist pause); closing tail `<= 0.10s`; inspect a **two-cycle playback loop** to confirm both spoken grammatical bridge and registered Frame-0 visual anchor continuity.

### 4. Broadcast Audio, Stems & Pronunciation Audit
- **Whisper ASR Check:** Verify `>= 0.98` word accuracy against script on every beat (flag any slurred numbers, dropped consonants, or mispronounced terms as BLOCKER).
- **Direct Listening Audit:** Listen directly to `narration_master.wav` to verify natural studio vocal tone (no double-EQ harshness, no metallic denoise/echo artifacts). Never describe automated signal analysis as a listening pass; record any review limitation honestly in the handoff.
- **SFX & Mix Balance:** Verify material-specific, tightly trimmed SFX cues tied to real actions (no generic cut whooshes, zero distorted hits or noisy tails), balanced `12–16 dB` mean below voice with smooth music sidechain ducking (no audible pumping) and a purposeful music lift/subtraction at the twist.
- **Loudness & 3-Stem Handoff:** Verify `-14.0 ± 0.5 LUFS` studio target (or `-16 LUFS` social target) and `<= -1.0 dBTP` true peak, plus full-length, sample-aligned **48 kHz / 24-bit** `dialogue`, `music`, and `sfx` WAV stems reconstructing the PCM mix within quantization error.

### 5. Factual, Provenance & Rights Compliance
- Compare every spoken and on-screen number, unit, and claim against `research/<topic>/claims.md` (flag any AI-generated chart/map/QR passed as measured evidence as BLOCKER).
- Confirm honest backend naming ("After Effects-style" unless actually authored/rendered in native After Effects), clean master + SRT + editable source + font/license provenance, clearance in `assets/clearance-log.md`, mandatory disclosure in `metadata.md` / `POST_CAPTION.txt`, and Rule 4 human approval gate (`human_approved: false` until explicit sign-off).

Report defects by timestamp, severity (`BLOCKER` / `WARNING`), evidence, and exact fix. Reinspect affected moments after edits. Give a publish-ready verdict only when all blockers are resolved.
