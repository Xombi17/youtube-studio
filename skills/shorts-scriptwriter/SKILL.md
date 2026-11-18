---
name: shorts-scriptwriter
description: Write a high-retention, viral-engineered YouTube Shorts script from a verified premise and defined audience.
---

# Shorts scriptwriter

Ask for or infer the audience, subject, target duration (sweet spot **28–45 seconds**), language, and tone. Read the claim ledger (`research/<topic>/claims.md`) when facts matter—never fabricate statistics, mechanics, or sources. For editorial paper-collage explainers, follow `skills/codex-shorts-blueprint/SKILL.md` (v2.0.0) alongside this skill.

## Mechanism & Visual Proof First (Before Drafting Beats)

Before writing beats, write two explicit sentences at the top of the script:
1. **Hidden mechanism:** One sentence stating the underlying cause or system being explained.
2. **Visual proof:** One sentence describing how the viewer *sees* that mechanism work even if the audio is muted (cross-section, occlusion reveal, matched comparison, or causal chain—not just arrows and large words).

Distinguish **sourced evidence** from **illustrative models**: keep conditional language intact, never treat a viral reference video's claims as independent factual research, and mark any invented example/UI metric as illustrative in `metadata.md`.

## High-Retention Viral Shorts Architecture

1. **Frame-0 "Stop-Stack" Hook (0.0–2.5s — VVSA Gatekeeper):**
   - Start speech at `<= 0.05s` (zero throat-clearing, zero "Hey guys", zero branding intros).
   - Deliver an emotional, counter-intuitive, or 2nd-person premise in **<= 8–10 spoken words** (*"That $4 bag is quietly charging you 25% more—not 20%."*).
   - **Open a curiosity loop** rather than spoiling the entire mechanism in Beat 1—make viewers stay to see *how* or *why*. Frame 0 must already be a composed story image.
2. **Story Over Textbook (Escalating Stakes):**
   - Never label beats like school slides (*"Step 1: Unit Price"*). Frame every beat as a hidden trap, discovery, or consumer reveal tied to everyday reality (*"your shelf"*, *"your bill"*).
   - Insert a **mid-video re-hook / mini-twist** every **10–12 seconds** (*"Wait—it gets worse."*, *"Most people assume 20% less means 20% more. Wrong."*), ensuring the final stretch after the last re-hook does not exceed 12s.
3. **Relentless Pacing & Zero Dead Air:**
   - Target **165–180 WPM** (**85–135 words** for a 30–45s Short).
   - Keep sentences short, punchy, and easy for voice cloning/TTS to enunciate cleanly (avoid tongue-twisters; spell tricky compound words cleanly in TTS hints).
   - Keep inter-beat pauses tight (**0.06–0.12s**); reserve **at most one** **0.18–0.24s** dramatic pause ONLY right before the core twist/payoff.
4. **Seamless Loop Ending:**
   - Never end on a dead-stop conclusion with trailing silence or a generic *"Like and subscribe!"*.
   - Engineer a **Seamless Loop Bridge** where the final phrase grammatically and rhythmically flows directly back into the first word of Beat 1 (e.g., ending with *"...and that's why..."* → loops straight into *"...that $4 snack bag is quietly costing you 25% more."*), with **`<= 0.10s` tail silence** and matching visual anchors.
   - Bake in an **organic comment catalyst** (a relatable everyday realization) without begging for engagement.

## Output Format

Include the two-sentence **Mechanism + Visual Proof** header, then for each beat provide:
- Exact time window, word count, and supporting `claims.md` claim ID
- Spoken narration line (TTS-clean) + display caption chunks (**3–5 words per chunk, max 2 lines**, broken on spoken meaning rather than arbitrary word count)
- Meaningful visual event cue every **1.2–2.0s** stating **what new information the viewer learns** and the **persistent visual anchor** (decorative jitter does not count as an event)
- Material-specific sound design / SFX trigger cue (tied to real actions, not generic cut whooshes)

Read the script aloud or verify timing before delivery; trim until every word earns its second. Mark any unverified claim for research before production. When handing off to `visual-director` / `codex-shorts-blueprint`, map beats into `premium_plan.json` and check structure with `python3 skills/codex-shorts-blueprint/scripts/validate_plan.py`. Deliver the script plus a one-sentence title/thumbnail pairing angle; never promise views or retention outcomes.
