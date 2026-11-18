---
name: codex-shorts-blueprint
description: Complete portable YouTube Shorts production skill for Codex and Paper Trail / Vox-style explainer Shorts. Enforces mobile UI safe zones, zero template chrome, Frame-0 hooks, seamless loops, 1.2–2.0s visual pacing, 12fps paper-collage craft, and a broadcast three-stem audio handoff.
---

# Viral Explainer YouTube Shorts Blueprint (Codex Master Skill)

User-supplied production specification, normalized from the message on
18 November 2026. Apply it when making a new editorial paper-collage Short:
1080×1920, 30 fps, target 28–45 seconds.

## 1. Script and virality architecture

- Frame-0 hook: speech starts at or before 0.05 s, with no intro or dead air.
  Use no more than 8–10 words in the first 2.5 s. Give second-person stakes or
  a counter-intuitive claim and open a curiosity loop.
- Tell a story with escalating stakes. Avoid classroom beat headings. Add a
  mini re-hook or twist every 10–12 s.
- Aim for 165–180 WPM and 85–135 words for a 30–45 s film. Use short speakable
  sentences. Verify factual statements in claims.md before scripting.
- Keep inter-beat gaps to 0.06–0.12 s. Allow one intentional 0.18–0.24 s pause
  immediately before the core twist.
- End with a grammatical and rhythmic bridge into the opening. Tail silence
  must be at most 0.10 s. Avoid a dead stop and generic subscribe requests.
  Include a relatable everyday reflection as an organic comment trigger.
- Retention and viral performance are production goals, not guaranteed results.

## 2. Clean full-bleed canvas and mandatory mobile safe zones

Never render template chrome: no mastheads, category kickers, divider lines,
beat-counter rectangles, source or illustrative-example footers, timers, or
progress bars. Source links and required AI disclosures go in metadata.md and
POST_CAPTION.txt rather than onto the frame.

For a 1080×1920 canvas:

- Top dead zone: y=0–195. Headlines start at y>=200.
- Right UI rail: x=915–1080. All critical text, numbers, badges, and callouts
  stay at x<=910.
- Bottom danger zone: y=1350–1920. No caption or key graphic extends below y=1350.
- Hero stage: x=60–900, y=220–1180.

## 3. Production implementation used for this film

These details implement the user's description; they are not additional text
claimed to have appeared in the supplied specification.

- Change composition, focal detail, or meaningful object state every 1.2–2.0 s.
  Plan that cadence from measured narration rather than equal long slides.
- Animate paper object poses at 12 fps inside the 30 fps delivery. Camera and
  paper-wipe transitions may run at 30 fps. Preserve rigid cutout geometry.
- Use actual transparent image-generated PNG layers, accurate typeset text,
  crisp shadows, and restrained paper texture. No SVG replacement assets.
- Generate word-timed captions. Check their actual bounding boxes against the
  safe zone in every displayed state, including punctuation and highlights.
- Deliver a captioned H.264/AAC master, a clean picture master, SRT, PNG cutouts,
  source project, claims.md, metadata.md, and an audio handoff: full-length,
  sample-aligned 48 kHz / 24-bit dialogue, music, and SFX WAV stems.
- Check the exported file, narration onset, tail, loop seam, pacing, caption
  geometry, full decode, loudness and peak headroom before calling it finished.
