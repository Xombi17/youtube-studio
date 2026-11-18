---
name: codex-shorts-blueprint
description: Produce premium 9:16 editorial paper-collage explainers with Frame-0 hooks, strict Shorts safe zones, visual proof, coherent 2.5D scenes, authored camera and typography motion, 12fps paper craft inside 30fps delivery, seamless loops, and a three-stem audio handoff. Includes a million-view reference study and After Effects implementation recipes.
metadata:
  version: "2.0.0"
  updated: "2026-11-18"
---

# Premium Shorts Blueprint v2

Use for a new 1080×1920, 30 fps, 28–45 s explainer in editorial paper-collage
style. Preserve the user's constraints below. The premium motion recipes are
production defaults to tune to the story, not a formula that guarantees views.

Read `references/research.md` for the evidence and `references/ae-workflow.md`
for implementation. Use `presets/motion-presets.json` when authoring a scene.
An example plan and a structural validator are in `examples/` and `scripts/`.

## 1. User requirements that remain binding

- Speech starts at <=0.05 s. Frame 0 is already a composed story image.
- At most 8–10 spoken words in the first 2.5 s. Open a curiosity loop with
  second-person stakes or a specific counter-intuitive claim. No greeting,
  branding intro or explanation of the entire answer in Beat 1.
- Target 165–180 WPM, normally 85–135 words. Use short speakable sentences.
  Verify factual claims in `claims.md` before finalizing the script.
- Add a mini re-hook or twist every 10–12 s. Keep inter-beat speech gaps at
  0.06–0.12 s; permit one 0.18–0.24 s pause immediately before the core twist.
- Add a meaningful visual event every 1.2–2.0 s. An event must advance the
  explanation: a revealing crop, state change, comparison, demonstration,
  evidence highlight, consequence or new shot. Decorative jitter is not an event.
- End with a grammatical and rhythmic bridge into the opening, <=0.10 s tail
  silence, and matching visual anchors. Include a relatable reflection without
  a generic subscribe/engagement request.
- Render paper-object craft at 12 fps within the 30 fps master. Camera,
  masks, typography and caption updates run at 30 fps where needed.
- Use actual high-quality raster PNG cutouts; no SVG replacement asset packs.
- Deliver full-length, sample-aligned 48 kHz / 24-bit dialogue, music and SFX
  WAV stems alongside the finished video and editable source.

### Safe zones and zero template chrome

All critical text, figures, badges and callouts stay in x=60–910, y=200–1350.
Hero artwork stays in x=60–900, y=220–1180. Keep headline top bounds at y>=200, the
right UI rail x=915–1080 clear, and captions/key graphics above y=1350.
Only background atmosphere may extend into the UI areas.

Do not burn mastheads, category kickers, top divider lines, beat counters,
source/illustrative-example footers, timers or progress bars into the film.
Put source URLs and relevant AI-production disclosure in `metadata.md` and
`POST_CAPTION.txt`. A story-relevant illustrated app metric is not template
chrome, but it must be marked as illustrative in the metadata if invented.

## 2. Research honestly before borrowing a technique

For a new subject, choose 3–5 relevant references, including a close visual
match and an adjacent example useful for mechanism or storytelling. Verify
their identities and public video-level view totals; record the retrieval date.
Distinguish exact player totals from rounded channel-card counts.

Record what was actually reviewed: timed player frames, continuous playback,
automatic captions, description only, or audio listening. Do not label a
thumbnail or transcript as a visual review. Do not infer exact easing,
production software, cut rate or sound design from a few stills. Automatic
captions can overlap, mistranscribe, or omit the opening; do not calculate
precise WPM from them without alignment and deduplication.

Public views do not expose retention, engaged views, swipe rate or revenue.
YouTube counts Shorts starts/replays without a minimum watch time under the
post-March-2025 definition. Treat the reference study as a source of editing
hypotheses, not evidence that an effect caused a million views. Keep factual
topic research independent of a viral video's claims.

## 3. Build an explanatory scene, not a sequence of posters

Before artwork, write one sentence stating the hidden mechanism and one
sentence describing the visual proof of it. If the voice is muted, the viewer
should still see what changed and why.

Distinguish sourced evidence from an illustrative model. Stage metaphors as
models and retain the conditional language of the claim; a convincing animation
is not new evidence about a real person, intention or measured outcome.

