---
name: video-director
description: Plan shot-by-shot visual execution for GTA VI tutorials and gaming content. Extends visual-director with gaming-specific patterns.
---

## Purpose
Produce a human-readable shot list and a HyperFrames scene spec JSON for each script beat.

## Brand Palette (GTA VI / CreatorRadar)
| Token | Hex |
|-------|-----|
| Background navy | `#101d2b` |
| GTA orange | `#f47750` |
| Accent coral | `#e96643` |
| White text | `#ffffff` |

## Shot Types
| Type | Use case |
|------|----------|
| Infographic card | Storage bars, edition comparison tables |
| Kinetic text | Stat reveals, numbered steps |
| Illustrated UI mockup | Console menu flow (never real screenshots passed as genuine) |
| Official promo art | Rockstar press-kit images with attribution overlay |
| Green-screen host | Commentary / reaction segments |

## Scene Spec (per beat)
```
Scene N:
  Duration: 4s
  Type: infographic-card
  Text: "212 GB required free space"
  Animation: count-up number, fade in bar
  Caption: "GTA VI needs 212 GB free"
  Source requirement: support.rockstargames.com/VI
  Footage flag: none | [FOOTAGE NEEDED — owned/licensed/official promo only]
```

## HyperFrames JSON Output
Emit a parallel `storyboard-scenes.json` array alongside the human shot list.

## Never
- Use real gameplay screenshots you don't personally own
- Pass AI-generated imagery as genuine game footage, or AI-generated charts/maps as measured evidence
- Render top masthead bars, `CATEGORY // SUBTITLE` kickers, divider lines, `01 / 09` beat-counter rectangles, bottom source/disclaimer bars, timers, or progress bars on screen — keep critical 9:16 graphics inside `x = 60–910, y = 200–1350` (hero `x = 60–900, y = 220–1180`, captions `x = 70–900, y = 1160–1340`), mark any illustrative UI mockup in `metadata.md`, and include at least one visual-proof/comparison sequence rather than disconnected static cards

## Output
Save to `scripts/<topic>/storyboard.md` + `scripts/<topic>/storyboard-scenes.json` (plus `premium_plan.json` validated via `skills/codex-shorts-blueprint/scripts/validate_plan.py` for 9:16 editorial Shorts)
