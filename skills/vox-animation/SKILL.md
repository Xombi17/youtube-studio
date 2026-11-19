---
name: vox-animation
description: Build a Vox-style cut-paper explainer video with no camera — one continuous generated world, type set inside the frame, and the animation timed off a real voiceover. Use when someone wants a faceless explainer reel or short that looks made rather than generated.
---

# Vox Animation

A 29 second explainer with no camera, no editor and no stock footage. One continuous paper world,
a character that accumulates through it, and an animation whose timing comes from the voice track
rather than a guess.

Built and shipped 29/08/2026. The reel it came from ran 29.1 seconds across ten beats.

---

## What you actually need

Four things, and only one of them costs money.

| Step | Tool | Cost | Swappable? |
|---|---|---|---|
| Generate the scenes | **Higgsfield** (`seedance_2_5`) | paid credits, ~45 per 1080p scene | **Yes.** Any image-to-video model that accepts a start frame works. The prompt is the asset, not the vendor |
| Voice | **Fish Audio** | **free** on `s2.1-pro-free` | Yes, but you need per-line audio files and their real durations |
| Turn the HTML into video | **Puppeteer** (this build) or **HyperFrames** | free / your plan | Yes. Anything that screenshots a page frame by frame |
| Conform and mux | **ffmpeg** | free | No |

**Higgsfield and HyperFrames are third-party products.** Higgsfield generates the scenes,
HyperFrames renders HTML to video. Neither is required by name — this build frame-stepped with
Puppeteer directly, because the composition drives a paused GSAP timeline through `window.seek(ms)`
and that needs nothing but a browser.

### Install

```bash
npm i puppeteer                      # frame-steps the composition
npm i -g ffmpeg-static               # conform, mux, extract the anchor frame
npx hyperframes                      # optional, if you would rather not hand-roll the stepper
```

Higgsfield and Fish Audio are accounts, not installs. Fish Audio needs an API key from
`fish.audio/app/developers`; the free model needs no credit.

⚠ **API credit and platform credit are separate wallets on Fish Audio.** A Plus subscription does
not pay for the API. Paid models return `402` until you top up. `s2.1-pro-free` is their newest
model, costs nothing, and is good enough for a finished reel.

---

## The method, in six steps

### 1. Record the voice FIRST

Everyone builds to a guessed timeline and squeezes the voiceover on afterwards. Do it the other way
round and the picture can never drift.

Write the script as a config, one entry per line:

```json
{ "id": "eyes",
  "say": "Puppeteer and Playwright give it eyes. It sees any live page.",
  "scene": "g1" }
```

`scripts/fish-tts script.json` generates one MP3 per line, measures each with ffprobe, and writes a
timing map:

```json
{ "id": "eyes",  "start_ms": 5965,  "dur_ms": 4232 }
```

The composition reads that file. Change a word and only that line re-records — everything
downstream moves on its own.

**Speed is real and reliable.** `prosody.speed` at 1.3 keeps the pacing fast.
⚠ **Emotion tags are not.** Measured four ways: the whisper came out 3.4 dB quieter and the shout
measured *zero* difference from the untagged control. Do not build a claim on them.

### 2. Generate scene one — the only one made from scratch

```
Editorial cut-paper motion graphics, vertical.
Deep navy textured paper background with visible paper grain.
Every object is flat cut paper with soft drop shadows, as if card is laid on card.
Palette strictly navy, cream off-white, terracotta orange and pale sky blue.
Camera holds completely still, no zoom, no pan, no push.
Deliberate stepped motion.
SCENE: [what happens in this beat]
Absolutely no text, no words, no letters, no numbers anywhere in frame.
```

**That last line is not optional.** Image models cannot spell, and a garbled word is worse than no
word. Every letter goes on afterwards, in code.

### 3. Extract the anchor frame

```bash
ffmpeg -sseof -0.2 -i scene1.mp4 -frames:v 1 -q:v 2 anchor.png
```

Upload it once. Every other scene starts from this exact image.

### 4. Generate every other scene from that ONE frame

```
Continue from the supplied frame: exact same [character], exact same [background], same lighting and soft shadows.
Camera holds completely still, no zoom, no pan.
Deliberate stepped motion.
[BEAT]: [what changes in this scene]
Absolutely no text, no words, no letters, no numbers anywhere in frame.
```

⚠ **THE RULE THAT MAKES THIS WORK. Anchor every scene to the same frame. Never chain scene two onto
scene one, then three onto two.** Chained in a line, each generation inherits the last one's small
errors and by scene six you have a different character in the same colours. Anchored to one frame,
nothing accumulates. Verified across two separate builds.

