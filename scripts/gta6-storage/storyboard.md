# Storyboard: GTA VI Storage Requirements
# Format: 45-second Vertical Short (1080×1920)
# Color palette: #101d2b (dark navy) | #f47750 (orange) | #e96643 (coral) | #f1eee7 (cream)
# Typography: Inter (headings) | IBM Plex Mono (eyebrows/labels)
# Tool: HyperFrames infographic renderer

---

## Scene 1 — HOOK CARD
**Duration:** 0:00–0:05 (5 seconds)
**Visual type:** HyperFrames static card with number reveal
**Background color:** `#101d2b` (dark navy)
**Text content:**
- Eyebrow (IBM Plex Mono, 18px, `#f47750`): "STORAGE ALERT"
- Giant number (Inter Black, 160px, `#f47750`): "212"
- Unit label (Inter Bold, 48px, `#f1eee7`): "GB"
- Subtitle (Inter Regular, 28px, `#f1eee7`): "of free space — that's what GTA VI needs"
- Progress bar at bottom: 0→11% (represents 5/45s elapsed)
**Animation:** "212" scales from 0.6→1.0 with orange flash; subtitle fades in 0.3s later
**Caption text:** "GTA 6 needs 212 GB of free space"

---

## Scene 2 — THE SCALE (Bar Comparison)
**Duration:** 0:05–0:14 (9 seconds)
**Visual type:** HyperFrames dual horizontal bar chart
**Background color:** `#f1eee7` (cream)
**Text content:**
- Eyebrow (IBM Plex Mono, 18px, `#101d2b`): "THE SCALE"
- Title (Inter Bold, 42px, `#101d2b`): "PS5 has ~825 GB usable"
- Bar 1 label: "GTA VI — 212 GB" | fill: `#f47750` | width: 212/825 = 25.7% of bar track
- Bar 2 label: "PS5 Usable — 825 GB" | fill: outline only `#101d2b` | width: 100%
- Callout label (IBM Plex Mono, 20px, `#e96643`): "≈ 26% of your whole drive"
- Progress bar: 11→31%
**Animation:** Bar 1 animates width left-to-right over 0.6s; Bar 2 outline appears first, then Bar 1 fills inside. Callout label slides in after both bars drawn.
**Caption text:** "That's about a quarter of your PS5's storage"

---

## Scene 3 — HOW TO FREE SPACE
**Duration:** 0:14–0:27 (13 seconds)
**Visual type:** HyperFrames animated numbered list
**Background color:** `#e96643` (coral)
**Text content:**
- Eyebrow (IBM Plex Mono, 18px, `#101d2b`): "HOW TO FREE SPACE"
- Item 1 (Inter Bold, 36px, `#101d2b`): "1. Delete unused games"
  Sub (Inter Regular, 22px, `#101d2b`, 70% opacity): "saves stay safe in PS5 cloud"
- Item 2 (Inter Bold, 36px, `#101d2b`): "2. Move saves to USB"
  Sub: "clears internal SSD headroom"
- Item 3 (Inter Bold, 36px, `#101d2b`): "3. Add an M.2 NVMe SSD"
  Sub: "fastest permanent fix — PS5 expansion slot"
- Progress bar: 31→60%
**Animation:** Items slide in from left with 0.4s stagger — Item 1 at 0s, Item 2 at 0.5s, Item 3 at 1.0s. Each item icon (✓ checkmark) draws in before text.
**Caption text:** "Delete games, back up saves, or expand with M.2 SSD"

---

## Scene 4 — PRELOAD IS LIVE
**Duration:** 0:27–0:38 (11 seconds)
**Visual type:** HyperFrames countdown/announcement card
**Background color:** `#101d2b` (dark navy)
**Text content:**
- Eyebrow (IBM Plex Mono, 18px, `#f47750`): "PRELOAD IS LIVE"
- Title (Inter Black, 52px, `#f1eee7`): "Started Nov 10"
- Sub (Inter Regular, 30px, `#f47750`): "Download it NOW"
- Body (Inter Regular, 24px, `#f1eee7`): "Launches Nov 19 at midnight"
- Small note (IBM Plex Mono, 16px, `#f1eee7`, 60% opacity): "~210 GB — give it time to download"
- Animated element: 3 pulsing orange circles (orbit dots) rotating slowly around a central "GTA VI" badge
- Progress bar: 60→84%
**Animation:** Title slides down from top; sub pulses; orbit dots rotate continuously at 20rpm.
**Caption text:** "Preload started Nov 10 — download now, launches Nov 19"

---

## Scene 5 — CTA CARD
**Duration:** 0:38–0:45 (7 seconds)
**Visual type:** HyperFrames tag/badge card
**Background color:** `#101d2b` (dark navy)
**Text content:**
- Eyebrow (IBM Plex Mono, 18px, `#f47750`): "MORE GTA 6 TIPS"
- Title (Inter Bold, 48px, `#f1eee7`): "Follow for daily GTA 6 updates"
- Badge pills (rounded rect, `#f47750` fill, `#101d2b` text, IBM Plex Mono 20px):
  - "STORAGE"
  - "PRELOAD"
  - "EDITIONS"
- Channel handle (Inter Regular, 22px, `#f1eee7`, bottom-right): "@[CHANNEL]"
- Progress bar: 84→100%
**Animation:** Badges bounce in with spring easing, 0.15s stagger. Title fades in. Channel handle slides from bottom.
**Caption text:** "Follow for more GTA 6 guides"

---

## Technical Specs

| Property | Value |
|---|---|
| Resolution | 1080 × 1920 px (vertical) |
| Total duration | 45 seconds |
| Frame rate | 30 fps |
| Output format | MP4 (H.264) |
| Audio | Silent track or royalty-free music (YouTube Audio Library) |
| Captions | Hardcoded per scene OR separate SRT file |
| Render tool | HyperFrames (Puppeteer headless Chrome) |

## Assets Checklist

- [ ] No real GTA VI footage or screenshots used
- [ ] All graphics are original HTML/CSS/JS
- [ ] No copyrighted logos used
- [ ] Bar chart data derived from official figures
- [ ] All text cross-referenced with research/gta6-storage/claims.md
