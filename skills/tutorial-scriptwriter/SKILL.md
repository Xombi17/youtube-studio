---
name: tutorial-scriptwriter
description: Write factual GTA VI tutorial scripts using verified claims only. Builds on shorts-scriptwriter for 30-60s vertical format.
---

## Purpose
Produce a beat-by-beat tutorial script for a 30–60 s vertical Short (or longer form) from a verified claim ledger.

## Input Required
- Claim ledger from `gta6-researcher` or `source-researcher` (research/<topic>/claims.md)

## Script Format
Each beat:
```
[00:00–00:05] HOOK
Spoken: "Here's exactly how much storage GTA VI needs on PS5."
On-screen text: "GTA VI Storage — The Real Numbers"
Visual: Infographic card — storage bar
Caption: GTA VI file size revealed
```

## Rules
- **Voice**: second-person instructional ("Go to Settings > Storage")
- **Hook**: state the concrete value in the first beat
- **Close**: one specific action item — NOT a generic subscribe ask
- **Unverified claims**: flag inline as `[VERIFY BEFORE PUBLISH]`
- **PS5-specific steps**: label `[PS5]` vs general console steps
- **Disclaimer**: if no personal gameplay testing, append footer:
  > Steps based on official Rockstar/PlayStation documentation. Verify on your own console before following.

## Timing Guide
| Format | Duration | Beats |
|--------|----------|-------|
| Short  | 30–60 s  | 5–8   |
| Medium | 2–5 min  | 12–20 |
| Long   | 5–15 min | 20–50 |

## Output
Save to `scripts/<topic>/script.md`
