# Model Routing Strategy

This document defines which AI model tier to use for each class of task in the production pipeline. Correct routing reduces cost and latency while ensuring quality where it matters.

---

## Routing Table

| Task Class | Examples | Model Tier | Notes |
|---|---|---|---|
| **Small / Fast** | Classification, tag generation, metadata formatting, caption timing, file renaming, search query generation | `gemini-2.0-flash-lite` or equivalent flash-lite | Batch-able; run as many as needed in parallel |
| **Medium** | Research organisation, claim ledger assembly, basic scripting (outline → draft), SEO description drafts | `gemini-2.0-flash` or equivalent flash | Good balance of speed and coherence |
| **Complex** | Original script writing, art direction, storyboard planning, QA review, fact-check adjudication, final copy editing | `gemini-2.5-pro` / thinking models | Use sparingly; justify in task brief |
| **Local tools** | Video assembly, caption burning, format conversion, audio mixing | FFmpeg (CLI) | No AI quota used; prefer for all editing tasks |
| **Rendering** | AI animation scenes, HyperFrames compositions, motion graphics | HyperFrames / Node.js locally | No remote AI quota unless using external API |

---

## Decision Rules

1. **Default to flash** for any task where quality can be verified quickly (e.g., a script outline that gets human review anyway).
2. **Escalate to pro/thinking** only when the output is high-stakes and not easily reversible (final published script, storyboard that drives expensive rendering).
3. **Never use a larger model** just because it's available. Document the reason when using pro/thinking in the task log.
4. **Re-use cached research** before firing a new research call — check `research/cache/<topic>/` first.

---

## Local Tools

| Tool | Purpose | Install check |
|---|---|---|
| `ffmpeg` | Video concat, caption burn, audio mix, format export | `ffmpeg -version` |
| `ffprobe` | Validate output duration, streams, metadata | bundled with ffmpeg |
| `node` / `npm` | HyperFrames rendering pipeline | `node --version` |
| HyperFrames | Motion graphics and AI animation scene rendering | See `README.md` install status |

---

## Research Cache

All research outputs are stored to avoid redundant API calls:

```
research/cache/<topic>/
  ├── claims.md          — verified claim ledger
  ├── sources.md         — source URLs + access dates
  └── raw-notes.md       — unprocessed research notes
```

Before starting any research task, check if `research/cache/<topic>/` already exists and is recent (< 7 days old for fast-moving topics like GTA VI launch; < 30 days for evergreen topics).

---

## Cost Discipline

- Research agents: flash (not pro) unless claim adjudication is genuinely ambiguous.
- SEO generation: flash-lite for tag lists; flash for descriptions.
- Script drafts: flash; escalate specific sections to pro only if needed.
- Never run pro/thinking models on tasks that an automated verification step will re-run anyway.
