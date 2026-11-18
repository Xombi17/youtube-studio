#!/usr/bin/env python3
"""
Rebuild deleted Live Clipper clips from .ts ring-buffer segments.

The clipper writes 10-second TS segments into renders/live_buffer/<channel>_<date>_<time>/
and only prunes them after the buffer window rolls past. When a clip folder is deleted
(by hand or by the B-tier purge) the MP4 is gone, but the source segments often survive.

This script:
  1. Builds a recovery plan from the deletion manifest + dashboard delete events
     (config/clipper-taste-memory.json) and locates the surviving segments.
  2. With --render, re-stitches the original window [trigger-20s .. trigger+0s]
     and re-runs the real export_clip_package() pipeline (captions, -14 LUFS, NVENC).

Usage:
  python scripts/recover_live_clips.py                 # plan only, writes JSON
  python scripts/recover_live_clips.py --render         # render every recoverable clip
  python scripts/recover_live_clips.py --render --only <clip_id>
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

LIVE_BUFFER_DIR = ROOT / "renders" / "live_buffer"
EXPORTS_CLIPS_DIR = ROOT / "exports" / "live-clips"
MANIFEST = ROOT / "exports" / "live-clips-b-tier-deleted-20261118.json"
TASTE_MEMORY = ROOT / "config" / "clipper-taste-memory.json"
PLAN_PATH = ROOT / "exports" / "live-clips-recovery-plan.json"

SEG_SEC = 10.0
PRE_SEGS = 2   # chat-pre-pad 20s
MAX_CLIP_SEC = 30.0

CLIP_RE = re.compile(r"^(\d{8})_(\d{6})_(.+?)_(s|a|b)-tier_s(\d{4})$")


def tier_for(score: float | None) -> str:
    """Tier from the score, not from the (often stale) folder label."""
    if score is None:
        return "B-TIER"
    if score >= 90.0:
        return "S-TIER"
    if score >= 72.0:
        return "A-TIER"
    return "B-TIER"


def parse_clip_id(clip_id: str):
    m = CLIP_RE.match(clip_id)
    if not m:
        return None
    ts = dt.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    return {
        "clip_id": clip_id,
        "ts": ts,
        "channel": m.group(3),
        "tier_label": {"s": "S-TIER", "a": "A-TIER", "b": "B-TIER"}[m.group(4)],
        "trigger_idx": int(m.group(5)),
    }


def load_interrupted() -> dict[str, dict]:
    """Clips that were being exported when the clipper was stopped (no moment.json on disk)."""
    out: dict[str, dict] = {}
    for state_file in LIVE_BUFFER_DIR.glob("state_*.json"):
        try:
            st = json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        for entry in st.get("in_progress_clips") or []:
            cid = entry.get("clip_id")
            if not cid:
                continue
            # A live clipper that is still running owns this export — never race it.
            if st.get("running"):
                continue
            out[cid] = {
                "clip_id": cid,
                "score": entry.get("score"),
                "archetype": entry.get("archetype") or "",
                "tier_label": entry.get("tier") or "",
                "origin": "interrupted-export",
            }
    return out


def load_targets(since: dt.datetime | None) -> dict[str, dict]:
    """Union of the B-tier purge manifest and dashboard delete events."""
    targets: dict[str, dict] = {}

    if MANIFEST.exists():
        man = json.loads(MANIFEST.read_text(encoding="utf-8"))
        for row in man.get("deleted", []):
            cid = row.get("clip")
            if not cid:
                continue
            targets[cid] = {
                "clip_id": cid,
                "score": row.get("score"),
                "archetype": row.get("archetype") or "",
                "origin": "b-tier-purge",
            }

    if TASTE_MEMORY.exists():
        tm = json.loads(TASTE_MEMORY.read_text(encoding="utf-8"))
        for ev in tm.get("recent_events", []):
            if ev.get("decision") != "deleted":
                continue
            ts = dt.datetime.fromtimestamp(float(ev.get("ts") or 0))
            if since and ts < since:
                continue
            cid = ev.get("clip_id")
            if not cid:
                continue
            row = targets.setdefault(cid, {"clip_id": cid, "origin": "dashboard-delete"})
            row["score"] = ev.get("score", row.get("score"))
            row["archetype"] = ev.get("archetype") or row.get("archetype") or ""
            row["deleted_at"] = ts.isoformat(timespec="seconds")

    for clip_id, row in load_interrupted().items():
        targets.setdefault(clip_id, row)

    for clip_id, row in list(targets.items()):
        parsed = parse_clip_id(clip_id)
        if not parsed:
            row["status"] = "unparsed"
            continue
        row.update({k: parsed[k] for k in ("channel", "tier_label", "trigger_idx")})
        row["ts"] = parsed["ts"].isoformat(timespec="seconds")
        # Interrupted exports only matter while metadata is still missing.
        if row.get("origin") == "interrupted-export":
            if (EXPORTS_CLIPS_DIR / row["channel"] / clip_id / "moment.json").exists():
                targets.pop(clip_id)
    return targets


def index_sessions() -> dict[str, list[dict]]:
    """channel -> [{dir, segs: {idx: path}, mtimes: {idx: epoch}}]"""
    sessions: dict[str, list[dict]] = {}
    for d in sorted(LIVE_BUFFER_DIR.glob("*_2026*")):
        if not d.is_dir():
            continue
        m = re.match(r"^(.+)_\d{8}_\d{6}$", d.name)
        if not m:
            continue
        channel = m.group(1)
        segs, mtimes = {}, {}
        for f in d.glob("seg_*.ts"):
            mm = re.search(r"seg_(\d+)\.ts$", f.name)
            if not mm:
                continue
            idx = int(mm.group(1))
            segs[idx] = f
            mtimes[idx] = f.stat().st_mtime
        if segs:
            sessions.setdefault(channel, []).append({"dir": d, "segs": segs, "mtimes": mtimes})
    return sessions


def contiguous_run(segs: dict[int, Path], idx: int) -> tuple[int, int]:
    lo = hi = idx
    while lo - 1 in segs:
        lo -= 1
    while hi + 1 in segs:
        hi += 1
    return lo, hi


def choose_session(sessions: list[dict], clip: dict) -> dict | None:
    """Pick the session whose seg_<idx> was written just before this clip was exported."""
    if not sessions:
        return None
    ts_epoch = dt.datetime.fromisoformat(clip["ts"]).timestamp()
    idx = clip["trigger_idx"]
    best = None
    for s in sessions:
        if idx not in s["segs"]:
            continue
        lag = ts_epoch - s["mtimes"][idx]
        if lag < -15 or lag > 900:
            continue
        if best is None or lag < best[0]:
            best = (lag, s)
    return best[1] if best else None


def build_plan(since: dt.datetime | None) -> dict:
    targets = load_targets(since)
    sessions = index_sessions()
    entries = []
    for row in sorted(targets.values(), key=lambda r: r["clip_id"]):
        if row.get("status") == "unparsed":
            entries.append({**row, "status": "unparsed"})
            continue
        clip_id, channel, idx = row["clip_id"], row["channel"], row["trigger_idx"]
        sess = choose_session(sessions.get(channel, []), row)

        # Exact window already stitched on disk (survived a crash mid-export)?
        raw = None
        if sess:
            cand = sess["dir"] / f"{clip_id}_raw.ts"
            if cand.exists():
                raw = cand

        if not sess:
            entries.append({**row, "status": "no-segments"})
            continue

        lo, hi = contiguous_run(sess["segs"], idx)
        start = max(lo, idx - PRE_SEGS)
        end = min(hi, idx)
        # Keep the window meaningful even when the trigger sat at the live edge.
        while (end - start + 1) < 2 and start - 1 >= lo:
            start -= 1
        n = end - start + 1
        window = [sess["segs"][i] for i in range(start, end + 1)]

        if raw is not None:
            status = "ok(raw)"
        elif n >= 2:
            status = "ok(segments)"
        else:
            status = "insufficient"

        entries.append({
            **row,
            "session": sess["dir"].name,
            "start_idx": start,
            "end_idx": end,
            "n_segs": n,
            "window_sec": n * SEG_SEC,
            "raw_file": str(raw) if raw else None,
            "status": status,
        })

    summary = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "total_targets": len(entries),
        "recoverable": sum(1 for e in entries if e["status"].startswith("ok")),
        "unrecoverable": sum(1 for e in entries if not e["status"].startswith("ok")),
        "by_status": {},
        "entries": entries,
    }
    for e in entries:
        summary["by_status"][e["status"]] = summary["by_status"].get(e["status"], 0) + 1
    return summary


def render(plan: dict, only: str | None, max_clip_sec: float) -> int:
    from orchestration.live_clipper_agent import (
        ASRManager,
        detect_nvenc,
        export_clip_package,
        stitch_segments,
    )

    use_nvenc = detect_nvenc()
    asr = ASRManager(backend="whistle", language="en")
    print(f"[recover] NVENC={use_nvenc} ASR={asr.engine_label}", flush=True)

    rendered = failed = 0
    for entry in plan["entries"]:
        if not entry["status"].startswith("ok"):
            continue
        clip_id = entry["clip_id"]
        if only and clip_id != only:
            continue
        out_dir = EXPORTS_CLIPS_DIR / entry["channel"] / clip_id
        final_mp4 = out_dir / f"{clip_id}.mp4"
        if final_mp4.exists() and (out_dir / "moment.json").exists():
            print(f"[skip] {clip_id} already exists", flush=True)
            continue

        media = Path(entry["raw_file"]) if entry.get("raw_file") else None
        tmp_media = None
        try:
            if media is None:
                window = [
                    LIVE_BUFFER_DIR / entry["session"] / f"seg_{i:06d}.ts"
                    for i in range(entry["start_idx"], entry["end_idx"] + 1)
                ]
                window = [p for p in window if p.exists()]
                tmp_media = LIVE_BUFFER_DIR / entry["session"] / f"{clip_id}_recover_raw.ts"
                stitch_segments(window, tmp_media)
                media = tmp_media

            score = entry.get("score")
            moment_info = {
                "source": f"https://www.twitch.tv/{entry['channel'].replace('-gta6', '')}",
                "stream_offset_sec": entry["start_idx"] * SEG_SEC,
                "captured_at": entry["ts"],
                "pre_pad_used": (entry["trigger_idx"] - entry["start_idx"]) * SEG_SEC,
                "post_pad_used": (entry["end_idx"] - entry["trigger_idx"]) * SEG_SEC,
                "clip_id": clip_id,
                "recovered": True,
                "fusion": {
                    "total_score": float(score) if score is not None else 60.0,
                    "tier": tier_for(score),
                    "archetype": entry.get("archetype") or "RECOVERED MOMENT",
                    "trigger_source": "recovered_segments",
                    "synergy": 0.0,
                    "synergy_reasons": ["rebuilt from ring-buffer segments"],
                },
                "chat": {"score": 0.0},
                "audio": {"score": 0.0},
                "visual": {"score": 0.0},
                "transcript_score": {"score": 0.0},
            }

            print(
                f"[render] {clip_id}  score={entry.get('score')}  "
                f"segs={entry['start_idx']}..{entry['end_idx']} ({entry['n_segs']}x10s)",
                flush=True,
            )
            export_clip_package(
                media,
                moment_info["source"],
                entry["channel"],
                moment_info,
                out_dir,
                layout="split-blur",
                use_nvenc=use_nvenc,
                smart_trim=True,
                asr_manager=asr,
                facecam_pos="top-right",
                max_clip_sec=max_clip_sec,
                enable_punch_zoom=True,
                enable_sfx=True,
            )
            rendered += 1
            print(f"[done]  {clip_id}", flush=True)
        except Exception as exc:  # keep going; one bad clip must not kill the batch
            failed += 1
            print(f"[fail]  {clip_id}: {exc}", flush=True)
        finally:
            if tmp_media is not None:
                tmp_media.unlink(missing_ok=True)
            plan_path = PLAN_PATH
            plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    print(f"[recover] rendered={rendered} failed={failed}", flush=True)
    return 0 if failed == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Rebuild deleted live clips from TS segments")
    ap.add_argument("--render", action="store_true", help="Re-render every recoverable clip")
    ap.add_argument("--only", help="Render a single clip_id")
    ap.add_argument("--since", default="", help="Dashboard delete events since ISO time (default: all)")
    ap.add_argument("--max-clip-sec", type=float, default=MAX_CLIP_SEC)
    args = ap.parse_args()

    since = dt.datetime.fromisoformat(args.since) if args.since else None
    plan = build_plan(since)
    PLAN_PATH.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    print(f"targets     : {plan['total_targets']}")
    print(f"recoverable : {plan['recoverable']}")
    print(f"unrecoverable: {plan['unrecoverable']}")
    for status, count in sorted(plan["by_status"].items()):
        print(f"  {status:<16} {count}")
    print(f"plan        : {PLAN_PATH}")

    if args.render:
        return render(plan, args.only, args.max_clip_sec)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
