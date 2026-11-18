---
name: visual-director
description: Turn a short video script into a high-retention 9:16 shot, camera, caption, and motion plan engineered for mobile YouTube Shorts.
---

# Visual director

Read the script, `claims.md`, and available assets. Align 9:16 editorial explainers with `skills/codex-shorts-blueprint/SKILL.md` (v2.0.0), `skills/codex-shorts-blueprint/presets/motion-presets.json`, and `skills/codex-shorts-blueprint/references/ae-workflow.md`. Pick one cohesive material system (paper stock, cut-edge treatment, lighting direction, shadow character, 2–3 base colors + 1 emphasis color, 1 display face + 1 readable text family) and reuse it across beats.

## 1. Explanatory Scenes & Mandatory Visual Proof (Not a Sequence of Posters)
- Before artwork, confirm the one-sentence **hidden mechanism** and one-sentence **visual proof** (the change and its cause must read clearly even with sound muted).
- Plan a small number of **coherent story worlds** (multiple meaningful events inside a continuous shot instead of a new title card every 1.6s) moving across **at least four presentation families** (e.g., world-wide view, macro detail, cross-section/mechanism, evidence close-up, comparison, consequence, payoff).
- **Mandatory Visual Proof Sequence:** Include at least one mechanism proof: `occlusion_reveal` / `cross_section` behind a surface, turning an object/map to expose a relationship, `matched_comparison` on a shared scale/baseline, causal follow-through, or locating an exact source detail connected to the claim. Arrows and big words alone are not proof.
  - *Reference shot-logic patterns (`skills/codex-shorts-blueprint/references/research.pdf`):* (a) **Object carry → perspective shift → cross-section** (carry one map/object across views with attached labels down into an interior proof); (b) **Evidence texture + scale shifts** (hold a consistent geographic/material anchor while pushing from overview to archival inset to macro detail); (c) **Close-up → setup → stakes → mechanism → payoff** (use persistent props and visible physical contact, adaptable to 2.5D paper without full 3D character animation). Do not blindly copy reference subscribe CTAs, lower caption positions, or >45s runtimes.
- **No Layout Fatigue:** Avoid more than **two consecutive events** using the same centered headline + floating-object layout. Frame 0 and the final loop anchor may deliberately match.
- **Per-Event Spec (Every 1.2–2.0s):** Specify (1) what new information the viewer learns, (2) persistent visual anchor, (3) what moves vs. stays fixed, (4) triggering narration word/phrase, (5) camera intention, matte/occlusion action, and focal hierarchy, and (6) supporting `claims.md` ID. Decorative jitter is not a visual event.

## 2. Clean Full-Bleed Canvas & Strict Mobile Safe Zones (`1080×1920`)
- **Zero template/HUD chrome:** Never render top masthead bars, `CATEGORY // SUBTITLE` kickers, horizontal divider lines, `01 / 09` beat-counter rectangles, bottom `SOURCE:` / `ILLUSTRATIVE EXAMPLE` bars, on-screen timers, or progress bars. Put source URLs and AI disclosures in `metadata.md` / `POST_CAPTION.txt`. (Story-relevant illustrated app metrics are allowed if marked illustrative in metadata.)
- **Safe Rect (`x = 60–910`, `y = 200–1350`):** Keep all critical text, figures, badges, and callouts inside this box. Keep headline top bounds `y >= 200`, the right UI rail `x = 915–1080` clear, and captions/key graphics strictly above `y = 1350`. Only background atmosphere may extend into UI regions.
- **Hero Stage (`x = 60–900`, `y = 220–1180`):** Stage foreground, subject, and oversized background planes cleanly inside the hero band with generous overscan for camera moves.
- **Caption Band (`x = 70–900`, `y = 1160–1340`):** Anchor 2D screen-space captions strictly above `y = 1350` so YouTube's bottom channel/title/scrubber overlay never obscures them.

## 3. Art Direction & PNG Asset Hygiene
- For editorial paper-collage Shorts, use **actual transparent raster PNG cutouts** (no SVG replacement asset packs) — one object per PNG, separating parts that move or occlude independently (front/back surfaces, phone/screen, foreground/midground/background, chart/labels).
- Size hero assets for the largest intended crop including zoom/overscan (**2000–4000 px** long edge for hero zooms beyond 150%).
- Inspect alpha edges on both light and dark backgrounds (reject soft rectangular haze, halos, clipped edges, baked labels, or distorted logos). Keep contact shadows separate when elevation changes.
- Use exact geometry or clean source imagery for evidence, maps, numbers, and UI — never pass AI-generated charts/maps/QR codes as measured evidence. Keep paper grain restrained and fixed (avoid temporal noise or continuous wobble on settled objects).

## 4. After Effects-Style 2.5D Motion, Three Clocks & Motion Presets
- **Three Independent Clocks (Mandatory):**
  - Intrinsic paper cutout poses: **`12 fps`**
  - Camera, mattes, world placement: **`30 fps`**
  - Typography & 2D screen-space captions: **`30 fps`**
  - Never apply `Posterize Time` to the entire final composition.
- **Authored Velocity & 10 Motion Recipes:** Start from the parameterized recipes in `skills/codex-shorts-blueprint/presets/motion-presets.json` (`evidence_push`, `object_carry`, `occlusion_reveal`, `cross_section`, `attached_callout`, `kinetic_emphasis`, `material_settle`, `focus_handoff`, `matched_comparison`, `motivated_whip`). Define anticipation, travel, deceleration, and a readable hold using Speed Graph / temporal Bezier curves (not default Easy Ease or a perpetual slow zoom everywhere). Limit `motivated_whip` to genuine story turns (max 1 per 10s).
- **Physically Tied Motion Blur:** Use native transform blur or temporal shutter sampling (`180°` shutter angle, `-90°` phase starting point) on fast world/camera motion — never a full-frame Gaussian blur; keep captions and critical reading text sharp.
- **Visual Loop Bridge:** Match the final visual anchor coordinates, scale, and color energy to Frame 0 for a clean two-cycle loop.
- **Honest Backend Naming:** Describe the look as "After Effects-style" when rendered in a local compositor; do not claim native AE project files or renders unless actually authored and checked in After Effects.

## 5. Typography & Frameless Kinetic Captions
- Do not put a large headline on every beat—let diagrams and actions carry the story; attach concise labels directly to their evidence points (project 3D anchors into 2D screen space).
- **Caption Styling:** Frameless high-contrast display sans starting around **`64–72 px`** (`line_height ~76 px`), typically **3–5 words** and **at most 2 lines**, broken on spoken meaning. Keep baselines stable, highlight only the active word/phrase in one emphasis color, and avoid constant per-word scale pumping or bounces.
- Type exact labels in the compositor (never rely on image generation for readable text/numbers) and validate **full swept bounds** (glyphs, shadows, camera motion, overshoot) against `x = 60–910, y = 200–1350`.

## Output & Structural Validation
Mark required assets and missing rights clearance. Emit a production-ready shot list, initial review frame list, and (for editorial Shorts) `premium_plan.json` validated with:
```bash
python3 skills/codex-shorts-blueprint/scripts/validate_plan.py <path/to/premium_plan.json>
```
Remember: structural plan validation does not replace full-resolution visual and normal-speed motion review.
