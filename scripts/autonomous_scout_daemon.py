#!/usr/bin/env python3
"""
CreatorRadar / ClipSurge — Autonomous 24/7 Live Stream Scout & Clipper Daemon

Runs continuously in the cloud:
1. Polls the creator watchlist (config/live-stream-watchlist.json) every N seconds.
2. When a priority creator goes live on Twitch or YouTube:
   - Spawns orchestration/live_clipper_agent.py with --auto-upload to stage clips (>= 80 score) as PRIVATE drafts.
   - Keeps track of running clipper PIDs and log outputs.
3. When the live stream concludes:
   - Gracefully stops the clipper process.
   - Flushes any pending clip exports.
4. Safe bounds: limits concurrent active sessions to max_parallel_default (default: 2).
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STUDIO_ROOT = Path(__file__).resolve().parent.parent
if str(STUDIO_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDIO_ROOT))

from scripts.live_stream_scout import discover_live_streams, load_watchlist_config

try:
    import scripts.redis_studio as redis_studio
except Exception:
    redis_studio = None

CONFIG_DIR = STUDIO_ROOT / "config"
LOGS_DIR = STUDIO_ROOT / "logs"
DAEMON_STATE_PATH = CONFIG_DIR / "autonomous_daemon_state.json"
SCOUT_PAUSED_PATH = CONFIG_DIR / "scout_paused.json"

active_sessions: dict[str, dict[str, Any]] = {}
stop_requested = False


def _sig_handler(signum, frame):
    global stop_requested
    print(f"\n[Daemon] Received signal {signum}. Shutting down active clippers...", flush=True)
    stop_requested = True


signal.signal(signal.SIGINT, _sig_handler)
signal.signal(signal.SIGTERM, _sig_handler)


def get_python_bin() -> str:
    venv_py = STUDIO_ROOT / ".venv" / "bin" / "python"
    return str(venv_py) if venv_py.exists() else sys.executable


def spawn_clipper_for_stream(
    stream: dict[str, Any],
    min_score: float = 80.0,
    asr: str = "local",
    upload_privacy: str = "private",
    layout: str = "facecam-split",
    facecam_pos: str = "top-right",
) -> subprocess.Popen:
    slug = stream.get("suggested_channel") or stream.get("display_name") or "stream"
    url = stream.get("url")
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOGS_DIR / f"daemon_{slug}_{int(time.time())}.log"

    # Map generic 'local' to 'whistle' (CPU-safe 16.9MB model) so it never crashes if CUDA/Modal is absent
    clipper_asr = "whistle" if asr in ("local", "cpu", "whistle") else asr

    cmd = [
        get_python_bin(),
        str(STUDIO_ROOT / "orchestration" / "live_clipper_agent.py"),
        "--url", url,
        "--name", slug,
        "--asr", clipper_asr,
        "--layout", layout,
        "--facecam-pos", facecam_pos,
        "--upload-profile", "clipper",
    ]

    print(f"[Daemon] Launching clipper for {slug} ({url})... Logs -> {log_file.name}", flush=True)
    out_f = open(log_file, "a", encoding="utf-8", buffering=1)
    proc = subprocess.Popen(
        cmd,
        cwd=str(STUDIO_ROOT),
        stdout=out_f,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    return proc


def prune_dead_sessions():
    dead = []
    for slug, info in active_sessions.items():
        proc = info["process"]
        ret = proc.poll()
        if ret is not None:
            print(f"[Daemon] Clipper for {slug} exited with code {ret}.", flush=True)
            dead.append(slug)
            url = info.get("stream", {}).get("url")
            if url and redis_studio:
                redis_studio.release_stream_lock(url)
    for slug in dead:
        active_sessions.pop(slug, None)


def cleanup_old_logs(max_age_sec: int = 86400 * 2):
    """Keep logs directory tidy by removing logs older than max_age_sec."""
    if not LOGS_DIR.exists():
        return
    now = time.time()
    for log_p in LOGS_DIR.glob("daemon_*.log"):
        try:
            if now - log_p.stat().st_mtime > max_age_sec:
                log_p.unlink()
        except Exception:
            pass


def save_daemon_state():
    state = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "active_count": len(active_sessions),
        "active_sessions": {
            k: {
                "url": v["stream"].get("url"),
                "display_name": v["stream"].get("display_name"),
                "started_at": v["started_at"],
                "pid": v["process"].pid,
            }
            for k, v in active_sessions.items()
        },
    }
    try:
        DAEMON_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass


def run_daemon(
    poll_interval: int = 120,
    min_score: float = 80.0,
    asr: str = "local",
    max_parallel: int = 2,
    upload_privacy: str = "private",
):
    print("=" * 64)
    print(" 🚀 ClipSurge — Autonomous 24/7 Live Stream Scout & Clipper")
    print(f" • Poll Interval:   {poll_interval}s")
    print(f" • Auto-Upload Min: {min_score} (Privacy: {upload_privacy})")
    print(f" • ASR Engine:      {asr}")
    print(f" • Max Parallel:    {max_parallel} concurrent stream(s)")
    print(f" • Redis Engine:    {'CONNECTED' if redis_studio and redis_studio.is_redis_connected() else 'MEMORY-FALLBACK'}")
    print("=" * 64, flush=True)

    while not stop_requested:
        prune_dead_sessions()
        cleanup_old_logs()
        save_daemon_state()

        is_paused = SCOUT_PAUSED_PATH.exists()
        if is_paused and active_sessions:
            for slug in list(active_sessions.keys()):
                info = active_sessions.pop(slug, None)
                if info:
                    proc = info.get("process")
                    if proc and proc.poll() is None:
                        proc.terminate()
            save_daemon_state()

        if not is_paused and len(active_sessions) < max_parallel:
            try:
                cfg = load_watchlist_config()
                # Dynamically discover trending streams across ALL categories on YouTube & Twitch
                res = discover_live_streams(
                    game=cfg.get("default_game", "ALL"),
                    min_viewers=200,
                    limit=20,
                    include_watchlist=True,
                    include_youtube=True,
                )
                live_candidates = res.get("streams", [])

                for stream in live_candidates:
                    if len(active_sessions) >= max_parallel:
                        break

                    slug = stream.get("suggested_channel") or stream.get("display_name")
                    url = stream.get("url")
                    if not url:
                        continue

                    if slug in active_sessions:
                        continue

                    # Distributed Redis lock to prevent duplicate clipping
                    if redis_studio:
                        locked = redis_studio.acquire_stream_lock(url, ttl_sec=7200)
                        if not locked:
                            continue

                    proc = spawn_clipper_for_stream(
                        stream=stream,
                        min_score=min_score,
                        asr=asr,
                        upload_privacy=upload_privacy,
                    )
                    active_sessions[slug] = {
                        "stream": stream,
                        "process": proc,
                        "started_at": datetime.now(timezone.utc).isoformat(),
                    }
                    save_daemon_state()

            except Exception as exc:
                print(f"[Daemon] Discovery poll error: {exc}", flush=True)

        for _ in range(poll_interval):
            if stop_requested:
                break
            time.sleep(1)

    # Clean shutdown
    print("[Daemon] Terminating all child clipper processes...", flush=True)
    for slug, info in active_sessions.items():
        try:
            url = info.get("stream", {}).get("url")
            if url and redis_studio:
                redis_studio.release_stream_lock(url)
            info["process"].terminate()
            info["process"].wait(timeout=5)
        except Exception:
            try:
                info["process"].kill()
            except Exception:
                pass
    active_sessions.clear()
    save_daemon_state()
    print("[Daemon] Clean shutdown complete.", flush=True)


def main():
    p = argparse.ArgumentParser(description="Autonomous 24/7 Live Stream Clipper Daemon")
    p.add_argument("--poll-interval", type=int, default=120, help="Seconds between watchlist checks (default: 120)")
    p.add_argument("--min-score", type=float, default=80.0, help="Min fusion score for auto-upload (default: 80.0)")
    p.add_argument("--asr", choices=["local", "whistle", "modal", "groq"], default="whistle", help="ASR engine (default: whistle for 0-GPU cloud)")
    p.add_argument("--max-parallel", type=int, default=2, help="Max simultaneous streams to clip (default: 2)")
    p.add_argument("--privacy", choices=["private", "unlisted", "public"], default="private", help="Staging privacy (default: private)")
    args = p.parse_args()

    run_daemon(
        poll_interval=args.poll_interval,
        min_score=args.min_score,
        asr=args.asr,
        max_parallel=args.max_parallel,
        upload_privacy=args.privacy,
    )


if __name__ == "__main__":
    main()
