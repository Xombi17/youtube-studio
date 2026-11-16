---
name: copyright-checker
description: Verify all assets are cleared for YouTube use before export. Extends clip-rights-checker with GTA VI specific guidance.
---

## Purpose
Produce a clearance table for every asset in a video before export. Block export of any uncleared asset.

## GTA VI / Rockstar Policy
Rockstar Games Video Policy (https://www.rockstargames.com/videoclippolicy) allows commentary, reviews, and tutorials using **in-game footage from your own gameplay**.

**Current status**: Since the game is not yet owned, only the following may be used:
| Asset type | Status | Condition |
|-----------|--------|-----------|
| Official trailers | ✅ Cleared | Commentary/reaction use; cite policy URL |
| Official press-kit screenshots | ✅ Cleared | With attribution: "© Rockstar Games" |
| Your own gameplay capture | ✅ Cleared (post-launch) | Only after you own the game |
| Third-party gameplay footage | ⚠️ Conditional | Requires individual rights check |
| Fan art / unofficial assets | ❌ Uncleared | Do not use without explicit license |

## Music
- ✅ YouTube Audio Library tracks
- ✅ Licensed tracks (document license)
- ❌ Copyrighted BGM (even short clips)

## AI-Generated Images
- ✅ Cleared if no third-party IP infringed
- Disclosure required: add "AI-generated graphics" in video description

## Clearance Table Output
```
| Asset filename | Source | License | Status | Attribution text |
|----------------|--------|---------|--------|-----------------|
```
Statuses: `cleared` | `conditional` | `uncleared`

## Block Rule
Do not proceed to video-editor if any asset is `uncleared`.

## Output
Append to `assets/clearance-log.md`
