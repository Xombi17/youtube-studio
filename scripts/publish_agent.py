#!/usr/bin/env python3
"""
ClipSurge — Publish Agent (select -> publish -> delete).

Pipeline contract:
  1. Clips scoring >= auto-upload-min-score are staged to YouTube as PRIVATE
     (see orchestration/live_clipper_agent.py) with their local package kept.
  2. This agent reviews every staged private Short with the simulated-human
     reviewer (scripts/human_clip_reviewer.py).
  3. verdict == POST  -> publish (private -> public), local package retained.
     verdict != POST  -> delete from YouTube AND remove the local package.

Publishing only happens inside the configured peak window so the channel never
dumps its whole backlog at 3 AM. Reviewing and rejecting run at any hour.

Safety rails:
  * A clip is NEVER deleted without a real verdict. If the local package is
    missing or the reviewer is unavailable the clip is left private and flagged.
  * dry_run mode reports every action without touching YouTube or disk.

Usage:
    .venv/bin/python scripts/publish_agent.py                 # scheduled pass
    .venv/bin/python scripts/publish_agent.py --dry-run       # report only
    .venv/bin/python scripts/publish_agent.py --publish-now   # ignore peak window
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import datetime, time as dtime, timezone
from pathlib import Path
from typing import Any

STUDIO_ROOT = Path(__file__).resolve().parent.parent
if str(STUDIO_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDIO_ROOT))

from scripts.youtube_uploader import (  # noqa: E402
    CONFIG_DIR,
    LIVE_CLIPS_DIR,
    YouTubeScopeError,
    delete_video,
    load_upload_history,
    set_video_privacy,
)

PUBLISH_CONFIG_PATH = CONFIG_DIR / "clipper-publish.json"
REPORT_PATH = CONFIG_DIR / "publish_agent_report.json"
PUBLISH_HISTORY_PATH = CONFIG_DIR / "publish_agent_history.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "dry_run": False,
    # How often the dashboard scheduler invokes a pass (seconds).
    "review_interval_sec": 300,
    # Local wall-clock window in which POST verdicts are allowed to go public.
    # Set both to null to publish as soon as a clip is reviewed.
    "peak_window": {"start": "19:00", "end": "22:00", "timezone": "Asia/Kolkata"},
    # Never publish a clip whose human_review.json is missing or inconclusive.
    "require_verdict": True,
    # Keep exports/live-clips/<channel>/<clip_id>/ after publishing (audit trail
    # + taste-memory input). Rejects always have their local package removed.
    "keep_local_after_publish": True,
    # Upper bound on publishes per pass, so a backlog cannot flood the channel.
    "max_publish_per_run": 4,
    # Upper bound on deletes per pass (cheap, but keep runaway loops bounded).
    "max_delete_per_run": 25,
    # Automatically purge orphaned uploads from YouTube if their local package was lost
    "clean_orphans": False,
}


def load_publish_config() -> dict[str, Any]:
    """Merge stored config over defaults (tolerates a missing/corrupt file)."""
    cfg = dict(DEFAULT_CONFIG)
    if PUBLISH_CONFIG_PATH.exists():
        try:
            stored = json.loads(PUBLISH_CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(stored, dict):
                cfg.update(stored)
        except Exception:
            pass
    return cfg


def save_publish_config(cfg: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    PUBLISH_CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def _parse_hhmm(value: Any) -> dtime | None:
    if not value:
        return None
    try:
        hh, mm = str(value).split(":", 1)
        return dtime(int(hh), int(mm))
    except Exception:
        return None


def in_peak_window(cfg: dict[str, Any], now: datetime | None = None) -> bool:
    """True when `now` falls inside the configured publish window (or none is set)."""
    win = cfg.get("peak_window") or {}
    start = _parse_hhmm(win.get("start"))
    end = _parse_hhmm(win.get("end"))
    if start is None or end is None:
        return True

    tz_name = str(win.get("timezone") or "UTC")
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc

    local = (now or datetime.now(timezone.utc)).astimezone(tz).time()
    if start <= end:
        return start <= local <= end
    # Window wraps midnight (e.g. 22:00 -> 02:00).
    return local >= start or local <= end


def local_clip_dir(rec: dict[str, Any]) -> Path | None:
    """Resolve the on-disk package for an upload receipt, if it still exists."""
    folder = rec.get("local_folder")
    if folder:
        p = Path(folder)
        if p.is_dir():
            return p

    channel = str(rec.get("clip_channel") or "").strip()
    source_id = str(rec.get("source_id") or "").strip()
    if not channel or not source_id:
        return None
    # Containment: never escape LIVE_CLIPS_DIR.
    cand = (LIVE_CLIPS_DIR / channel / source_id).resolve()
    root = LIVE_CLIPS_DIR.resolve()
    if not str(cand).startswith(str(root)):
        return None
    return cand if cand.is_dir() else None


def is_staged(rec: dict[str, Any]) -> bool:
    """A staged clip is private and not yet resolved by a previous pass."""
    if rec.get("publish_status") in ("published", "deleted", "failed"):
        return False
    if rec.get("privacy_status") != "private":
        return False
    # Skip anything that is already scheduled to self-publish.
    if rec.get("publish_at"):
        return False
    return bool(rec.get("video_id"))


def review_staged(rec: dict[str, Any], cfg: dict[str, Any]) -> tuple[str, dict[str, Any] | None, str]:
    """
    Returns (verdict, review_dict, note).
    verdict: 'POST' | 'MAYBE' | 'SKIP' | 'ORPHAN' | 'UNREVIEWED'
    'ORPHAN' = no local package to review; requires a manual human decision.
    """
    if not cfg.get("require_verdict", True):
        return "POST", None, "require_verdict disabled"

    clip_dir = local_clip_dir(rec)
    if clip_dir is None:
        # Legacy uploads ran with delete_clip_after_upload=True, so the MP4 is
        # already gone. Never guess here: an unreviewable clip stays private and
        # waits for an explicit human decision (see manual_decision).
        return "ORPHAN", None, "local package missing — cannot review, left private for manual decision"

    try:
        from scripts.human_clip_reviewer import review_clip_as_human

        rev = review_clip_as_human(clip_dir)
    except Exception as exc:
        return "UNREVIEWED", None, f"reviewer unavailable ({exc}) — left private"

    if not isinstance(rev, dict):
        return "UNREVIEWED", None, "reviewer returned no verdict — left private"

    verdict = str(rev.get("verdict") or "UNREVIEWED").upper()
    if verdict not in ("POST", "MAYBE", "SKIP"):
        verdict = "UNREVIEWED"
    return verdict, rev, str(rev.get("gut_reaction") or "")


def _patch_history(video_id: str, **fields: Any) -> None:
    """Persist a field change onto the matching upload receipt (atomic rewrite)."""
    hist = load_upload_history()
    for rec in hist:
        if rec.get("video_id") == video_id:
            rec.update(fields)
            break
    else:
        return
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    from scripts.youtube_uploader import UPLOAD_HISTORY_PATH

    tmp = UPLOAD_HISTORY_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(hist[:500], indent=2), encoding="utf-8")
    tmp.replace(UPLOAD_HISTORY_PATH)


def _append_event(event: dict[str, Any]) -> None:
    try:
        events: list[dict[str, Any]] = []
        if PUBLISH_HISTORY_PATH.exists():
            prev = json.loads(PUBLISH_HISTORY_PATH.read_text(encoding="utf-8"))
            if isinstance(prev, list):
                events = prev
        events.insert(0, event)
        PUBLISH_HISTORY_PATH.write_text(json.dumps(events[:500], indent=2), encoding="utf-8")
    except Exception:
        pass


def _is_not_found(exc: Exception) -> bool:
    status = getattr(getattr(exc, "resp", None), "status", None)
    body = str(getattr(exc, "content", "") or "")
    return status == 404 or "notFound" in body


def _delete_on_youtube(video_id: str, profile: str) -> str:
    """Delete a video, tolerating an already-removed upload. Returns a note."""
    try:
        delete_video(video_id, profile=profile)
        return "youtube delete ok"
    except YouTubeScopeError:
        raise
    except Exception as exc:
        if _is_not_found(exc):
            return "already absent on YouTube"
        raise


def _remove_local_package(rec: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    clip_dir = local_clip_dir(rec)
    if clip_dir is None:
        return {"removed": False, "reason": "already gone"}
    if dry_run:
        return {"removed": False, "path": str(clip_dir), "dry_run": True}
    try:
        shutil.rmtree(clip_dir, ignore_errors=True)
        return {"removed": not clip_dir.exists(), "path": str(clip_dir)}
    except Exception as exc:
        return {"removed": False, "path": str(clip_dir), "error": str(exc)}


def run_publish_agent(
    dry_run: bool | None = None,
    force_publish: bool = False,
    clean_orphans: bool | None = None,
    profile: str = "clipper",
    log=print,
) -> dict[str, Any]:
    """
    One select -> publish -> delete pass over every staged private Short.

    Returns a structured report; never raises for a single clip's failure.
    """
    cfg = load_publish_config()
    effective_dry = cfg.get("dry_run", False) if dry_run is None else bool(dry_run)
    window_open = in_peak_window(cfg) or force_publish
    do_clean_orphans = cfg.get("clean_orphans", False) if clean_orphans is None else bool(clean_orphans)

    staged = [r for r in load_upload_history() if is_staged(r)]
    staged.sort(key=lambda r: str(r.get("uploaded_at") or ""), reverse=True)

    report: dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": effective_dry,
        "peak_window_open": window_open,
        "staged_found": len(staged),
        "published": [],
        "rejected": [],
        "deferred": [],
        "orphaned": [],
        "errors": [],
    }

    if not cfg.get("enabled", True):
        report["note"] = "publish agent disabled in config/clipper-publish.json"
        log(f"[PublishAgent] disabled — {report['note']}")
        return report

    log(
        f"[PublishAgent] pass start — {len(staged)} staged private Short(s), "
        f"peak window {'OPEN' if window_open else 'closed'}"
        f"{' [DRY RUN]' if effective_dry else ''}"
    )

    published = 0
    rejected = 0

    for rec in staged:
        vid = str(rec.get("video_id") or "")
        title = str(rec.get("title") or vid)
        try:
            verdict, rev, note = review_staged(rec, cfg)

            if verdict == "ORPHAN":
                if do_clean_orphans:
                    if effective_dry:
                        log(f"  [DRY]   would clean ORPHAN video {title[:50]} from YouTube")
                        report["rejected"].append({"video_id": vid, "title": title, "verdict": "ORPHAN_CLEAN", "dry_run": True})
                    else:
                        log(f"  [ORPHAN-CLEAN] {title[:50]} — deleting lost-package video from YouTube")
                        try:
                            yt_note = _delete_on_youtube(vid, profile)
                            _patch_history(vid, publish_status="deleted", publish_note=f"orphan cleanup ({yt_note})")
                            report["rejected"].append({"video_id": vid, "title": title, "verdict": "ORPHAN_CLEAN"})
                            rejected += 1
                        except Exception as exc:
                            log(f"  [ORPHAN-ERR] Failed to delete {vid}: {exc}")
                    continue

                report["orphaned"].append(
                    {"video_id": vid, "title": title, "note": note, "local_folder": rec.get("local_folder")}
                )
                if rec.get("publish_status") not in ("orphaned", "kept_private"):
                    _patch_history(vid, publish_status="orphaned", publish_note=note)
                log(f"  [ORPHAN] {title[:57]} — needs manual decision (no local package)")
                continue

            if verdict == "UNREVIEWED":
                report["deferred"].append({"video_id": vid, "title": title, "note": note})
                _patch_history(vid, publish_status="unreviewed", publish_note=note)
                log(f"  [defer] {title[:58]} — {note}")
                continue

            if verdict == "POST":
                if not window_open:
                    report["deferred"].append(
                        {"video_id": vid, "title": title, "note": "POST but peak window closed"}
                    )
                    _patch_history(vid, publish_status="reviewed_pending_window")
                    log(f"  [hold]  {title[:58]} — POST, waiting for peak window")
                    continue
                if published >= int(cfg.get("max_publish_per_run", 4)):
                    report["deferred"].append(
                        {"video_id": vid, "title": title, "note": "max_publish_per_run reached"}
                    )
                    _patch_history(vid, publish_status="reviewed_pending_window")
                    continue

                if effective_dry:
                    log(f"  [DRY]   would PUBLISH {title[:58]} ({(rev or {}).get('human_score')}/100)")
                    report["published"].append({"video_id": vid, "title": title, "dry_run": True})
                    published += 1
                    continue

                set_video_privacy(vid, "public", profile=profile)
                published += 1
                _patch_history(
                    vid,
                    publish_status="published",
                    privacy_status="public",
                    published_at=datetime.now(timezone.utc).isoformat(),
                    human_review=rev,
                )
                report["published"].append(
                    {
                        "video_id": vid,
                        "title": title,
                        "human_score": (rev or {}).get("human_score"),
                        "gut_reaction": (rev or {}).get("gut_reaction"),
                    }
                )
                _append_event(
                    {
                        "at": datetime.now(timezone.utc).isoformat(),
                        "action": "publish",
                        "video_id": vid,
                        "title": title,
                        "human_score": (rev or {}).get("human_score"),
                    }
                )
                log(
                    f"  [PUB]   {title[:58]} -> public "
                    f"({(rev or {}).get('human_score')}/100)"
                )
                continue

            # MAYBE / SKIP -> reject: delete from YouTube and drop the local package.
            if rejected >= int(cfg.get("max_delete_per_run", 25)):
                report["deferred"].append({"video_id": vid, "title": title, "note": "max_delete_per_run reached"})
                continue

            if effective_dry:
                log(f"  [DRY]   would DELETE {title[:58]} (verdict={verdict})")
                report["rejected"].append({"video_id": vid, "title": title, "verdict": verdict, "dry_run": True})
                rejected += 1
                continue

            yt_note = "youtube delete ok"
            try:
                yt_note = _delete_on_youtube(vid, profile)
            except YouTubeScopeError:
                raise
            except Exception as exc:
                yt_note = f"youtube delete failed: {exc}"
                report["errors"].append({"video_id": vid, "error": yt_note})
                # Still drop the local package? No — keep it so the clip can be
                # retried; a half-deleted state must not lose the evidence.
                _patch_history(vid, publish_status="failed", publish_note=yt_note)
                log(f"  [ERR]   {title[:58]} — {yt_note}")
                continue

            local = _remove_local_package(rec, dry_run=False)
            rejected += 1
            _patch_history(
                vid,
                publish_status="deleted",
                publish_note=f"verdict={verdict}",
                local_clip_deleted=bool(local.get("removed")),
                human_review=rev,
            )
            report["rejected"].append(
                {
                    "video_id": vid,
                    "title": title,
                    "verdict": verdict,
                    "human_score": (rev or {}).get("human_score"),
                    "gut_reaction": (rev or {}).get("gut_reaction"),
                    "local_removed": bool(local.get("removed")),
                }
            )
            _append_event(
                {
                    "at": datetime.now(timezone.utc).isoformat(),
                    "action": "delete",
                    "video_id": vid,
                    "title": title,
                    "verdict": verdict,
                    "human_score": (rev or {}).get("human_score"),
                }
            )
            log(f"  [DEL]   {title[:58]} — {verdict} "
                f"({(rev or {}).get('human_score')}/100), local {'removed' if local.get('removed') else 'kept'}")

        except YouTubeScopeError as exc:
            report["errors"].append({"video_id": vid, "error": str(exc)})
            log(f"  [SCOPE] {title[:58]} — {exc}")
            break  # every later call will fail the same way; stop wasting quota
        except Exception as exc:
            report["errors"].append({"video_id": vid, "error": str(exc)})
            log(f"  [ERR]   {title[:58]} — {exc}")

    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["counts"] = {
        "staged": len(staged),
        "published": len(report["published"]),
        "rejected": len(report["rejected"]),
        "deferred": len(report["deferred"]),
        "orphaned": len(report["orphaned"]),
        "errors": len(report["errors"]),
    }

    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    except Exception:
        pass

    c = report["counts"]
    log(
        f"[PublishAgent] pass done — published {c['published']}, rejected {c['rejected']}, "
        f"deferred {c['deferred']}, orphaned {c['orphaned']}, errors {c['errors']}"
    )
    return report


def manual_decision(
    video_id: str,
    action: str,
    profile: str = "clipper",
    log=print,
) -> dict[str, Any]:
    """
    Explicit human resolution for a staged clip the agent could not decide
    (typically an orphan with no local package).

    action: 'publish' (private -> public), 'delete' (YouTube + local package),
            'keep' (leave private, defer back to the agent).
    """
    action = str(action or "").strip().lower()
    if action not in ("publish", "delete", "keep"):
        raise ValueError(f"unknown action: {action!r} (expected publish|delete|keep)")

    hist = load_upload_history()
    rec = next((r for r in hist if r.get("video_id") == video_id), None)
    if rec is None:
        return {"error": f"video {video_id} not in upload history", "status": "NOT_FOUND"}
    if not is_staged(rec):
        return {"error": f"video {video_id} is not staged", "status": "NOT_STAGED"}

    title = str(rec.get("title") or video_id)
    if action == "keep":
        _patch_history(video_id, publish_status="kept_private", publish_note="manual: keep private")
        log(f"[PublishAgent] manual KEEP {title[:58]} — stays private")
        return {"status": "OK", "action": "keep", "video_id": video_id}

    if action == "publish":
        set_video_privacy(video_id, "public", profile=profile)
        _patch_history(
            video_id,
            publish_status="published",
            privacy_status="public",
            published_at=datetime.now(timezone.utc).isoformat(),
            publish_note="manual publish",
        )
        _append_event(
            {
                "at": datetime.now(timezone.utc).isoformat(),
                "action": "publish",
                "video_id": video_id,
                "title": title,
                "manual": True,
            }
        )
        log(f"[PublishAgent] manual PUBLISH {title[:58]} -> public")
        return {"status": "OK", "action": "publish", "video_id": video_id}

    yt_note = _delete_on_youtube(video_id, profile)
    local = _remove_local_package(rec, dry_run=False)
    _patch_history(
        video_id,
        publish_status="deleted",
        publish_note=f"manual delete ({yt_note})",
        local_clip_deleted=bool(local.get("removed")),
    )
    _append_event(
        {
            "at": datetime.now(timezone.utc).isoformat(),
            "action": "delete",
            "video_id": video_id,
            "title": title,
            "manual": True,
            "note": yt_note,
        }
    )
    log(f"[PublishAgent] manual DELETE {title[:58]} — {yt_note}")
    return {"status": "OK", "action": "delete", "video_id": video_id, "note": yt_note}


def check_and_clean_disk(min_free_gb: float = 3.0, log=print) -> dict[str, Any]:
    """Check disk usage and safely remove stale intermediate chunks if storage is low."""
    total, used, free = shutil.disk_usage(STUDIO_ROOT)
    free_gb = free / (1024 ** 3)
    cleaned_bytes = 0

    if free_gb < min_free_gb:
        log(f"[PublishAgent:DiskGuard] Low disk warning: {free_gb:.1f} GB free (threshold: {min_free_gb:.1f} GB). Cleaning temp buffers...")
        # 1. Clean old .ts chunks from renders/ and /tmp
        for scan_dir in [STUDIO_ROOT / "renders", Path("/tmp")]:
            if not scan_dir.exists():
                continue
            for p in scan_dir.glob("*.ts"):
                try:
                    if time.time() - p.stat().st_mtime > 1800:
                        cleaned_bytes += p.stat().st_size
                        p.unlink()
                except Exception:
                    pass

        log(f"[PublishAgent:DiskGuard] Cleaned {cleaned_bytes / (1024**2):.1f} MB.")

    return {"free_gb": round(free_gb, 2), "cleaned_bytes": cleaned_bytes}


def run_publish_daemon(
    interval_sec: int = 300,
    dry_run: bool = False,
    force_publish: bool = False,
    clean_orphans: bool = False,
    profile: str = "clipper",
    log=print,
) -> None:
    """Continuous 24/7 autonomous publisher loop with Redis queue support & disk guard."""
    import signal

    stop_event = threading.Event()

    def _on_signal(sig, frame):
        log(f"\n[PublishAgent] Received signal {sig}. Terminating publisher daemon cleanly...")
        stop_event.set()

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    log("=" * 64)
    log(" 🚀 ClipSurge — Autonomous 24/7 Video Publisher & Lifecycle Agent")
    log(f" • Review Interval: {interval_sec}s")
    log(f" • Profile:         {profile}")
    log(f" • Clean Orphans:   {clean_orphans}")
    log(f" • Dry Run:         {dry_run}")
    log("=" * 64)

    # Try importing redis engine
    redis_mod = None
    try:
        import scripts.redis_studio as redis_mod
    except Exception:
        try:
            import redis_studio as redis_mod
        except Exception:
            pass

    last_pass_time = 0.0

    while not stop_event.is_set():
        now = time.time()
        should_run_pass = (now - last_pass_time) >= interval_sec

        # Check if immediate publish job arrived in Redis queue
        job = None
        if redis_mod:
            try:
                job = redis_mod.pop_publish_job(timeout=1)
            except Exception:
                pass

        if job:
            log(f"[PublishAgent] Received immediate publish job from Redis: {job.get('title') or job.get('video_id')}")
            should_run_pass = True

        if should_run_pass:
            last_pass_time = now
            try:
                check_and_clean_disk(min_free_gb=3.0, log=log)
                run_publish_agent(
                    dry_run=dry_run,
                    force_publish=force_publish,
                    clean_orphans=clean_orphans,
                    profile=profile,
                    log=log,
                )
            except Exception as exc:
                log(f"[PublishAgent] Pass error: {exc}")

        # Sleep responsive to signals
        for _ in range(max(1, min(10, interval_sec))):
            if stop_event.is_set():
                break
            time.sleep(1.0)

    log("[PublishAgent] Publisher daemon shutdown complete.")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="ClipSurge publish agent (select -> publish -> delete)")
    p.add_argument("--dry-run", action="store_true", help="Report actions without touching YouTube or disk")
    p.add_argument("--publish-now", action="store_true", help="Ignore the peak window for this pass")
    p.add_argument("--clean-orphans", action="store_true", help="Purge orphaned videos without local package")
    p.add_argument("--daemon", action="store_true", help="Run continuously as a 24/7 background daemon")
    p.add_argument("--interval", type=int, default=300, help="Daemon review pass interval in seconds (default: 300)")
    p.add_argument("--profile", default="clipper", help="YouTube profile (default: clipper)")
    p.add_argument("--status", action="store_true", help="Print staged clips and exit")
    args = p.parse_args(argv)

    if args.status:
        staged = [r for r in load_upload_history() if is_staged(r)]
        print(f"staged private clips: {len(staged)}")
        for r in staged:
            print(f"  {r.get('video_id')}  {r.get('privacy_status')}  {str(r.get('title'))[:70]}")
        return 0

    if args.daemon:
        run_publish_daemon(
            interval_sec=args.interval,
            dry_run=args.dry_run,
            force_publish=args.publish_now,
            clean_orphans=True if args.clean_orphans else None,
            profile=args.profile,
        )
        return 0

    run_publish_agent(
        dry_run=True if args.dry_run else None,
        force_publish=args.publish_now,
        clean_orphans=True if args.clean_orphans else None,
        profile=args.profile,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
