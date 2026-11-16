#!/usr/bin/env python3
"""
CreatorRadar Dashboard CLI
Tracks trends, content ideas queue, pipeline production status,
and YouTube monetization milestones.
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime

STUDIO_ROOT = Path(__file__).resolve().parent.parent

def print_header(title):
    print("\n" + "=" * 64)
    print(f"  CREATORRADAR :: {title.upper()}")
    print("=" * 64)

def show_monetization_status():
    print_header("Channel Monetization Progress")
    subscribers = 11000
    sub_goal = 1000
    watch_hours_goal = 4000
    shorts_views_goal = 10_000_000

    print(f"• Current Subscribers: {subscribers:,} / {sub_goal:,}  [PASS: 1,100% of goal!]")
    print(f"• Long-Form Watch Hours (12 mo): [Tracking via YouTube Studio] / {watch_hours_goal:,} hrs")
    print(f"• Shorts Views (90 days):        [Tracking via YouTube Studio] / {shorts_views_goal:,} views")
    print("\nStatus: YPP Subscriber Threshold Met. Focus on Shorts velocity & watch time retention.")

def show_ideas_queue():
    print_header("Active Production & Ideas Queue")
    queue_file = STUDIO_ROOT / "dashboard" / "ideas-queue.md"
    if not queue_file.exists():
        print("Ideas queue file not found.")
        return

    with open(queue_file, "r") as f:
        lines = f.readlines()

    in_table = False
    for line in lines:
        if line.strip().startswith("| ID |"):
            in_table = True
            print("-" * 64)
        if in_table and line.strip().startswith("| GTA-"):
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if len(parts) >= 8:
                id_, topic, category, fmt, hook, r_stat, s_stat, p_stat = parts[:8]
                print(f"[{id_}] {topic[:38]:<38} | {category[:15]} | R:{r_stat} S:{s_stat} P:{p_stat}")
    print("-" * 64)

def show_gta6_facts():
    print_header("GTA VI Verified Knowledge Base")
    facts_file = STUDIO_ROOT / "config" / "gta6-sources.md"
    if facts_file.exists():
        with open(facts_file, "r") as f:
            for line in f:
                if line.startswith("|") and ("Launch Date" in line or "Storage" in line or "Preload" in line or "Standard" in line):
                    print(line.strip())
    else:
        print("Verified facts registry in config/gta6-sources.md")

def show_pipeline_health():
    print_header("Studio System Audit & Skills")
    skills_dir = STUDIO_ROOT / "skills"
    if skills_dir.exists():
        skills = sorted([d.name for d in skills_dir.iterdir() if (d / "SKILL.md").exists()])
        print(f"Total Local Skills Active: {len(skills)}")
        for i, s in enumerate(skills, 1):
            print(f"  {i:2d}. {s}")
    
    # Check renders and exports
    exports_dir = STUDIO_ROOT / "exports"
    if exports_dir.exists():
        topics = [d.name for d in exports_dir.iterdir() if d.is_dir()]
        print(f"\nCompleted / Staged Topic Packages: {len(topics)}")
        for t in topics:
            has_meta = (exports_dir / t / "metadata.md").exists()
            has_chk = (exports_dir / t / "checklist.md").exists()
            mp4s = list((exports_dir / t).glob("*.mp4"))
            status_str = f"Meta: {'✓' if has_meta else '✗'}, Checklist: {'✓' if has_chk else '✗'}, Video: {'✓' if mp4s else 'Pending'}"
            print(f"  • {t:<22} [{status_str}]")

def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd in ("queue", "ideas"):
            show_ideas_queue()
        elif cmd in ("ypp", "monetization"):
            show_monetization_status()
        elif cmd in ("facts", "gta6"):
            show_gta6_facts()
        elif cmd in ("skills", "health"):
            show_pipeline_health()
        else:
            print("Usage: python3 dashboard/radar.py [queue|monetization|facts|skills]")
        return

    # Default full display
    show_pipeline_health()
    show_monetization_status()
    show_ideas_queue()
    show_gta6_facts()
    print("\nCreatorRadar Dashboard ready. Run with specific flags or view dashboard/README.md.")

if __name__ == "__main__":
    main()
