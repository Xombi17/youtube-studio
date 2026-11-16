# GTA VI — Authoritative Sources Registry

This file defines the **only approved primary sources** for GTA VI factual claims used in scripts, descriptions, and on-screen text. Every claim must be traceable to one of these sources.

> **Last updated:** November 2026

---

## Tier 1 — Official Primary Sources (Highest Confidence)

| Source | URL | Type | Notes |
|---|---|---|---|
| Rockstar Games — GTA VI official page | `rockstargames.com/VI` | Publisher official | Main product page; pricing, editions, release date |
| Rockstar Games Support — GTA VI | `support.rockstargames.com/VI` | Publisher support docs | Technical specs, file size, preload info |
| PlayStation — GTA VI Support | `playstation.com/en-in/support/games/gta-vi-support/` | Platform holder | PS5-specific storage, install, preload guidance |
| Xbox — GTA VI Support | Xbox official support (search `GTA VI` on `support.xbox.com`) | Platform holder | Xbox Series X\|S specific guidance |
| Rockstar Games Newswire | `rockstargames.com/newswire` | Official blog | Official announcements, patch notes, event news |

---

## Tier 2 — Official Adjacent (High Confidence, Attribute Carefully)

| Source | URL | Type | Notes |
|---|---|---|---|
| PlayStation Store listing | `store.playstation.com` | Platform store | Edition names, pricing, DLC contents |
| Xbox Store listing | `xbox.com/en-US/games/store` | Platform store | Edition names, pricing, pre-order bonuses |
| Official GTA VI Trailers | YouTube → `youtube.com/@RockstarGames` | Official trailers | Visual gameplay snippets — usable under Rockstar Video Policy for commentary |

---

## Known Verified Facts (as of November 2026)

> These facts have been confirmed by Tier 1 sources. Mark as CONFIRMED in claim ledgers.

| Fact | Value | Source | Confidence |
|---|---|---|---|
| Release date | November 19, 2026 | Rockstar official | ✅ CONFIRMED |
| Platforms at launch | PS5 and Xbox Series X\|S only (no PC at launch) | Rockstar official | ✅ CONFIRMED |
| Preload start date | November 10, 2026 | Rockstar/PlayStation support | ✅ CONFIRMED |
| PS5 install file size | ~210 GB (download) / ~212 GB space required | PlayStation support | ✅ CONFIRMED |
| Standard Edition price | $79.99 USD | Rockstar / PlayStation Store | ✅ CONFIRMED |
| Ultimate Edition price | $99.99 USD | Rockstar / PlayStation Store | ✅ CONFIRMED |
| PC release | Not announced for 2026 launch | Rockstar official | ✅ CONFIRMED (no PC at launch) |

---

## What NOT to Claim Without Independent Verification

The following categories of information must **not** be stated as fact unless independently verified from a Tier 1 source with a URL and access date:

- In-game mechanics (how driving, combat, wanted levels work)
- Mission names, mission count, story plot details
- In-game cheat codes
- In-game map size or region names (unless from official source)
- Character backstory details beyond official trailers
- Any post-launch DLC or update content
- Multiplayer (GTA Online VI) feature details unless officially announced
- Performance specs (frame rate, resolution modes) unless confirmed by Rockstar or platform holder
- Mod support details

> **Rule:** If you cannot link to a Tier 1 or Tier 2 source, do not state it as fact. Present as "reportedly" or "according to [secondary source]" and flag for human review.

---

## Secondary Sources (Use with Caution — Label as Unverified)

These may be referenced for context or as leads, but claims from them must be flagged UNVERIFIED in the claim ledger and not presented as confirmed facts:

- IGN, GameSpot, Eurogamer, Kotaku (cite article + date)
- GTA Wiki / GTA Fandom (community-maintained; may be outdated or speculative)
- Reddit (r/GTA6, r/GrandTheftAutoV) — leads only, not citable

---

## Claim Ledger Template

For each research task, create `research/<topic>/claims.md` with this format:

```markdown
| Claim | Source URL | Access Date | Tier | Confidence | Verified By |
|---|---|---|---|---|---|
| File size is ~212GB | support.rockstargames.com/VI | 2026-11-16 | 1 | CONFIRMED | [agent name] |
| Cheat codes include X | — | — | — | UNVERIFIED | — |
```
