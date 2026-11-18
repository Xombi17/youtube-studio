# Clipping Studio — Improvement Review

Reviewed: engine, clipper scripts, dashboard API, Next.js panel.
Method: code reading of the live path end-to-end. No runtime tests were executed.
All paths are relative to the repo root; line numbers as of this review.

**Verdict:** the pipeline is feature-rich and unusually well thought out (multimodal fusion,
synergy, taste memory, free-tier budgeting, approval gating). The weaknesses are not in the
scoring idea — they are in the **clip window arithmetic**, **error isolation during export**,
and **the fact that the danger zones are silent**. Those three account for most of the "why did
this clip miss the moment" and "why did the session die" classes of bug.

---

## 1. The six that matter most

| # | Problem | Impact |
|---|---|---|
| 1 | Clip window math drops the post-pad (and can drop the trigger segment entirely) | Clips end before the reaction |
| 2 | Export runs inline in the live polling loop | Scoring freezes 30–120 s per clip; peak-escalation and cooldowns go blind |
| 3 | One export exception kills the whole session | Loses all pending clips + the session |
| 4 | Dashboard API has `Access-Control-Allow-Origin: *` and no auth | Any website can start/delete/upload in the user's browser |
| 5 | YouTube chat depends on abandoned `pytchat`, and failure is silent | Up to 55 scoring points silently missing |
| 6 | No overlap/IoU dedupe between clips | Duplicate clips of the same moment |

---

## 2. P0 — Correctness

### C1. Clip window excludes the post-pad (and can exclude the peak)

**Evidence:** `orchestration/live_clipper_agent.py:2381-2384` (live) and `:2094-2096` (VOD):

```python
start_idx = max(0, idx - pre_segs_use)
end_idx = min(start_idx + max_clip_segs - 1, idx + post_segs)
```

`max_clip_segs` is a **total-length** cap measured from `start_idx`, but the code treats it as if
the window were centered on `idx`. Whenever `pre_segs_use + post_segs >= max_clip_segs`, the
`min()` clamps `end_idx` to `start_idx + max_clip_segs - 1`, which can be **before** `idx`.

Concrete failure with the dashboard's own defaults:

| Input | Value | Segments |
|---|---|---|
| `chat_pre_pad` | 20 s (`LiveClipperPanel.tsx:43`) | `chat_pre_segs = 2` |
| `post_pad` | 8 s (`LiveClipperPanel.tsx:44`) | `post_segs = 1` |
| `max_clip_sec` | 30 s (`LiveClipperPanel.tsx:45`) | `max_clip_segs = 3` |

`start = idx-2`, `end = min(idx, idx+1) = idx`. **Post-pad is effectively 0 s** even though the
UI promises 8 s. Raise `chat_pre_pad` to 30 s (3 segments) and `end = min(idx-1, idx+1) = idx-1`:
the clip ends **one full segment before the moment that triggered it**.

The same formula also cripples dynamic peak extension (`:2360`): `new_end` is clamped by
`start_idx + max_clip_segs - 1`, so with a long lookback the window cannot grow at all —
the "ride the peak" feature silently no-ops.

**Fix:** size the pre-roll to leave room for the post-roll, then cap:

```python
# keep the trigger and its reaction; shrink lookback if the budget is tight
post_use = min(post_segs, max_clip_segs - 1)
pre_use  = min(pre_segs_use, max_clip_segs - 1 - post_use)
start_idx = max(0, idx - pre_use)
end_idx   = min(idx + post_use, start_idx + max_clip_segs - 1)
```

`new_end` in the extension branch should be `min(idx + post_segs, job["start_idx"] + max_clip_segs - 1)`
and should also be allowed to **slide** `start_idx` forward if the peak moved.

**Tests to add:** property test asserting `start_idx <= trigger_idx <= end_idx` and
`end_idx - start_idx + 1 <= max_clip_segs` for all combinations of
`(pre_pad, post_pad, max_clip_sec, seg_dur)`.

---

### C2. Export blocks the live loop

**Evidence:** `orchestration/live_clipper_agent.py:2427-2446` — `stitch_segments()` +
`export_clip_package()` are called synchronously inside `while True:` / `for job in pending_clips`.
VOD has the same problem at `:2106-2119`.