Plan a small number of coherent story worlds. Each can contain several visual
events within a continuous shot. Do not force a new title card every 1.6 s.
Move through at least four useful presentation families across the film, for
example: world-wide view, macro detail, cross-section/mechanism, evidence
close-up, comparison, consequence, payoff. A continuous world can supply these
families through camera and object changes.

For each event specify:

1. What new information the viewer learns.
2. Which object remains the visual anchor.
3. What moves and what stays fixed.
4. The narration word/phrase that triggers the change.
5. Camera intention, occlusion/matte action and focal hierarchy.
6. Which source claim the image supports.

Avoid more than two consecutive events using the same centered headline plus
floating-object layout. Frame 0 and the final loop anchor may deliberately
match. An object may return when its role changes; repeating it as decoration
does not count as a new visual event.

### A visual proof sequence is mandatory

Choose at least one: reveal the hidden mechanism behind a surface; turn an
object/map to expose a relationship; compare like with like on the same scale;
follow an action through cause, mechanism and consequence; or locate an exact
source detail and connect it to the claim. Arrows and large words alone are
not a mechanism demonstration.

For the rage-bait example, show the same post producing a correction, the
correction producing a reply, and the thread revealing an attention incentive.
A phone, angry face and marionette hand floating in successive frames is not
sufficient proof. The objects need causal, visible connections.

## 4. Art direction and asset preparation

- Define one material system per film: paper stock, cut-edge treatment,
  photographic/illustration treatment, lighting direction and shadow character.
- Use 2–3 base colors and one emphasis color. Use one display face plus one
  readable text family. Alternate composition and scale, not arbitrary styling.
- Generate one object per transparent PNG. Separate parts that must move or
  occlude independently: front/back surfaces, book/hinge, phone/screen, hand/
  strings, foreground/midground/background, chart/labels.
- Size assets for the largest intended crop, including zoom and overscan.
  For a hero zoomed beyond 150%, prefer a 2000–4000 px source long edge.
- Inspect alpha on light and dark backgrounds. Reject rectangular haze,
  clipped edges, fuzzy halos, adjacent props, baked labels or distorted logos.
  Keep contact shadows separate when they must react to elevation or motion.
- Use clean source imagery or exact geometry for evidence, maps, numbers and
  UI. Do not treat an AI-generated chart/map/QR pattern as measured evidence.
- Add restrained, fixed paper grain and material-specific imperfections. Avoid
  temporal noise, identical sawtooth tears on every card, or continuous wobble
  on every object. Settled objects should feel placed in a world.

## 5. After Effects-style motion architecture

Use three independent timing systems:

| System | Rate | Purpose |
|---|---:|---|
| Intrinsic paper poses | 12 fps | Cutout movement and handmade pose changes |
| Camera, mattes, world placement | 30 fps | Fluid framing, reveals and transitions |
| Typography and captions | 30 fps | Crisp, precisely timed reading |

In After Effects, use 12 fps actor precomps within a 30 fps main comp; preserve
the actor timing. Keep the camera/world wrappers and 2D type/HUD at 30 fps.
Do not apply Posterize Time to the entire final composition.

Build separate foreground, subject and background planes with enough overscan.
Use one camera intention per shot. Camera moves must reveal, compare, follow,
or establish a relationship; a perpetual slow zoom is not a substitute.

### Author velocity, do not use one easing everywhere

Choose anticipation, travel, deceleration and a readable hold. Start from the
curves in `motion-presets.json`; tune by viewing the movement at normal speed.
Use the Speed Graph/temporal influence in After Effects, or a proper temporal
Bezier implementation in another compositor. Distinguish time interpolation
from the spatial path.

Default to decisive movement with a quiet landing. Use small overshoot only
for a material event such as a paper slap; do not bounce every label/camera.
Replace random drift with motivated movement and a stable resting pose.

### Use these techniques for a reason

- **Evidence push:** a restrained camera move toward the detail being explained.
- **Object-carry match cut:** register the same object's screen anchor across
  the cut; change its context while preserving viewer orientation.
- **Occlusion reveal:** a foreground surface or matte exposes the hidden cause.
- **Cross-section:** remove or open a surface to explain an interior relationship.
- **Attached callout:** a line/label follows its actual evidence point.
- **Comparison:** keep scale, baseline, units and camera treatment comparable.
- **Kinetic emphasis:** one important word changes at the exact narrated moment.
- **Depth/focus shift:** separate the subject from its environment with parallax
  and restrained focus, preserving the readability of all critical type.

