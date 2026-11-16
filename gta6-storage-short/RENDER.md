# RENDER.md — GTA VI Storage Requirements Short

**Project:** `gta6-storage-short`
**Output target:** `gta6-storage-short.mp4`
**Spec:** 1080×1920, 45 seconds, H.264, portrait

---

## Method 1 — Puppeteer / Headless Chrome (Recommended)

> [!IMPORTANT]
> Requires Node.js ≥18 and `puppeteer` installed. The HyperFrames renderer drives Chrome programmatically, seeks the GSAP timeline, and captures frames.

### Install dependencies

```bash
cd /home/varad/Videos/youtube/gta6-storage-short
npm install puppeteer
```

### Render script (save as `render.js`)

```js
const puppeteer = require('puppeteer');
const { execSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const HTML = path.resolve(__dirname, 'index.html');
const OUT_DIR = path.resolve(__dirname, 'frames');
const FPS = 30;
const DURATION = 45;
const TOTAL_FRAMES = FPS * DURATION;

fs.mkdirSync(OUT_DIR, { recursive: true });

(async () => {
  const browser = await puppeteer.launch({
    defaultViewport: { width: 1080, height: 1920, deviceScaleFactor: 1 },
    args: ['--no-sandbox', '--disable-web-security', '--allow-file-access-from-files'],
  });
  const page = await browser.newPage();
  await page.goto(`file://${HTML}`, { waitUntil: 'networkidle0' });

  // Boot timeline
  await page.evaluate(() => {
    window.__timelines['main'].seek(0);
  });

  for (let i = 0; i < TOTAL_FRAMES; i++) {
    const t = i / FPS;
    await page.evaluate((t) => window.__timelines['main'].seek(t), t);
    const framePath = path.join(OUT_DIR, `frame_${String(i).padStart(5, '0')}.png`);
    await page.screenshot({ path: framePath, type: 'png' });
    if (i % 30 === 0) process.stdout.write(`\rFrame ${i}/${TOTAL_FRAMES}`);
  }

  await browser.close();
  console.log('\nFrames captured. Encoding…');

  execSync(
    `ffmpeg -y -r ${FPS} -i "${OUT_DIR}/frame_%05d.png" ` +
    `-c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p ` +
    `-vf "scale=1080:1920" ` +
    `"${path.resolve(__dirname, 'gta6-storage-short.mp4')}"`,
    { stdio: 'inherit' }
  );

  console.log('Done → gta6-storage-short.mp4');
})();
```

### Run

```bash
node render.js
```

---

## Method 2 — Screen Recording (Quick / No Node renderer)

1. Open `index.html` in Chrome, set zoom to fit 1080×1920 (use DevTools device mode).
2. Trigger the timeline:
   ```js
   // Paste in DevTools console:
   window.__timelines['main'].play(0);
   ```
3. Record with OBS or QuickTime cropped to the browser viewport (1080×1920).
4. Export as MP4 H.264.
5. Trim to exactly **45 seconds** in any video editor.

---

## Method 3 — HyperFrames CLI (if installed)

```bash
npx hyperframes render \
  --input ./index.html \
  --output gta6-storage-short.mp4 \
  --width 1080 --height 1920 \
  --fps 30 --duration 45
```

---

## Add a Silent Audio Track

The project has no audio. Add a silent track so YouTube's encoder is happy:

```bash
ffmpeg -i gta6-storage-short.mp4 \
  -f lavfi -i anullsrc=r=44100:cl=stereo \
  -shortest -c:v copy -c:a aac -b:a 128k \
  gta6-storage-short-audio.mp4
```

Or replace with a YouTube Audio Library track (royalty-free):

```bash
ffmpeg -i gta6-storage-short.mp4 \
  -i path/to/music.mp3 \
  -map 0:v -map 1:a \
  -shortest -c:v copy -c:a aac -b:a 128k \
  gta6-storage-short-final.mp4
```

---

## Verify Output with ffprobe

```bash
ffprobe -v error \
  -select_streams v:0 \
  -show_entries stream=width,height,r_frame_rate,codec_name,duration \
  -of default=noprint_wrappers=1 \
  gta6-storage-short.mp4
```

**Expected output:**

```
codec_name=h264
width=1080
height=1920
r_frame_rate=30/1
duration=45.000000
```

---

## Expected Final File

| Property | Value |
|---|---|
| Filename | `gta6-storage-short.mp4` |
| Codec | H.264 (libx264) |
| Resolution | 1080×1920 (portrait, 9:16) |
| Frame rate | 30 fps |
| Duration | 45 seconds |
| Audio | Silent or YT Audio Library track |
| File size (est.) | ~40–80 MB at CRF 18 |
