---
name: video-editor
description: Assemble final video from rendered scenes, broadcast audio, curated SFX, and kinetic captions using FFmpeg.
---

# Video Editor & Broadcast Audio Standards

## Purpose
Assemble rendered scenes, engineer studio-grade 3-stem broadcast audio (Voice + Curated SFX + Dynamic Music Bed), burn safe-zone kinetic captions, and export a QC-verified YouTube-ready MP4.

## 1. Broadcast Audio Architecture (Mandatory — 3 Stems)

### A. Single-Pass Studio Vocal Chain
- **NEVER double-process vocals** (never stack EQ/compression/loudnorm twice across two scripts, and avoid heavy `afftdn` or `aecho` filters that create metallic artifacts).
- Process directly from raw cloned creator takes (`beat_XX_raw.wav`) **once**:
  - `highpass=f=78` (clean sub-rumble)
  - Warm chest `+1.8 dB @ 135 Hz`, de-mud `-2.2 dB @ 310 Hz`, clarity `+2.2 dB @ 3.4 kHz`, silky air `+1.2 dB @ 10 kHz`
  - Gentle `deesser=i=0.22`, smooth single-stage broadcast compressor (`threshold=-19dB:ratio=2.8:attack=14:release=115`)
  - Natural energetic pace (`atempo=1.02`–`1.04`, never chipmunk)
  - Safe silence trim (`start_threshold=-54dB` so soft `S`/`Sh`/`T` consonants are never clipped)
- **Whisper Pronunciation Gate:** Generate multi-take candidates for tricky beats and verify **>= 0.98 word accuracy** with Whisper before mastering.
- **Zero Dead Air Pacing:** Start first syllable `<= 0.05s`, keep inter-beat pauses tight (`0.06–0.12s`, reserving `0.18–0.24s` ONLY for a dramatic twist pause), and keep seamless loop tail `<= 0.10s`.

### B. Material-Specific, Auditioned Stereo SFX Bus
- **Place SFX on actual material actions** (paper movement, keypress, impact, stamp) rather than whooshing every cut.
- **Audition every SFX asset** before mixing—discard distorted sub-hits, harsh screeches, rattling crashes, or noisy wind tails.
- Trim every SFX tightly (`0.05s–0.75s` with clean fade-outs) so zero muddy tails bleed over spoken words.
- Pan cues subtly in stereo (`-0.35` to `+0.35`) synced to exact visual motion events.
- Gain-stage SFX cleanly (`-9 to -12 dB` peak, `-30 to -34 dB` mean — roughly **12–16 dB below voice**) and apply gentle voice-keyed sidechain ducking (`ratio=1.6–1.8`) on the SFX bus so speech always stays 100% intelligible.

### C. Dynamic Music Bed, Mastering & 3-Stem Handoff
- Loop shorter beds seamlessly with `acrossfade=d=1.6` (wrap music tails for seamless Shorts loops; never fade to dead silence).
- Carve a vocal pocket (`equalizer=f=1800:width_type=o:width=1.8:g=-4.5`), widen lightly (`extrastereo=m=1.15`), and apply smooth voice-keyed sidechain ducking (`threshold=0.04:ratio=2.8:attack=22:release=320`) without audible pumping.
- **Dynamic Music Arc:** Avoid a flat constant-energy loop—use a purposeful lift or `0.3–0.5s` subtraction right before the core twist/reveal so the payoff lands cleanly.
- **Two-Pass EBU R128 Master:** Target **`-14.0 ± 0.5 LUFS`** studio loudness (or **`-16 LUFS`** social starting target per `codex-shorts-blueprint` v2) and **`<= -1.0 dBTP`** true peak (`linear=true`), then listen directly for intelligibility and fatigue. Do not equate automated signal measurements with a listening pass.
- **Mandatory 3-Stem Handoff (`codex-shorts-blueprint` v2):** Export full-length, sample-aligned **48 kHz / 24-bit WAV** stems (`dialogue`, `music`, `sfx`) at sample zero and master gain so a unity sum reconstructs the PCM mix within quantization error, alongside the PCM mix, clean picture master, SRT, PNG cutouts, and editable source.

## 2. FFmpeg Operations & High-Quality Export
```bash
# Final YouTube-ready mux (1080x1920, 30fps, H.264 BT.709 limited yuv420p CRF 16-18 + 48kHz stereo 256k AAC)
ffmpeg -y -i visual_raw.mp4 -i narration_master.wav \
  -map 0:v:0 -map 1:a:0 \
  -c:v libx264 -crf 17 -pix_fmt yuv420p \
  -colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv \
  -c:a aac -b:a 256k -ar 48000 -ac 2 \
  -movflags +faststart -shortest output.mp4
```
*(Use `-c:v copy` only when `visual_raw.mp4` is already encoded to H.264, `1080×1920`, `30 fps`, BT.709 limited range, `yuv420p`, CRF 16–18.)*

## 3. Shorts Safe-Zone Caption Spec (`1080×1920`)
- **Position:** Anchor 2D screen-space captions cleanly inside **`x = 70–900`, `y = 1160–1340`** (strictly inside safe rect `x = 60–910, y = 200–1350`, above the bottom YouTube Shorts UI overlay and clear of the `x = 915–1080` right rail).
- **Style:** Frameless crisp display sans starting around **`64–72 px`**, **3–5 words** per chunk (**max 2 lines**), broken on spoken meaning. Keep baselines stable, highlight only the active word/phrase in one emphasis color (no per-word scale pumping or bounces), and keep captions sharp (never blurred by camera motion blur).
- **Swept Bounds:** Validate actual rendered glyph, shadow, and animation bounds inside `x = 60–910, y = 200–1350`.

## 4. QC Checklist (Mandatory Before Export)
- [ ] `ffmpeg -v error -i output.mp4 -f null -` passes with zero errors (`DECODE_OK`)
- [ ] Video stream verified: H.264, `1080×1920`, `30 fps`, BT.709 limited range, `yuv420p`, `-movflags +faststart`
- [ ] Integrated loudness `-14.0 ± 0.5 LUFS` (or `-16 LUFS` social target), true peak `<= -1.0 dBTP`, `48000 Hz` stereo `256k` AAC
- [ ] Full-length, sample-aligned 48 kHz / 24-bit `dialogue`, `music`, and `sfx` WAV stems verified to reconstruct PCM mix at unity
- [ ] Swept caption and hero graphics verified inside Shorts UI safe zone (`x = 60–910, y = 200–1350`; hero `x = 60–900, y = 220–1180`)
- [ ] Direct ear audition of `narration_master.wav` confirms zero slurs, metallic artifacts, or SFX clashes (note any listening limitation honestly)
- [ ] Zero dead air at start (`<= 0.05s`), loop-ready tail (`<= 0.10s`), and clean **two-cycle visual/audio loop** verified
- [ ] Clean picture master, SRT, PNG cutouts, editable source, `claims.md`, and `metadata.md` packaged in handoff

## Session Log
Append every run to `editing/session-log.md`:
```
Date | Input files | Output | Duration | Notes
```

## Output
`renders/<topic>/final.mp4` → `exports/<topic>/YYYYMMDD-<slug>.mp4`