### 5. Compose — type INSIDE the scene, never under it

A caption bar beneath a video is the single loudest "these two things were stuck together" tell.
Title cards go *in* the frame: tilted slightly, with a shadow, sitting on the same surface as
everything else.

Then pin **real screenshots** into the world as paper photographs — tilted, cream border, drop
shadow. The animation is obviously made, the screenshots are obviously real, and together the whole
thing reads as checkable.

### 6. Render and prove it moves

```bash
./scripts/render.sh                       # frame-steps, muxes the voice, exports H.264
python3 motion-check.py out/final.mp4     # any static run after 0.5s = FAIL
ffprobe -v error -select_streams v:0 \
  -show_entries stream=codec_name,width,height,color_range,nb_frames out/final.mp4
```

Ship only on `h264`, `1080x1920`, `color_range=tv`, and a frame count matching the composition.

---

## Pace: the third tell

The outlier this was modelled on runs **2.8 seconds a beat**. The first build ran 3.6 over 58
seconds and read as a list. The rebuild came in at 2.9 over 29.1 seconds.

Cutting to that meant losing half the script. The full list only survives on the final frame, which
is the one people screenshot.

---

## Four failures that cost real time

- **A beat longer than its 5s clip holds on the last frame and reads frozen.** Ping-pong through
  the clip instead. Never stretch, never hold.
- **A container at `opacity:0` whose CHILDREN are animated shows nothing.** Every title card was
  invisible for a whole render because of it.
- **Generating on true black paper is not worth the credits.** A test scene came back (27,28,38)
  against a colour-graded (25,26,32) — identical to the eye. Grade the navy instead.
- **Card drift under ~30px across a beat is below the motion check's floor** and reads as static.

---

## Files here

| Path | What it is |
|---|---|
| `scripts/fish-tts` | script config → per-line MP3s → measured timing map |
| `scripts/render.sh` | Puppeteer frame-stepper → ffmpeg → H.264 export with a truncation guard |
| `examples/composition.html` | the working composition, GSAP timeline driven by `window.seek(ms)` |
| `examples/script.json` | a real ten-beat script |
| `examples/timings.json` | what fish-tts writes back |

---

## Long-form: a 4+ minute explainer, and the thing that changes

Proven 29/08/2026 on a 4:09 history-of-neural-networks explainer, 59 beats, **zero generated video
credits**. `examples/compositor-longform.html` is that build.

**Generated video does not scale to long form.** At a Vox pace of ~2.8s a beat, six minutes is ~125
beats, which is roughly 4,000 Higgsfield credits. So above about a minute, **compose the beats in
code and reserve generation for hero moments only.** It is also the better result: an annotation
has to land on the exact word being spoken, and only code reading the voice timings can do that.

Five devices carry an entire explainer: **photo** (Ken Burns over a real archival image),
**annotate** (marker circle and arrow drawing onto that photo), **collage** (torn-edge cut-outs
staggering onto flat colour blocks), **chart** (a line drawing itself), **diagram** (network layers,
or the XOR four-point proof).

**Write the compositor as a PURE FUNCTION OF TIME.** `render(t)` draws the complete frame for time
`t`, with no animation loop and no timeline library. Frame-stepping is then exact and reproducible,
and any frame can be inspected on its own during debugging.

### Four failures this build hit, all worth avoiding

- ⚠ **The motion check failed at 28% static (137 of 489 samples) on the first full render.** A Ken
  Burns of 0.07 zoom across a 4s beat moves ~5px in a 0.5s sample, under the floor. **Every device
  must still be moving at the END of its beat**: finish builds by 50-62% of the beat, then keep a
  marker travelling, nodes breathing, or cards drifting.
- ⚠ **Do not add that motion as a whole-canvas translate.** It pushed the chart and both diagrams
  out of frame. Scale about the CENTRE (`translate(W/2,H/2)` → `scale` → `translate(-W/2,-H/2)`).
- ⚠ **A cross-fade breaks if the outgoing device sets its own `globalAlpha`.** Render the previous
  device to an offscreen canvas and `drawImage` that with the fade alpha.
- ⚠ **Waiting on the output file EXISTING is not waiting for the render.** `moov atom not found`
  is what you get for probing a file ffmpeg is still writing. Wait for the process, not the path.

### Archival images

Wikimedia Commons works and is fast, but **it 403s the default urllib agent** — set a real
`User-Agent`. Record licence and author per file at download time, and render an attribution card
into the video: CC BY and CC BY-SA require it. `assets/CREDITS.tsv` is the manifest format.