`export_clip_package` does: wav extract → probe → smart-trim → reaction peaks → render (NVENC or
`libx264 medium`) → loudnorm (`:1640-1930`). On the RTX 4060 laptop this is maybe 15–40 s; on CPU
it can be 60–120 s. During that time:

- new `seg_*.ts` files are not scored, so `sample_window_score` history and `recent_txt` fall behind;
- dynamic peak extension cannot fire;
- `cooldown_segs` timers are measured against the frozen `idx` (it's segment-based, so the next
  trigger can fire back-to-back once the loop resumes);
- chat keeps accumulating on its own thread, so chat windows are wall-clock while the scoring loop
  is segment-clock — they drift apart.

**Fix:** one exporter worker (single-threaded, to keep NVENC/CPU sane):

```python
export_q: queue.Queue[dict] = queue.Queue()

def _export_worker():
    while True:
        job = export_q.get()
        if job is None: break
        try:
            ...stitch, export, enqueue groq batch...
        except Exception:
            log.exception("export failed for %s", job["clip_id"])
            persist_failed(job)
        finally:
            export_q.task_done()

threading.Thread(target=_export_worker, daemon=True).start()
```

Materialize the window before queueing (segments are pruned at `:2549-2553` — `safe_floor` protects
pending jobs but **not** queued export jobs once they're removed from `pending_clips`). Either copy
the `.ts` files into the job dir, or extend `safe_floor` to include queued jobs.

---

### C3. A single export failure ends the session

**Evidence:** no `try/except` around `stitch_segments` / `export_clip_package` at `:2433-2443`.
`stitch_segments` uses `subprocess.run(..., check=True)` (`:2009-2019`), so a non-zero FFmpeg exit
raises `CalledProcessError` straight through the live loop (caught only by `finally` teardown).
A transient Groq 429 inside `export_clip_package` (`:1666-1690`) can do the same.

**Fix:** per-job `try/except Exception`, mark the clip `FAILED` in state with the reason, keep
going. Also consider `stitch_segments` returning `None` instead of raising.

---

### C4. Copy-concat is fragile across reconnects

**Evidence:** `:2004-2019` — `-c copy` over `seg_*.ts`. After a reconnect (`:2560-2575`) the new
FFmpeg process restarts `-segment_start_number` but the stream's codec parameters / timestamps may
have reset. `-c copy` assumes identical timebase and SPS/PPS; mismatches give A/V drift, frozen
frames, or a hard failure.

**Fix:** add `-fflags +genpts -avoid_negative_ts make_zero`, and on failure retry with

```python
["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-b:a", "192k"]
```

Log when the fallback is used — repeated fallbacks indicate an unstable source, which is itself
useful signal for auto-scout.

---

### C5. Disk exhaustion has no guard in the clipper

**Evidence:** `shutil.disk_usage` appears only in `scripts/studio_doctor.py:84`. Nothing in
`orchestration/` or the clipper routes checks free space before export or before writing the ring
buffer.

A 1080p60 session at `buffer_minutes` default (see `:2210`) plus a 30–60 s clip per trigger can
consume multiple GB/hour. When the disk fills, FFmpeg fails mid-write and C3 applies.

**Fix:** pre-flight in the export worker (`< 3 GB` → refuse new exports, set state status
`DISK_LOW`), and prune exported `B-TIER` clips oldest-first above a configurable ceiling
(`max_exports_gb`). Surface free space in the panel.

---

### C6. YouTube chat: abandoned dependency, silent failure

**Evidence:** `:531-585` imports `pytchat` and returns silently on `ImportError` (`:546-549`);
all exceptions are swallowed at `:577-579` with a 5 s retry and `self.connected = False`.
`pytchat`'s last release is 2021 and it breaks whenever YouTube changes InnerTube — this is a
known, recurring failure mode, not a hypothetical.

Because chat is worth 0–55 points in fusion, a silent `pytchat` failure turns an S-Tier stream into
a B-Tier one with no explanation. The user just sees "nothing good happened".

**Fix (short term):** log a prominent warning on start, and expose per-platform
`chat.connected` in the panel (the state already carries it — verify it's rendered, not just in JSON).
**Fix (proper):** add an HTTP fallback that polls
`https://www.youtube.com/youtubei/v1/live_chat/get_live_chat` with the `continuation` token from
the watch page. That removes the dependency entirely and is ~150 lines.

---

## 3. P1 — Clip quality & scoring

### Q1. No overlap suppression between clips

**Evidence:** `:2375-2392` enforces only `cooldown_segs` between *triggers*, and the extension loop
(`:2359-2372`) can extend an existing job into a new trigger's territory. Nothing checks whether a
new window intersects a `pending_clips` window or the last N exported windows.

**Fix:** compute IoU on `[start_idx, end_idx]` (or timestamp overlap) against pending + the last
`dedupe_window` exported clips; if IoU > 0.5, merge into the better-scoring job instead of emitting.

### Q2. Grading uses the peak score, not the clip's score

**Evidence:** `moment_info["fusion"] = fusion` stores the trigger-window fusion (`:2393-2399`) and
is never recomputed after the window is assembled or extended. A clip whose first 20 s are dead air
but whose peak segment scored 91 will still be labelled `S-TIER`.

**Fix:** keep the existing `score_history` and compute a window score (mean of the top 3 segments,
or `0.6*peak + 0.4*mean`). Write both `peak_score` and `window_score` to `moment.json`; grade on
`window_score`. The panel already has room to show the split.

### Q3. Tier thresholds and magic numbers are scattered

**Evidence:**

- `:1216-1217` hardcodes `>= 90` / `>= 72` in `fuse_multimodal_score`.
- `scripts/groq_clip_brain.py:70` reads `s_tier_min` / `a_tier_min` from
  `config/viral-style-bible.json`.
- `:1666` and `:1688` use ad-hoc `pre_score >= 65` to decide Groq captions.
- `:2446` defaults `auto_upload_min_score` to `90.0`.
- `LIVE_CLIPPER_WORKFLOW.md:73` documents **82 / 65**.
- `LiveClipperPanel.tsx:42` defaults the trigger threshold to `42`.

Five different numbers, one of which (the doc) is simply wrong. **Fix:** a single
`load_scoring_config()` (`scripts/groq_clip_brain._load_tier_thresholds` already does half of it)
feeding fusion, review, upload, and the UI. Add a `GET /api/clipper/config` so the panel can render
the real tier boundaries instead of hardcoded labels.

### Q4. Chat dominates the fusion and is platform-skewed

**Evidence:** `fuse_multimodal_score` (`:1065+`) — chat 0–55, audio 0–35, visual 0–32, ASR 0–40,
with synergy −12..+22. A visually spectacular fail (chair jump, ragdoll, explosion) with a quiet
chat cannot reach S-Tier. Auto-scout sessions started without a chat monitor are structurally
capped.

**Fix (medium effort):** normalize each signal as a z-score against a rolling session baseline
before weighting, so "loud for this stream" counts, not just "loud in absolute terms". Keep the raw
sub-scores in `moment.json` for explainability. Add `weights` to `config/clipper-signals.json`.

### Q5. Visual analyzer fails closed and silently

**Evidence:** `analyze_visual_motion` (`:831-930`) wraps everything in `except Exception: return empty`,
where `empty["score"] = 0.0`. One bad segment or an FFmpeg build without the PNG muxer removes up to
32 points for the rest of the session.

**Fix:** count consecutive failures; after 3, set a `degraded: ["visual"]` flag in state and surface
it in the panel. Distinguish "no motion detected" (score 0, legitimate) from "analyzer broken".

### Q6. The exported captions may come from a different transcript than the score

**Evidence:** `export_clip_package` re-extracts audio and re-transcribes via Groq for
`pre_score >= 65` (`:1666-1690`), while the trigger score was computed from the per-segment
`asr_manager.transcribe()` output. Two ASR passes, two chances to disagree; `transcript.json` can
therefore differ from the text that `moment.json` and `score_transcript_v2` saw.

**Fix:** when the exported window is contiguous with the analyzed segments, reuse the cached
segment transcripts (concatenate with offsets). Only fall back to a fresh Groq transcription when
smart-trim needs better word alignment, and record `transcript_source: "groq" | "segment"`.

---

## 4. P2 — Performance

| ID | Issue | Evidence | Fix |
|---|---|---|---|
| P1 | `export_clip_package` runs 5–7 sequential FFmpeg passes | `:1640-1930` (wav extract, probe, reaction peaks, render, loudnorm) | Reuse the wav already extracted for ASR; probe via `ffprobe` once and cache; already single-graph for render + loudnorm — keep it |
| P2 | `analyze_visual_motion` spawns an FFmpeg per segment at 1 fps | `:848-866` | Add `--fast-analyze` (0.5 fps, 96×54) and measure cost; or decode N segments in one pass |
| P3 | `/api/clipper/status` re-reads every `moment.json` and checklist every 2.5 s | `dashboard/app.py:193-277`, `list_live_clips:136-195`, poll interval `LiveClipperPanel.tsx:98` | Cache parsed JSON keyed by `(path, mtime, size)`; invalidate on write |
| P4 | Status payload grows with clip count; logs capped at 80 lines per session | `dashboard/app.py:215` | Add `?since=` / cursor for logs; paginate clips |

---

## 5. P3 — Dashboard & UX

| ID | Issue | Evidence |
|---|---|---|
| U1 | Header controls hardcode `max_clips: 8` and `duration_minutes: 60` — not editable although the engine supports both | `LiveClipperPanel.tsx:218-219` |
| U2 | Trigger threshold defaults to 42 while "strict" grading is 90/72 — the label doesn't tell the user what 42 will produce | `LiveClipperPanel.tsx:42` |
| U3 | No export progress: only a `stage: "EXPORTING_NVENC"` string, no per-stage or percent | `dashboard/app.py:2205-2216` state, `:2431` |
| U4 | No bulk actions (multi-select approve / delete / upload) and no keyboard shortcuts | gallery section, `LiveClipperPanel.tsx` |
| U5 | Errors collapse into one `err` string; logs are a truncated tail | `LiveClipperPanel.tsx:203-230`, `dashboard/app.py:215` |
| U6 | `synergy_reasons` exists in `moment.json` but is not shown — the "why this clip" story is invisible | `:1065+` writes it; panel doesn't render it |
| U7 | No cost/quota telemetry, though the Groq budget guard exists | `scripts/groq_clip_brain._acquire_groq_budget` |
| U8 | No "degraded mode" banner (visual analyzer down, chat disconnected, ASR falling back) | see Q5, C6 |

Small but high-value: **U5 + U8 together** remove most of the "it just stopped working" confusion.

---

## 6. P4 — Security

### S1. `Access-Control-Allow-Origin: *` on a mutating localhost API

**Evidence:** `dashboard/app.py:1002-1004` sets `*` for all responses, including
`/api/clipper/start`, `/api/clipper/delete`, `/api/clipper/approve`, `/api/clipper/upload`.
The server binds `127.0.0.1` (`:1680`), which blocks remote hosts but **not** a web page open in the
user's own browser: a cross-origin `POST` with `Content-Type: application/json` triggers a preflight,
which this server answers with `*` and `Content-Type` allowed → the request goes through.

That means any site the user visits can start a clipper session on an arbitrary URL, delete clips,
or trigger an upload. This is the highest-severity finding in the review.

**Fix:**

```python
ALLOWED_ORIGINS = {"http://localhost:3000", "http://127.0.0.1:3000"}
origin = self.headers.get("Origin")
if origin in ALLOWED_ORIGINS:
    self.send_header("Access-Control-Allow-Origin", origin)
    self.send_header("Vary", "Origin")
# reject mutating requests whose Origin is present and not allowlisted
```

Plus a per-session bearer token (`GET /api/session/token`, required by all `POST` routes) is the
belt-and-braces version.

### S2. Unvalidated `url` reaches `streamlink` / `yt-dlp`

**Evidence:** `/api/clipper/start` takes `url` from JSON and passes it to `resolve_stream_url`
(`:380-405`, subprocess argv). A `file://` path, a `--`-prefixed argument, or an internal
`http://169.254.169.254/...` URL is accepted.

**Fix:** parse with `urllib.parse`, allow only `twitch.tv` / `youtube.com` / `youtu.be` hosts (and
their subdomains), reject non-http(s) schemes, and never place the URL before `--` in argv.

### S3. Delete containment is correct — keep the pattern

**Evidence:** `dashboard/app.py:1571-1584` validates `channel`/`clip_id`, resolves the target, and
requires it to start with `LIVE_CLIPS_DIR` + separator. This is the right shape. Apply the same
`resolve()` + prefix check to `channel` in `/api/clipper/approve` and `/api/clipper/upload`
instead of only rejecting `/`, `\`, `..`.

---

## 7. P5 — Observability, tests, docs

### O1. No structured logging

**Evidence:** zero `logging` usage in `orchestration/live_clipper_agent.py` (only `print`), and
29 `except Exception` blocks — several of which discard the exception entirely (e.g. `:577-579`).

**Fix:** `logging` with a rotating per-session file (`exports/live-clips/<channel>/session.log`),
`log.exception` in every swallow path that represents a real failure, and a counters dict in state
(`segments_scored`, `export_failures`, `asr_fallbacks`, `chat_reconnects`).

### O2. No test suite

**Evidence:** no `tests/` directory; no `test_*.py` outside `.venv`.

Highest value per hour, in order:

1. **Window math** (C1) — pure function, table-driven, catches the worst bug in the system.
2. **`fuse_multimodal_score`** — bounds (0–100), monotonicity per signal, synergy clamped to
   `[-12, +22]`, tier thresholds from config.
3. **`score_transcript_v2`** — fixture transcripts: hook, question, profanity, pure-Hindi, empty.
4. **`sample_window_score`** — synthetic event timestamps → expected rate/z-score.
5. **`stitch_segments`** — assert argv contains the safety flags; assert fallback triggers on a
   corrupted fixture.
6. **Path containment** — `/api/clipper/delete` rejects `..`, absolute paths, symlink escape.
7. **One golden export** — 5 s synthetic clip, assert duration within ±0.3 s, audio stream exists,
   `moment.json` written.

### O3. Docs drift

`LIVE_CLIPPER_WORKFLOW.md:73` says S-Tier ≥ 82 / A-Tier ≥ 65; the code says 90 / 72. Update after
Q3 makes config the source of truth, and generate the table from config rather than hand-writing it.

---

## 8. Quick wins (≤ 1 hour each)

| Fix | Where | Why |
|---|---|---|
| Correct window math | `:2381`, `:2360`, `:2094` | Fixes missed reactions for every session |
| `try/except` per export job | `:2433` | Stops one bad clip from ending the stream |
| Tighten CORS + Origin check | `dashboard/app.py:1002` | Closes a real localhost attack |
| URL allowlist for `start` | `dashboard/app.py:380` | Same |
| Recompute and store `window_score` | `:2393` | Honest tiers without a redesign |
| IoU dedupe against pending clips | `:2375` | Kills duplicate exports |
| Log + surface `chat.connected` | `:546`, panel | Turns a silent 55-point loss into a visible warning |
| Expose `max_clips` / `duration_minutes` in UI | `LiveClipperPanel.tsx:218` | Engine already supports it |

## 9. Suggested sequence

1. **Stop the bleeding:** C1 (window math), C3 (error isolation), S1 (CORS), C2 (export queue).
2. **Make failures visible:** O1 (logging), C6 (chat status), Q5 (degraded visual), U5/U8.
3. **Quality:** Q1 (dedupe), Q2 (window score), Q3 (config single source), Q6 (transcript reuse).
4. **Polish:** P2 (status cache), U1–U7, O2 (tests), O3 (docs).

## 10. What is already solid

Worth stating so it doesn't get rewritten by accident:

- `fuse_multimodal_score` already matches the blueprint thresholds (90/72) — the drift is elsewhere.
- Delete-path containment (`:1571-1584`) is done correctly.
- Groq free-tier budgeting with disk caching (`scripts/groq_clip_brain.py`) is a genuinely good
  design for a zero-budget channel.
- Taste memory with Laplace smoothing (`scripts/clipper_taste_memory.py`) is the right shape for
  learning from approve/delete feedback.
- The approval gate before upload, and private-by-default uploads, match the workspace's Rule 4/5.
- `safe_floor` segment pruning (`:2549-2553`) already avoids deleting segments a pending job needs —
  the export-queue change just has to extend that guarantee to queued jobs.
