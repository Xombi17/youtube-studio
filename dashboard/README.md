# CreatorRadar Dashboard

A lightweight, file-based dashboard for tracking the YouTube production pipeline.

---

## Purpose

The dashboard provides a single place to monitor:

1. **Content idea queue** — from raw idea to published, with status per stage
2. **Production status** — which videos are in which stage of the pipeline
3. **Monetization progress** — watch hours and Shorts views toward YPP thresholds
4. **GTA VI info monitoring** — newly published official Rockstar/PlayStation/Xbox updates

---

## Components

### 1. Daily Gaming Trend Discovery

**Manual workflow:**
- Check YouTube trending (Gaming tab) each morning
- Check Google Trends → `trends.google.com` → "GTA 6" topic
- Check Rockstar Newswire: `rockstargames.com/newswire`
- Check PlayStation Blog: `blog.playstation.com`
- Log new opportunities directly into `ideas-queue.md`

**Optional automation (requires setup):**
- YouTube Data API v3 — `GET /youtube/v3/videos?chart=mostPopular&videoCategoryId=20` (category 20 = Gaming)
- Requires API key in `.env` (never commit to git)
- Script location (future): `dashboard/scripts/trend-fetch.js`

### 2. GTA VI Info Monitoring

Monitor these sources for new announcements:
- `rockstargames.com/newswire` — official blog
- `support.rockstargames.com/VI` — support docs updates
- `playstation.com/en-in/support/games/gta-vi-support/` — PS5 guidance updates
- Official Rockstar YouTube: `youtube.com/@RockstarGames`

When new information is found: update `config/gta6-sources.md` and add new content ideas to the queue.

### 3. Topic Opportunity Ranking

Ideas in `ideas-queue.md` are ranked by **Priority** (High / Medium / Low) based on:
- Search demand (trending topic vs. evergreen)
- Time-sensitivity (pre-launch, day-one, post-launch window)
- Production effort vs. expected reach
- Competition (how many similar videos exist already)

### 4. Content Idea Queue

See `ideas-queue.md` for the live table.

**Status values:**

| Status | Meaning |
|---|---|
| `idea` | Raw idea captured, not yet researched |
| `research` | Research and fact-checking in progress |
| `scripted` | Script complete, awaiting storyboard |
| `produced` | Video rendered and edited, awaiting review |
| `approved` | Human-approved, ready to upload |
| `published` | Live on YouTube |
| `blocked` | Stuck — missing asset, rights issue, etc. |

### 5. Production Status Tracker

For each active video, the pipeline stages are tracked in its claims ledger and storyboard files:

```
research/<topic>/claims.md        — research + fact-check stage
scripts/<topic>/script.md         — scripting stage
scripts/<topic>/storyboard.md     — storyboard stage
renders/<topic>/                  — rendering + editing stage
exports/<topic>/metadata.md       — SEO metadata stage
```

### 6. Monetization Progress Tracker

Update manually from YouTube Studio Analytics:

| Metric | Target | Current | Last Updated |
|---|---|---|---|
| Subscribers | 1,000 (already met) | ~11,000 | — |
| Watch hours (12 months) | 4,000 hours | [check Studio] | — |
| Shorts views (90 days) | 10,000,000 | [check Studio] | — |
| Community Guidelines strikes | 0 | [check Studio] | — |
| AdSense linked | ✅ | [confirm] | — |

---

## File Structure

```
dashboard/
  README.md           ← this file
  ideas-queue.md      ← live content idea tracking table
  scripts/            ← (future) automation scripts
```