Reserve whip/punch transitions for a real turn in the story. Prefer spatial
continuity over a different transition on every cut. Transitions are not the
story's main visual events.

### Motion blur must be physically tied to movement

Use native transform motion blur or temporal shutter sampling, not a Gaussian
blur over the finished frame. A useful starting point is 180° shutter angle
and -90° phase; tune to speed and the paper aesthetic. Keep captions and
critical reading text crisp. Check moving edges and matte reveals at full
resolution. For a local compositor, sample camera/world transforms across
the shutter interval while respecting held 12 fps actor poses.

## 6. Typography, captions and mobile reading

- Do not add a large headline to every event. Let a diagram or action carry
  the explanation when it can. Labels identify evidence rather than narrating
  the entire voice-over twice.
- Use a clear hierarchy: one focal visual, one primary reading task, and
  supporting labels only when needed. Attach labels to their objects.
- Start captions around 64–72 px at 1080-wide delivery, typically 3–5 words,
  at most two lines. Break on spoken meaning rather than an arbitrary word count.
- Highlight only the active word/meaningful phrase. Avoid constant scale
  pulsing, large per-word bounces or entire sentences competing with a headline.
- Keep caption baselines stable and bound all glyphs, panels, shadows and
  animation overshoot to the safe zone. Check actual rendered font metrics.
- Type exact labels in the compositor; do not ask image generation to draw
  readable captions or accurate numbers. Check missing glyphs at native size.

## 7. Sound and loop finish

The sound-design guidance here is an editorial recommendation; the reference
study did not audit the source videos' audio.

Make narration natural and consistent. Place paper/impact/keyboard cues on
actual material actions; do not whoosh every cut. Use a restrained score with
a purposeful lift or subtraction at the twist. Duck it under speech without
audible pumping. As a social-delivery starting target, use about -16 LUFS
integrated and <=-1 dBTP, then listen for intelligibility and fatigue.

Record the ending bridge and following opening in one take when possible;
remove the repeated opening at its word boundary. Match the last visual
anchor to frame 0. Wrap music tails and avoid a fade to silence or generic CTA.

Export the three stems at equal length, sample zero and master gain so a
unity sum reconstructs the PCM mix within quantization error. Measure onset,
tail, loudness and peaks, but do not describe signal analysis as a listening
pass. Record any review limitation accurately in the handoff.

## 8. Production order and quality gates

1. Verify claims and reference evidence; write the mechanism and visual proof.
2. Write and synthesize/record the script; measure real timing and loop bridge.
3. Author `premium_plan.json`: scenes, meaningful events, anchor continuity,
   camera/matte recipes, claim IDs, 12/30 fps separation and text safe boxes.
4. Validate the plan with `scripts/validate_plan.py`. Structural success is not
   visual approval: still review composition, clarity and motion.
5. Prepare a consistent PNG asset set and build the scene graph. If the chosen
   renderer lacks parallax, occlusion or temporal motion blur, extend it before
   calling the output premium. A repeated slideshow is not a finished substitute.
6. Render the opening and the proof sequence internally. Inspect full-size
   frames and normal-speed movement; fix the art/motion before the full export.
7. Render, mix and inspect the final files. User-delegated creative choices
   can be resolved autonomously; these are internal quality gates, not new
   approval prompts.

### Final checks

- Frame-0 image and speech; actual voice onset <=0.05 s and tail <=0.10 s.
- Narration WPM, re-hook times, gap limits and meaningful visual-event cadence.
- Full swept text/hero bounds, including camera motion, overshoot and blur.
- Captions at 30 fps, paper craft at 12 fps, camera/matte motion at 30 fps.
- No template chrome; accurate numbers, units, sources and disclosure metadata.
- Review every shot, the core mechanism, all transitions, and a two-cycle loop.
- No clipped PNGs/halos, missing font glyphs, edge gaps, aliasing or unreadable type.
- Full video/audio decode; H.264/AAC, 1080×1920, 30 fps, BT.709 limited range,
  yuv420p, fast-start MP4. Use a suitable high-quality encode such as CRF 16–18.
- Clean master, SRT, PNG layers, editable source, fonts/licenses/provenance,
  claims/metadata, three 48 kHz / 24-bit stems, PCM mix and measured QA record.

Use “After Effects-style” to describe the visual approach when another
compositor renders it. Do not claim an After Effects project, native AE render,
or executed JSX unless it was actually produced and checked in that software.
