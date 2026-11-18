#!/usr/bin/env python3
"""Move already-rendered sub-gate clips out of exports/live-clips.

Nothing is deleted: folders are moved to exports/live-clips-quarantine/
and appended to its index.jsonl, so a mis-scored clip can be restored.

Usage:
  python scripts/quarantine_b_tier.py --dry-run
  python scripts/quarantine_b_tier.py --gate 72
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from orchestration.live_clipper_agent import EXPORTS_CLIPS_DIR, quarantine_clip  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Quarantine clips below the A-tier export gate")
    ap.add_argument("--gate", type=float, default=72.0, help="Minimum score to keep (default: 72)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    moved = kept = skipped = 0
    for clip_dir in sorted(p for p in EXPORTS_CLIPS_DIR.glob("*/*") if p.is_dir()):
        moment = clip_dir / "moment.json"
        if not moment.exists():
            skipped += 1
            print(f"[skip] {clip_dir.name}  (no moment.json — may still be rendering)")
            continue
        try:
            fusion = json.loads(moment.read_text(encoding="utf-8")).get("fusion") or {}
            score = float(fusion.get("total_score") or 0.0)
            tier = str(fusion.get("tier") or "?")
        except Exception as exc:
            skipped += 1
            print(f"[skip] {clip_dir.name}  (unreadable moment.json: {exc})")
            continue

        if score >= args.gate:
            kept += 1
            print(f"[keep] {score:5.1f} {tier:<6} {clip_dir.name}")
            continue

        if args.dry_run:
            moved += 1
            print(f"[would-move] {score:5.1f} {tier:<6} {clip_dir.name}")
            continue

        dest = quarantine_clip(clip_dir, f"existing clip below gate {args.gate:.1f}", score)
        if dest:
            moved += 1
            print(f"[moved] {score:5.1f} {tier:<6} {clip_dir.name} -> {dest}")
        else:
            skipped += 1

    print(f"\nkept={kept} moved={moved} skipped={skipped} gate={args.gate}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
