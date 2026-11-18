---
name: youtube-seo
description: Generate YouTube-optimized title, description, tags, thumbnail concept and chapter markers for gaming content.
---

## Purpose
Produce a complete `metadata.md` for a finished video — ready to paste into YouTube Studio or ingest into the publishing pipeline.

## 1. Title Strategy

### For Long-Form Videos (16:9)
- 50–60 characters
- Leading keyword first
- Clear value signal (number, outcome, comparison)
- *Examples:*
  - `GTA 6 File Size: How to Free Up 212GB on PS5`
  - `GTA 6 Standard vs Ultimate Edition — What You Get`

### For YouTube Shorts (9:16) — 2026 Viral Packaging
- **Length:** Strict maximum **< 55 characters** so it does not truncate on mobile Browse/Home tabs.
- **End-Payoff Hooks:** Promise a twist or reveal at the end to drive Average Percentage Viewed (APV) > 100%.
  - *Example:* `What happens at the 25-second mark is insane`
  - *Example:* `The final stat on GTA 6 changes everything`
- **Reverse-Psychology Friction:** Trigger viewer interaction and comments.
  - *Example:* `Whatever you do, don't tap the sound`
  - *Example:* `Don't buy the GTA 6 physical edition yet`

## 2. Description Structure & Hashtag Hygiene

### Hashtags (Critical 2026 Rules)
- **Strictly 3–5 niche-relevant hashtags** (e.g. `#Shorts #GTA6 #Gaming`).
- **Never tag stuff:** Over 15 tags causes YouTube to ignore all tags. Over 60 tags triggers automated spam de-indexing ("0-view jail").
- Select the proper **Video Category** in YouTube Studio (Gaming, Science & Technology) rather than attempting to spam description tags.

### Description Template
```
Line 1: Primary keyword + value hook (visible before fold)
Line 2: Supporting intrigue / comment catalyst (visible before fold)

Full explanation & context...

#Shorts #PillarTag #NicheTag

Sources:
- <official URL>

AI disclosure: Graphics created with AI assistance. All facts sourced from official documentation.
[Channel links / socials]
```

## 3. Custom Thumbnail Frame Strategy (Browse Features 2x Funnel)
- Shorts without thumbnails rely 100% on the volatile Shorts Feed. Custom thumbnails push Shorts to the **YouTube Home Feed (Browse Features)** alongside long-form videos.
- Bake a high-contrast 1080×1920 thumbnail card into the video timeline for 1–2 frames.
- **Mobile Upload Requirement:** Upload via the YouTube Mobile App and tap the **Pencil icon** on the video preview to scrub and lock the custom frame. Desktop does not permit custom thumbnail selection for Shorts.

## 4. Staging & Scheduling Protocol
- **Staging Visibility:** Always upload as **UNLISTED** (never Private). Unlisted status allows YouTube to finish Content ID / copyright scanning and 1080p60 encoding before launch.
- **Audience Peak Velocity:** Check **YouTube Analytics > Audience** and schedule/publish **60 minutes before the daily peak viewing hour** to capture the initial seed wave.
- **Related Video Link:** Always set a **Related Video** in YouTube Studio to funnel Shorts viewers into a long-form binge session.

## 5. Chapters (Videos > 2 min)
```
0:00 Intro
0:12 The numbers
0:45 How to free up space
1:30 Which edition to buy
```

## Never
- Promise views, rankings, or monetization timelines
- Use clickbait titles that contradict the video content

## Output
Save to `exports/<topic>/metadata.md`
