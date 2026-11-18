#!/usr/bin/env python3
"""
CreatorRadar Studio Engine API Server
Backend API powering the Next.js Studio UI (dashboard-next) on port 8080:
- Live system telemetry (GPU, NVENC, VoiceStudio health, 31 skills, 120 styles)
- Ideas queue reader & writer (dashboard/ideas-queue.md)
- Full 120-style catalog API (Claude Video 2.0 + Lemo-Opuscar)
- Topic-agnostic render job runner streaming real pipeline logs
- Exports & QA review browser + human-approval checklist sign-off (Rule 4)
- In-browser microphone voice enrollment + VoiceStudio preview synthesis
- Live Creator Tools (hookscore.py + title.py linters)
- HTTP Range media streaming for smooth HTML5 video playback & scrubbing
"""

import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = STUDIO_ROOT / "scripts"
VOICE_DIR = STUDIO_ROOT / "assets" / "voices"
EXPORTS_DIR = STUDIO_ROOT / "exports"
RENDERS_DIR = STUDIO_ROOT / "renders"
SKILLS_DIR = STUDIO_ROOT / "skills"
QUEUE_FILE = STUDIO_ROOT / "dashboard" / "ideas-queue.md"
PORT = int(os.environ.get("STUDIO_API_PORT", "8080"))

VOICE_DIR.mkdir(parents=True, exist_ok=True)
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
RENDERS_DIR.mkdir(parents=True, exist_ok=True)

if str(STUDIO_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDIO_ROOT))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from render_scene import detect_nvenc  # noqa: E402
from select_style import list_all_styles  # noqa: E402
from voice_studio_client import (  # noqa: E402
    DEFAULT_EDGE_VOICE,
    DEFAULT_PROFILE_ID,
    VOICE_STUDIO_URL,
    generate_narration,
    is_voicestudio_running,
    list_voicestudio_profiles,
)
from clipper_taste_memory import (  # noqa: E402
    get_taste_memory_summary,
    record_clip_feedback,
)
from groq_clip_brain import (  # noqa: E402
    get_groq_usage_summary,
    get_naga_usage_summary,
    groq_batch_review_clips,
    read_cached_groq_review,
)
from human_clip_reviewer import (  # noqa: E402
    AUTO_REVIEW_TIERS,
    read_cached_human_review,
    review_clip_as_human,
)
from live_stream_scout import (  # noqa: E402
    discover_live_streams,
    load_watchlist_config,
)
from youtube_uploader import (  # noqa: E402
    PROFILE_LABELS,
    build_oauth_url,
    build_upload_metadata,
    complete_oauth_callback,
    disconnect_youtube,
    get_youtube_status,
    load_upload_history,
    normalize_profile,
    read_upload_receipt,
    save_client_secret,
    upload_video,
)

ACTIVE_JOBS: dict[str, dict] = {}
ACTIVE_UPLOADS: dict[str, dict] = {}
UPLOAD_LOCK = threading.Lock()
LOG_BUFFER: list[str] = []
LOG_LOCK = threading.Lock()
STYLE_CACHE: list[dict] | None = None
HW_INFO_CACHE: dict | None = None

LIVE_CLIPS_DIR = EXPORTS_DIR / "live-clips"
# Dashboard "delete" is a trash move, never rmtree: the folder is hidden from the reel list but
# stays recoverable if the click was a mistake.
DELETED_CLIPS_DIR = EXPORTS_DIR / "live-clips-deleted"
LIVE_BUFFER_DIR = RENDERS_DIR / "live_buffer"
LIVE_STATE_FILE = LIVE_BUFFER_DIR / "live_clipper_state.json"
CLIPPER_SESSIONS: dict[str, dict] = {}
CLIPPER_LOGS: list[str] = []
CLIPPER_LOCK = threading.Lock()


def _kill_proc_tree(proc: subprocess.Popen | None, pid: int | None = None):
    if proc is not None and proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), 15)
        except Exception:
            proc.terminate()
        try:
            proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), 9)
            except Exception:
                proc.kill()
    elif pid and _pid_alive(pid):
        try:
            os.killpg(os.getpgid(pid), 15)
        except Exception:
            try:
                os.kill(pid, 15)
            except OSError:
                pass


def _pid_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def list_live_clips() -> list[dict]:
    if not LIVE_CLIPS_DIR.exists():
        return []
    clips: list[dict] = []
    for channel_dir in sorted(LIVE_CLIPS_DIR.iterdir()):
        if not channel_dir.is_dir():
            continue
        for clip_dir in sorted(channel_dir.iterdir(), reverse=True):
            if not clip_dir.is_dir():
                continue
            mp4s = sorted(clip_dir.glob("*.mp4"))
            if not mp4s:
                continue
            mp4 = mp4s[0]
            moment_path = clip_dir / "moment.json"
            meta_path = clip_dir / "metadata.md"
            check_path = clip_dir / "checklist.md"
            moment = {}
            if moment_path.exists():
                try:
                    moment = json.loads(moment_path.read_text(encoding="utf-8"))
                except Exception:
                    moment = {}
            checklist_md = check_path.read_text(encoding="utf-8") if check_path.exists() else ""
            human_approved = bool(checklist_md) and ("- [ ]" not in checklist_md) and ("- [x]" in checklist_md.lower())
            fusion = moment.get("fusion") or {}
            human_review = read_cached_human_review(clip_dir) or moment.get("human_review")
            clips.append({
                "clip_id": clip_dir.name,
                "channel": channel_dir.name,
                "video_url": f"/media/exports/live-clips/{channel_dir.name}/{clip_dir.name}/{mp4.name}",
                "size_mb": round(mp4.stat().st_size / (1024 * 1024), 2),
                "mtime": mp4.stat().st_mtime,
                "captured_at": moment.get("captured_at") or "",
                "total_score": fusion.get("total_score", moment.get("total_score", 0)),
                "tier": fusion.get("tier", "B-TIER"),
                "archetype": fusion.get("archetype", "LIVE CLIP"),
                "trigger_source": fusion.get("trigger_source", "audio_speech"),
                "synergy": fusion.get("synergy", 0),
                "synergy_reasons": fusion.get("synergy_reasons", []),
                "pre_pad_used": moment.get("pre_pad_used", 0),
                "post_pad_used": moment.get("post_pad_used", 0),
                "smart_trim_offset_sec": moment.get("smart_trim_offset_sec", 0),
                "transcript": moment.get("transcript", ""),
                "audio": moment.get("audio", {}),
                "chat": moment.get("chat", {}),
                "visual": moment.get("visual", {}),
                "transcript_score": moment.get("transcript_score", {}),
                "metadata_md": meta_path.read_text(encoding="utf-8") if meta_path.exists() else "",
                "checklist_md": checklist_md,
                "human_approved": human_approved,
                "human_review": human_review,
                "needs_human_review": bool(
                    not human_review and str(fusion.get("tier") or "").upper() in AUTO_REVIEW_TIERS
                ),
                "youtube_upload": read_upload_receipt(clip_dir),
            })
    clips.sort(key=lambda c: c["mtime"], reverse=True)
    return clips


def get_live_clipper_status() -> dict:
    sessions_out: list[dict] = []
    seen_channels: set[str] = set()

    state_files = sorted(LIVE_BUFFER_DIR.glob("state_*.json"), key=lambda p: p.stat().st_mtime, reverse=True) if LIVE_BUFFER_DIR.exists() else []
    for sf_path in state_files:
        try:
            st = json.loads(sf_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        ch = st.get("channel") or sf_path.stem.replace("state_", "")
        seen_channels.add(ch)
        # Report the trigger actually in force: the clipper clamps --threshold up to the
        # export gate, so an old state file's lower number must not be shown as the live line.
        _gate = float(st.get("min_export_score") or 72.0)
        if _gate > 0 and float(st.get("threshold") or 0) < _gate:
            st["threshold"] = _gate
        sess = CLIPPER_SESSIONS.get(ch)
        proc = sess.get("proc") if sess else None
        proc_alive = proc is not None and proc.poll() is None
        is_running = proc_alive or (bool(st.get("running")) and _pid_alive(st.get("pid")))
        st["running"] = is_running
        if not is_running and st.get("status") not in ("STOPPED", None):
            st["status"] = "STOPPED"
            st["in_progress_clips"] = []
        sess_logs = list(sess.get("logs", [])[-80:]) if sess else []
        sessions_out.append({
            "channel": ch,
            "running": is_running,
            "state": st,
            "logs": sess_logs,
        })

    for ch, sess in list(CLIPPER_SESSIONS.items()):
        if ch in seen_channels:
            continue
        proc = sess.get("proc")
        is_running = proc is not None and proc.poll() is None
        sessions_out.insert(0, {
            "channel": ch,
            "running": is_running,
            "state": {
                "running": is_running,
                "status": "STARTING" if is_running else "STOPPED",
                "pid": proc.pid if proc else None,
                "url": sess.get("url", ""),
                "platform": "stream",
                "channel": ch,
                "segments_scanned": 0,
                "clips_completed": 0,
                "in_progress_clips": [],
                "latest_segment": None,
                "history": [],
                "threshold": sess.get("threshold", 72),
                "min_export_score": sess.get("min_export_score", 72.0),
                "chat_pre_pad": sess.get("chat_pre_pad", 30),
                "post_pad": sess.get("post_pad", 12),
                "layout": sess.get("layout", "facecam-split"),
            },
            "logs": list(sess.get("logs", [])[-80:]),
        })

    sessions_out.sort(key=lambda s: (not s["running"], -(s["state"].get("updated_at") or 0)))

    primary = sessions_out[0] if sessions_out else None
    any_running = any(s["running"] for s in sessions_out)
    total_in_prog = sum(len(s["state"].get("in_progress_clips", [])) for s in sessions_out if s["running"])

    with CLIPPER_LOCK:
        logs_tail = list(CLIPPER_LOGS[-100:])
    if not logs_tail and primary:
        logs_tail = primary.get("logs", [])

    clips = list_live_clips()
    return {
        "running": any_running,
        "running_count": sum(1 for s in sessions_out if s["running"]),
        "sessions": sessions_out,
        "state": primary["state"] if primary else None,
        "in_progress_count": total_in_prog,
        "clips_count": len(clips),
        "clips": clips,
        "logs": logs_tail,
        "taste_memory": get_taste_memory_summary(),
        "auto_scout": get_auto_scout_snapshot(),
        "groq_usage": get_groq_usage_summary(),
        "naga_usage": get_naga_usage_summary(),
    }


def stop_live_clipper(channel: str | None = None) -> dict:
    stopped_channels: list[str] = []
    targets = [slugify(channel)] if channel else list(CLIPPER_SESSIONS.keys())

    if LIVE_BUFFER_DIR.exists():
        for sf_path in LIVE_BUFFER_DIR.glob("state_*.json"):
            try:
                st = json.loads(sf_path.read_text(encoding="utf-8"))
                ch = st.get("channel") or sf_path.stem.replace("state_", "")
                if channel and ch != slugify(channel):
                    continue
                if st.get("pid") and _pid_alive(st.get("pid")):
                    _kill_proc_tree(None, st.get("pid"))
                    stopped_channels.append(ch)
                st["running"] = False
                st["status"] = "STOPPED"
                st["in_progress_clips"] = []
                sf_path.write_text(json.dumps(st, indent=2), encoding="utf-8")
            except Exception:
                pass

    for ch in targets:
        sess = CLIPPER_SESSIONS.get(ch)
        if sess:
            _kill_proc_tree(sess.get("proc"))
            if ch not in stopped_channels:
                stopped_channels.append(ch)
            CLIPPER_SESSIONS.pop(ch, None)

    # Clean up stale buffer folders without active sessions to save disk space
    if LIVE_BUFFER_DIR.exists():
        for d in LIVE_BUFFER_DIR.glob("*_*"):
            if d.is_dir() and not d.name.startswith("audio_"):
                try:
                    is_active = any(
                        s.get("proc") and s["proc"].poll() is None and s.get("channel", "") in d.name
                        for s in CLIPPER_SESSIONS.values()
                    )
                    if not is_active and (time.time() - d.stat().st_mtime) > 1800:
                        shutil.rmtree(d, ignore_errors=True)
                except Exception:
                    pass

    if stopped_channels:
        log(f"Stopped Live Clipper session(s): {', '.join(stopped_channels)}")
    return {"status": "STOPPED", "stopped": stopped_channels, "was_running": bool(stopped_channels)}


def start_live_clipper(payload: dict) -> dict:
    url = (payload.get("url") or "").strip()
    if not url:
        raise ValueError("Stream URL is required (Twitch or YouTube Live)")

    LIVE_BUFFER_DIR.mkdir(parents=True, exist_ok=True)
    raw_name = (payload.get("name") or "").strip()
    if raw_name:
        channel = slugify(raw_name)
    else:
        m_tw = re.search(r"twitch\.tv/([a-zA-Z0-9_]+)", url, re.I)
        m_yt = re.search(r"(?:v=|youtu\.be/|live/)([a-zA-Z0-9_-]{11})", url)
        channel = slugify(m_tw.group(1) if m_tw else (f"yt-{m_yt.group(1)}" if m_yt else f"stream-{int(time.time())}"))

    # Only stop an existing session with the SAME channel name (supports multiple simultaneous streams!)
    stop_live_clipper(channel)

    state_file = LIVE_BUFFER_DIR / f"state_{channel}.json"
    keywords = (payload.get("keywords") or "").strip()
    threshold = float(payload.get("threshold", 72))
    chat_pre_pad = int(payload.get("chat_pre_pad", 20))
    audio_pre_pad = int(payload.get("audio_pre_pad", 15))
    post_pad = int(payload.get("post_pad", 8))
    max_clip_sec = int(payload.get("max_clip_sec", 30))
    layout = payload.get("layout", "split-blur")
    if layout not in ("split-blur", "facecam-split", "pip-overlay", "crop", "landscape"):
        layout = "split-blur"
    facecam_pos = payload.get("facecam_pos", "top-right")
    if facecam_pos not in ("top-right", "top-left", "bottom-right", "bottom-left"):
        facecam_pos = "top-right"
    asr = payload.get("asr", "hinglish")
    if asr not in ("modal", "hinglish", "whisper", "whistle"):
        asr = "hinglish"
    asr_lang = payload.get("asr_lang", "auto")
    if asr_lang not in ("auto", "hi", "en"):
        asr_lang = "auto"
    # Auto-guard: never run Hindi/Hinglish Whisper on English Twitch streams unless Hindi is explicitly selected
    if "twitch.tv/" in url.lower() and asr == "hinglish" and asr_lang != "hi":
        if not any(ind in url.lower() for ind in ("rakazone", "mythpat", "scout", "mortal", "carry", "hindi")):
            asr = "whistle"
            asr_lang = "en"
    continuous = bool(payload.get("continuous", True))
    max_clips = 0 if continuous else int(payload.get("max_clips", 0))
    duration_minutes = 0.0 if continuous else float(payload.get("duration_minutes", 0))
    keep_max_clips = int(payload.get("keep_max_clips", 20))

    cmd = [
        studio_python(),
        str(STUDIO_ROOT / "orchestration" / "live_clipper_agent.py"),
        "--url", url,
        "--name", channel,
        "--state-file", str(state_file),
        "--threshold", str(threshold),
        "--min-export-score", str(float(payload.get("min_export_score", 72.0) or 72.0)),
        "--chat-pre-pad", str(chat_pre_pad),
        "--audio-pre-pad", str(audio_pre_pad),
        "--post-pad", str(post_pad),
        "--max-clip-sec", str(max_clip_sec),
        "--layout", layout,
        "--facecam-pos", facecam_pos,
        "--asr", asr,
        "--asr-lang", asr_lang,
        "--buffer-minutes", "5",
        "--max-clips", str(max_clips),
        "--duration-minutes", str(duration_minutes),
        "--keep-max-clips", str(keep_max_clips),
    ]
    if continuous:
        cmd += ["--continuous"]
    if keywords:
        cmd += ["--keywords", keywords]
    if payload.get("auto_upload"):
        priv = str(payload.get("upload_privacy") or "private").lower()
        if priv not in ("private", "unlisted", "public"):
            priv = "private"
        min_sc = float(payload.get("auto_upload_min_score", 90.0))
        # Strict isolation: Live Clipper auto-uploads ALWAYS target 'clipper' (ClipSurge) & S-Tier >=90 only
        cmd += ["--auto-upload", "--auto-upload-min-score", str(min_sc), "--upload-privacy", priv, "--upload-profile", "clipper"]

    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["CACTUS_TELEMETRY"] = "0"

    sess_logs = [f"[{time.strftime('%H:%M:%S')}] [{channel}] Starting Live Clipper on {url}..."]
    with CLIPPER_LOCK:
        CLIPPER_LOGS.append(sess_logs[0])

    LIVE_BUFFER_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LIVE_BUFFER_DIR / f"{channel}_live.log"
    # Append, never truncate: previous runs' scores/timestamps are the only evidence
    # available when a clip folder has to be reconstructed from buffer segments.
    lf = open(log_file, "a", encoding="utf-8", buffering=1)
    lf.write(f"\n{'=' * 72}\n" + sess_logs[0] + "\n")

    proc = subprocess.Popen(
        cmd,
        cwd=str(STUDIO_ROOT),
        stdout=lf,
        stderr=subprocess.STDOUT,
        env=env,
        start_new_session=True,
    )
    lf.close()
    CLIPPER_SESSIONS[channel] = {
        "channel": channel,
        "url": url,
        "proc": proc,
        "logs": sess_logs,
        "threshold": threshold,
        "min_export_score": float(payload.get("min_export_score", 72.0) or 72.0),
        "chat_pre_pad": chat_pre_pad,
        "post_pad": post_pad,
        "layout": layout,
    }
    log(f"Started Live Clipper [{channel}] (pid={proc.pid}) on {url}")
    return {"status": "STARTED", "channel": channel, "pid": proc.pid, "url": url}


AUTO_SCOUT_LOCK = threading.Lock()
AUTO_SCOUT_STATE: dict = {
    "enabled": False,
    "game": "Grand Theft Auto VI",
    "languages": ["EN"],
    "max_parallel": 2,
    "poll_interval_sec": 120,
    "threshold": 72.0,
    "max_clip_sec": 30,
    "layout": "split-blur",
    "last_scan_at": 0.0,
    "last_started": [],
    "last_error": None,
}
AUTO_SCOUT_THREAD: threading.Thread | None = None


def get_auto_scout_snapshot() -> dict:
    with AUTO_SCOUT_LOCK:
        return dict(AUTO_SCOUT_STATE)


def _active_clipper_urls_and_channels() -> tuple[set[str], set[str], int]:
    st = get_live_clipper_status()
    urls: set[str] = set()
    channels: set[str] = set()
    running_count = 0
    for s in st.get("sessions") or []:
        if s.get("running"):
            running_count += 1
            channels.add(str(s.get("channel") or "").lower())
            u = str((s.get("state") or {}).get("url") or "").strip().lower().rstrip("/")
            if u:
                urls.add(u)
    return urls, channels, running_count


def run_live_discover(game: str | None = None, lang: str | None = None, limit: int = 16) -> dict:
    langs = ["ALL"] if (lang and lang.upper() == "ALL") else ([l.strip().upper() for l in lang.split(",") if l.strip()] if lang else None)
    res = discover_live_streams(game=game, languages=langs, limit=limit)
    active_urls, active_channels, running_count = _active_clipper_urls_and_channels()
    for st in res.get("streams") or []:
        u_low = str(st.get("url") or "").strip().lower().rstrip("/")
        ch_low = str(st.get("suggested_channel") or "").lower()
        st["already_clipping"] = (u_low in active_urls) or (ch_low in active_channels)
    res["running_count"] = running_count
    return res


def start_parallel_batch(payload: dict) -> dict:
    """Start multiple live clippers in parallel from explicit stream list OR auto-discovered top N streams."""
    cfg = load_watchlist_config()
    hard_cap = int(cfg.get("max_parallel_hard_cap", 4))
    max_parallel = max(1, min(hard_cap, int(payload.get("max_parallel") or payload.get("auto_top_n") or 2)))
    threshold = float(payload.get("threshold", 72))
    max_clip_sec = int(payload.get("max_clip_sec", 30))
    layout = payload.get("layout", "split-blur")
    auto_upload = bool(payload.get("auto_upload", False))
    upload_privacy = str(payload.get("upload_privacy") or "private")
    keywords = (payload.get("keywords") or "gta 6,vice city,leonida,lucia,jason,police,wasted,glitch,ayo,crazy,insane,clip").strip()

    active_urls, active_channels, running_count = _active_clipper_urls_and_channels()
    slots_free = max(0, max_parallel - running_count)

    streams = payload.get("streams")
    if not streams:
        game = payload.get("game") or cfg.get("default_game", "Grand Theft Auto VI")
        lang = payload.get("lang") or "EN"
        disc = run_live_discover(game=game, lang=lang, limit=max(12, max_parallel * 4))
        # Prefer Twitch live streams for zero-friction parallel clipping
        streams = [s for s in disc.get("streams") or [] if s.get("platform") == "twitch"]

    started: list[dict] = []
    skipped: list[str] = []
    for st in streams:
        if len(started) >= slots_free and not payload.get("streams"):
            break
        if len(started) + running_count >= hard_cap:
            break
        url = str(st.get("url") or "").strip()
        if not url:
            continue
        ch_name = slugify(st.get("suggested_channel") or st.get("channel") or st.get("login") or "live-stream")
        if url.lower().rstrip("/") in active_urls or ch_name.lower() in active_channels:
            skipped.append(ch_name)
            continue
        # Use 0-VRAM CPU Whistle for English parallel streams so 2-4 streams run effortlessly!
        asr_mode = str(payload.get("asr") or st.get("recommended_asr") or "whistle")
        asr_lang = str(payload.get("asr_lang") or st.get("recommended_lang") or "en")
        res = start_live_clipper({
            "url": url,
            "name": ch_name,
            "threshold": threshold,
            "chat_pre_pad": 20,
            "audio_pre_pad": 15,
            "post_pad": 8,
            "max_clip_sec": max_clip_sec,
            "layout": layout,
            "facecam_pos": "top-right",
            "asr": asr_mode,
            "asr_lang": asr_lang,
            "max_clips": int(payload.get("max_clips", 10)),
            "duration_minutes": float(payload.get("duration_minutes", 60)),
            "keywords": keywords,
            "auto_upload": auto_upload,
            "upload_privacy": upload_privacy,
        })
        active_urls.add(url.lower().rstrip("/"))
        active_channels.add(ch_name.lower())
        started.append({
            "channel": res["channel"],
            "url": url,
            "pid": res["pid"],
            "display_name": st.get("display_name") or ch_name,
            "viewers": st.get("viewers", 0),
        })

    return {
        "status": "OK",
        "started": started,
        "skipped": skipped,
        "running_count": running_count + len(started),
        "max_parallel": max_parallel,
    }


def _auto_scout_loop():
    while True:
        snap = get_auto_scout_snapshot()
        if not snap.get("enabled"):
            time.sleep(2.0)
            continue
        try:
            res = start_parallel_batch({
                "game": snap["game"],
                "lang": ",".join(snap.get("languages") or ["EN"]),
                "max_parallel": snap["max_parallel"],
                "threshold": snap["threshold"],
                "max_clip_sec": snap["max_clip_sec"],
                "layout": snap["layout"],
            })
            with AUTO_SCOUT_LOCK:
                AUTO_SCOUT_STATE["last_scan_at"] = time.time()
                AUTO_SCOUT_STATE["last_error"] = None
                if res.get("started"):
                    AUTO_SCOUT_STATE["last_started"] = res["started"]
                    log(f"[AutoScout] Auto-started {len(res['started'])} parallel stream(s): {', '.join(s['channel'] for s in res['started'])}")
        except Exception as exc:
            with AUTO_SCOUT_LOCK:
                AUTO_SCOUT_STATE["last_scan_at"] = time.time()
                AUTO_SCOUT_STATE["last_error"] = str(exc)
        interval = max(30, int(get_auto_scout_snapshot().get("poll_interval_sec", 120)))
        for _ in range(interval):
            if not get_auto_scout_snapshot().get("enabled"):
                break
            time.sleep(1.0)


def set_auto_scout(payload: dict) -> dict:
    global AUTO_SCOUT_THREAD
    enabled = bool(payload.get("enabled", True))
    with AUTO_SCOUT_LOCK:
        AUTO_SCOUT_STATE["enabled"] = enabled
        if payload.get("game"):
            AUTO_SCOUT_STATE["game"] = str(payload["game"]).strip()
        if payload.get("lang"):
            raw_l = str(payload["lang"]).strip().upper()
            AUTO_SCOUT_STATE["languages"] = ["ALL"] if raw_l == "ALL" else [x.strip() for x in raw_l.split(",") if x.strip()]
        if payload.get("max_parallel"):
            AUTO_SCOUT_STATE["max_parallel"] = max(1, min(4, int(payload["max_parallel"])))
        if payload.get("threshold"):
            AUTO_SCOUT_STATE["threshold"] = float(payload["threshold"])
        if payload.get("max_clip_sec"):
            AUTO_SCOUT_STATE["max_clip_sec"] = int(payload["max_clip_sec"])
        if payload.get("layout"):
            AUTO_SCOUT_STATE["layout"] = str(payload["layout"])
        if payload.get("poll_interval_sec"):
            AUTO_SCOUT_STATE["poll_interval_sec"] = max(30, int(payload["poll_interval_sec"]))

    if enabled and (AUTO_SCOUT_THREAD is None or not AUTO_SCOUT_THREAD.is_alive()):
        AUTO_SCOUT_THREAD = threading.Thread(target=_auto_scout_loop, daemon=True)
        AUTO_SCOUT_THREAD.start()
    log(f"[AutoScout] {'ENABLED' if enabled else 'DISABLED'} (game={AUTO_SCOUT_STATE['game']}, max_parallel={AUTO_SCOUT_STATE['max_parallel']})")
    return get_auto_scout_snapshot()


# ---------------------------------------------------------------------------
# Publish agent scheduler (select -> publish -> delete staged private Shorts)
# ---------------------------------------------------------------------------
PUBLISH_LOCK = threading.Lock()
PUBLISH_STATE: dict = {
    "running": False,
    "last_run_at": 0.0,
    "last_report": None,
    "last_error": None,
}
PUBLISH_THREAD: threading.Thread | None = None


def get_publish_snapshot() -> dict:
    """Scheduler view of the publish agent. Config lives in config/clipper-publish.json."""
    from scripts.publish_agent import load_publish_config, in_peak_window, is_staged
    from scripts.youtube_uploader import load_upload_history

    cfg = load_publish_config()
    with PUBLISH_LOCK:
        snap = dict(PUBLISH_STATE)
    snap["config"] = cfg
    snap["peak_window_open"] = in_peak_window(cfg)
    staged = [r for r in load_upload_history() if is_staged(r)]
    snap["staged_count"] = len(staged)
    snap["staged"] = [
        {
            "video_id": r.get("video_id"),
            "title": r.get("title"),
            "url": r.get("url"),
            "clip_channel": r.get("clip_channel"),
            "uploaded_at": r.get("uploaded_at"),
            "publish_status": r.get("publish_status"),
            "local_clip_deleted": r.get("local_clip_deleted"),
            "human_score": (r.get("human_review") or {}).get("human_score"),
        }
        for r in staged[:40]
    ]
    snap["orphaned"] = [r for r in staged if r.get("publish_status") == "orphaned"]
    snap["orphaned_count"] = len(snap["orphaned"])
    return snap


def _publish_loop():
    """Runs a select -> publish -> delete pass on a fixed interval from config."""
    while True:
        from scripts.publish_agent import load_publish_config

        cfg = load_publish_config()
        if not cfg.get("enabled"):
            time.sleep(5.0)
            continue

        started = time.time()
        with PUBLISH_LOCK:
            if PUBLISH_STATE.get("running"):
                time.sleep(5.0)
                continue
            PUBLISH_STATE["running"] = True
        try:
            from scripts.publish_agent import run_publish_agent

            report = run_publish_agent(log=lambda m: log(f"[PublishAgent] {m}"))
            with PUBLISH_LOCK:
                PUBLISH_STATE["last_run_at"] = time.time()
                PUBLISH_STATE["last_report"] = report
                PUBLISH_STATE["last_error"] = None
        except Exception as exc:
            with PUBLISH_LOCK:
                PUBLISH_STATE["last_run_at"] = time.time()
                PUBLISH_STATE["last_error"] = str(exc)
            log(f"[PublishAgent] pass failed: {exc}")
        finally:
            with PUBLISH_LOCK:
                PUBLISH_STATE["running"] = False

        # Sleep in slices so flipping `enabled` in config takes effect quickly.
        remaining = max(0.0, int(cfg.get("review_interval_sec", 3600)) - (time.time() - started))
        while remaining > 0:
            if not load_publish_config().get("enabled"):
                break
            step = min(5.0, remaining)
            time.sleep(step)
            remaining -= step


def ensure_publish_scheduler() -> None:
    """Start the background pass loop once per dashboard boot (if enabled)."""
    global PUBLISH_THREAD
    from scripts.publish_agent import load_publish_config

    if not load_publish_config().get("enabled"):
        return
    with PUBLISH_LOCK:
        if PUBLISH_THREAD is not None and PUBLISH_THREAD.is_alive():
            return
        PUBLISH_THREAD = threading.Thread(target=_publish_loop, daemon=True, name="publish-agent")
        PUBLISH_THREAD.start()
    log("[PublishAgent] scheduler started")


def run_publish_pass(dry_run: bool = False, force_publish: bool = False) -> dict:
    """Manual trigger from the panel. Refuses to overlap a scheduled pass."""
    with PUBLISH_LOCK:
        if PUBLISH_STATE.get("running"):
            return {"error": "publish pass already running", "status": "BUSY"}
        PUBLISH_STATE["running"] = True
    try:
        from scripts.publish_agent import run_publish_agent

        report = run_publish_agent(
            dry_run=dry_run,
            force_publish=force_publish,
            log=lambda m: log(f"[PublishAgent] {m}"),
        )
        with PUBLISH_LOCK:
            PUBLISH_STATE["last_run_at"] = time.time()
            PUBLISH_STATE["last_report"] = report
            PUBLISH_STATE["last_error"] = None
        return {"status": "OK", "report": report}
    except Exception as exc:
        with PUBLISH_LOCK:
            PUBLISH_STATE["last_error"] = str(exc)
        log(f"[PublishAgent] manual pass failed: {exc}")
        return {"error": str(exc), "status": "FAILED"}
    finally:
        with PUBLISH_LOCK:
            PUBLISH_STATE["running"] = False


def studio_python() -> str:
    venv_py = STUDIO_ROOT / ".venv" / "bin" / "python"
    return str(venv_py) if venv_py.exists() else sys.executable


def log(msg: str):
    entry = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(entry, flush=True)
    with LOG_LOCK:
        LOG_BUFFER.append(entry)
        if len(LOG_BUFFER) > 250:
            LOG_BUFFER[:] = LOG_BUFFER[-250:]


def slugify(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")[:64] or "untitled"


def probe_hardware() -> dict:
    global HW_INFO_CACHE
    if HW_INFO_CACHE is not None:
        return HW_INFO_CACHE
    gpu_name = None
    gpu_vram = None
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=4,
        )
        if res.returncode == 0 and res.stdout.strip():
            parts = [p.strip() for p in res.stdout.strip().splitlines()[0].split(",")]
            gpu_name = parts[0]
            gpu_vram = parts[1] if len(parts) > 1 else None
    except Exception:
        pass
    HW_INFO_CACHE = {
        "gpu": gpu_name,
        "vram": gpu_vram,
        "nvenc": detect_nvenc(),
    }
    return HW_INFO_CACHE


def get_styles_catalog() -> list[dict]:
    global STYLE_CACHE
    if STYLE_CACHE is None:
        STYLE_CACHE = list_all_styles()
    return STYLE_CACHE


def count_skills() -> list[str]:
    names: set[str] = set()
    for base in (SKILLS_DIR, STUDIO_ROOT / ".claude" / "skills"):
        if base.exists():
            for d in base.iterdir():
                if d.is_dir() and (d / "SKILL.md").exists():
                    names.add(d.name)
    return sorted(names)


def parse_ideas_queue() -> list[dict]:
    if not QUEUE_FILE.exists():
        return []
    items: list[dict] = []
    in_table = False
    for line in QUEUE_FILE.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("| ID |"):
            in_table = True
            continue
        if in_table and s.startswith("|---"):
            continue
        if in_table:
            if not s.startswith("|"):
                if items:
                    break
                continue
            parts = [p.strip().strip("`") for p in s.split("|")[1:-1]]
            if len(parts) >= 9 and parts[0] and not parts[0].startswith("["):
                items.append({
                    "id": parts[0],
                    "topic": parts[1],
                    "category": parts[2],
                    "format": parts[3],
                    "hook": parts[4],
                    "research_status": parts[5],
                    "script_status": parts[6],
                    "production_status": parts[7],
                    "priority": parts[8],
                    "notes": parts[9] if len(parts) > 9 else "",
                    "slug": slugify(parts[1]),
                })
    return items


def append_idea_to_queue(item: dict) -> dict:
    existing = parse_ideas_queue()
    next_num = len(existing) + 1
    prefix = "GTA" if "gta" in item.get("topic", "").lower() else "CR"
    idea_id = item.get("id") or f"{prefix}-{next_num:03d}"

    def clean_cell(val: str) -> str:
        return str(val or "—").replace("|", "/").replace("\n", " ").strip()

    row = (
        f"| {clean_cell(idea_id)} | {clean_cell(item.get('topic', 'Untitled'))} | "
        f"{clean_cell(item.get('category', 'Tech / AI Explainer'))} | "
        f"{clean_cell(item.get('format', 'Short'))} | "
        f"{clean_cell(item.get('hook', 'Pending research'))} | `idea` | — | — | "
        f"{clean_cell(item.get('priority', 'MEDIUM')).upper()} | "
        f"{clean_cell(item.get('notes', 'Added via Studio UI'))} |"
    )

    text = QUEUE_FILE.read_text(encoding="utf-8") if QUEUE_FILE.exists() else ""
    marker = "\n---\n\n## Adding New Ideas"
    if marker in text:
        updated = text.replace(marker, f"\n{row}{marker}", 1)
    else:
        updated = text.rstrip() + f"\n{row}\n"
    QUEUE_FILE.write_text(updated, encoding="utf-8")
    return {"id": idea_id, "topic": item.get("topic"), "row": row}


def list_projects() -> list[dict]:
    projects: list[dict] = []
    if not EXPORTS_DIR.exists():
        return projects
    for d in sorted(EXPORTS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir():
            continue
        mp4s = sorted(d.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        manifest_path = d / "project.json"
        review_path = d / "review.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        review = json.loads(review_path.read_text(encoding="utf-8")) if review_path.exists() else {}
        checklist_path = d / "checklist.md"
        checklist_text = checklist_path.read_text(encoding="utf-8") if checklist_path.exists() else ""
        human_approved = bool(re.search(r"\[x\]\s*\*\*Final human approval\*\*|\[x\]\s*Final human approval", checklist_text, re.I))

        samples_dir = d / "review_samples"
        frames = sorted(p.name for p in samples_dir.glob("*.jpg")) if samples_dir.exists() else []
        video_name = mp4s[0].name if mp4s else manifest.get("export_video")

        projects.append({
            "slug": d.name,
            "topic": manifest.get("topic") or d.name.replace("-", " ").title(),
            "format": manifest.get("format", "short"),
            "resolution": manifest.get("resolution") or review.get("metrics", {}).get("resolution"),
            "created_at": manifest.get("created_at"),
            "style": manifest.get("style"),
            "hook": manifest.get("hook"),
            "video": video_name,
            "video_url": f"/media/exports/{d.name}/{video_name}" if video_name else None,
            "has_metadata": (d / "metadata.md").exists(),
            "has_checklist": checklist_path.exists(),
            "has_review": review_path.exists(),
            "qa_passed": review.get("passed", manifest.get("qa_passed")),
            "qa_verdict": review.get("verdict", manifest.get("qa_verdict", "UNREVIEWED")),
            "metrics": review.get("metrics", {}),
            "human_approved": human_approved,
            "youtube_upload": read_upload_receipt(d),
            "frames": [f"/media/exports/{d.name}/review_samples/{f}" for f in frames],
            "job_status": ACTIVE_JOBS.get(d.name, {}).get("status", "READY" if video_name else "IDLE"),
        })
    return projects


def get_project_detail(slug: str) -> dict | None:
    d = EXPORTS_DIR / slug
    if not d.exists() or not d.is_dir():
        return None
    summary = next((p for p in list_projects() if p["slug"] == slug), None)
    if not summary:
        return None

    def read_opt(p: Path) -> str | None:
        return p.read_text(encoding="utf-8", errors="replace") if p.exists() else None

    render_dir = RENDERS_DIR / slug
    review_path = d / "review.json"
    summary["review"] = json.loads(review_path.read_text(encoding="utf-8")) if review_path.exists() else None
    summary["metadata_md"] = read_opt(d / "metadata.md")
    summary["checklist_md"] = read_opt(d / "checklist.md")
    summary["review_md"] = read_opt(d / "REVIEW.md")
    summary["script_md"] = read_opt(render_dir / "script.md")
    return summary


def run_render_job(payload: dict) -> dict:
    topic = (payload.get("topic") or "GTA VI Storage Requirements PS5").strip()
    slug = slugify(payload.get("slug") or topic)
    fmt = payload.get("format", "short")
    if fmt not in ("short", "long"):
        fmt = "short"
    style = payload.get("style", "auto")
    voice = payload.get("voice") or DEFAULT_PROFILE_ID
    edge_voice = payload.get("edge_voice") or DEFAULT_EDGE_VOICE
    quality = payload.get("quality", "high")
    include_sfx = payload.get("sfx", True)
    custom_script = (payload.get("script_text") or "").strip()

    job = {
        "slug": slug,
        "topic": topic,
        "format": fmt,
        "style": style,
        "status": "RUNNING",
        "started_at": time.time(),
        "finished_at": None,
        "error": None,
    }
    ACTIVE_JOBS[slug] = job

    def _worker():
        tmp_script_path = None
        try:
            cmd = [
                studio_python(),
                str(STUDIO_ROOT / "orchestration" / "multi_agent_studio.py"),
                "--topic", topic,
                "--slug", slug,
                "--format", fmt,
                "--style", style,
                "--voice", voice,
                "--edge-voice", edge_voice,
                "--quality", quality,
            ]
            if not include_sfx:
                cmd.append("--no-sfx")

            if custom_script:
                render_dir = RENDERS_DIR / slug
                render_dir.mkdir(parents=True, exist_ok=True)
                tmp_script_path = render_dir / "custom_input_script.md"
                tmp_script_path.write_text(custom_script, encoding="utf-8")
                cmd.extend(["--script", str(tmp_script_path)])

            log(f"Launching render job '{slug}' ({fmt}, style={style}, quality={quality})...")
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.rstrip()
                if line and not line.startswith(("{", "}", "  \"")):
                    log(f"[{slug}] {line}")
            ret = proc.wait()
            if ret == 0:
                job["status"] = "DONE"
                log(f"Render job '{slug}' completed successfully!")
            else:
                job["status"] = "ERROR"
                job["error"] = f"Pipeline exited with code {ret}"
                log(f"Render job '{slug}' failed with exit code {ret}.")
        except Exception as e:
            job["status"] = "ERROR"
            job["error"] = str(e)
            log(f"Render job '{slug}' crashed: {e}")
        finally:
            job["finished_at"] = time.time()

    threading.Thread(target=_worker, daemon=True).start()
    return job


def list_youtube_uploads() -> list[dict]:
    """Collect all completed upload receipts from persistent history plus exports/ and exports/live-clips/."""
    by_vid: dict[str, dict] = {}
    extra: list[dict] = []

    for rec in load_upload_history():
        vid = rec.get("video_id")
        if vid:
            by_vid[vid] = rec
        else:
            extra.append(rec)

    if EXPORTS_DIR.exists():
        for rec_path in EXPORTS_DIR.rglob("youtube_upload.json"):
            try:
                data = json.loads(rec_path.read_text(encoding="utf-8"))
                data["folder"] = str(rec_path.parent.relative_to(STUDIO_ROOT))
                vid = data.get("video_id")
                if vid:
                    by_vid.setdefault(vid, data)
                else:
                    extra.append(data)
            except Exception:
                pass
    receipts = list(by_vid.values()) + extra
    receipts.sort(key=lambda r: r.get("uploaded_at") or "", reverse=True)
    return receipts


def start_youtube_upload(payload: dict) -> dict:
    target = (payload.get("target") or payload.get("slug") or payload.get("clip_id") or "").strip()
    if not target:
        raise ValueError("target (project slug or clip_id) is required")
    target_type = payload.get("type")  # "project" | "clip" | None
    channel = (payload.get("channel") or "").strip() or None
    approve_now = bool(payload.get("approve_now", False))

    overrides = {
        k: payload[k]
        for k in ("title", "description", "hashtags", "tags", "category_id", "privacy_status", "publish_at", "made_for_kids", "contains_synthetic_media", "thumbnail_path")
        if k in payload and payload[k] is not None
    }

    # Validate target & approval synchronously before spawning thread
    preview = build_upload_metadata(target, target_type=target_type, channel=channel, overrides=overrides)
    if not approve_now and not preview["human_approved"]:
        raise PermissionError(
            "CreatorRadar Rule 4: Human approval required before uploading to YouTube. "
            "Sign off the checklist or check 'Approve & Upload'."
        )

    # Strict isolation: live clips ALWAYS route to 'clipper' (ClipSurge), studio exports ALWAYS route to 'studio' (Paper Trail)
    if preview["kind"] == "clip":
        profile = "clipper"
    elif preview["kind"] == "project":
        profile = "studio"
    else:
        profile = normalize_profile(payload.get("profile"), kind=preview["kind"])
    yt_st = get_youtube_status(refresh_channel=False, profile=profile)
    if not yt_st.get("connected"):
        label = PROFILE_LABELS.get(profile, profile)
        raise RuntimeError(f"{label} ('{profile}') is not connected yet. Connect it in the YouTube Upload tab first.")

    job_id = f"{preview['kind']}:{preview['id']}"
    job = {
        "job_id": job_id,
        "kind": preview["kind"],
        "profile": profile,
        "id": preview["id"],
        "channel": preview["channel"],
        "title": preview["title"],
        "privacy_status": preview["privacy_status"],
        "status": "UPLOADING",
        "progress": 0,
        "bytes_sent": 0,
        "total_bytes": 0,
        "started_at": time.time(),
        "finished_at": None,
        "receipt": None,
        "error": None,
    }
    with UPLOAD_LOCK:
        ACTIVE_UPLOADS[job_id] = job

    def _worker():
        def _prog(pct: int, sent: int, total: int):
            with UPLOAD_LOCK:
                job["progress"] = pct
                job["bytes_sent"] = sent
                job["total_bytes"] = total

        try:
            log(f"[YouTube:{profile}] Starting upload '{preview['title']}' ({preview['privacy_status']})...")
            receipt = upload_video(
                target,
                target_type=target_type,
                channel=channel,
                overrides=overrides,
                require_approval=True,
                approve_now=approve_now,
                progress_cb=_prog,
                profile=profile,
                delete_clip_after_upload=bool(payload.get("delete_clip_after_upload", True)),
            )
            with UPLOAD_LOCK:
                job["status"] = "DONE"
                job["progress"] = 100
                job["receipt"] = receipt
                job["finished_at"] = time.time()
            cleanup_note = f" (auto-deleted local clip, freed {receipt.get('freed_mb', 0)} MB)" if receipt.get("local_clip_deleted") else ""
            log(f"[YouTube] Uploaded '{receipt['title']}' -> {receipt['url']}{cleanup_note}")
        except Exception as exc:
            with UPLOAD_LOCK:
                job["status"] = "ERROR"
                job["error"] = str(exc)
                job["finished_at"] = time.time()
            log(f"[YouTube] Upload failed for '{preview['id']}': {exc}")

    threading.Thread(target=_worker, daemon=True).start()
    return job


# The API binds 127.0.0.1, but that does NOT stop a web page the user visits from
# issuing cross-origin POSTs. Echo CORS only for the Studio UI's own origins so a
# random site cannot start/delete/upload clips through the user's browser.
ALLOWED_ORIGINS = {
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
}


class StudioAPIHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _origin_allowed(self) -> bool:
        """Allow non-browser clients (no Origin header) and the Studio UI origins only."""
        origin = self.headers.get("Origin")
        return origin is None or origin in ALLOWED_ORIGINS

    def _send_cors(self):
        origin = self.headers.get("Origin")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Range")

    def _send_json(self, data, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self._send_cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str, status: int = 200):
        body = html.encode("utf-8")
        self.send_response(status)
        self._send_cors()
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return {}
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        return json.loads(raw) if raw.strip() else {}

    def _serve_media(self, rel_path: str):
        # Strictly allow only exports/, renders/, and assets/
        parts = Path(urllib.parse.unquote(rel_path)).parts
        if not parts or parts[0] not in ("exports", "renders", "assets") or ".." in parts:
            self._send_json({"error": "Forbidden media path"}, 403)
            return
        target = (STUDIO_ROOT / Path(*parts)).resolve()
        if not str(target).startswith(str(STUDIO_ROOT.resolve())) or not target.is_file():
            self._send_json({"error": "File not found"}, 404)
            return

        file_size = target.stat().st_size
        ctype, _ = mimetypes.guess_type(str(target))
        ctype = ctype or "application/octet-stream"
        range_header = self.headers.get("Range")

        if range_header and range_header.startswith("bytes="):
            byte_range = range_header.replace("bytes=", "").split(",")[0]
            start_s, end_s = byte_range.split("-", 1)
            start = int(start_s) if start_s else 0
            end = int(end_s) if end_s else file_size - 1
            end = min(end, file_size - 1)
            if start > end or start >= file_size:
                self.send_response(416)
                self._send_cors()
                self.send_header("Content-Range", f"bytes */{file_size}")
                self.end_headers()
                return
            length = end - start + 1
            self.send_response(206)
            self._send_cors()
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            self.send_header("Content-Length", str(length))
            self.end_headers()
            with open(target, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(65536, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
            return

        self.send_response(200)
        self._send_cors()
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(file_size))
        self.end_headers()
        with open(target, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def do_OPTIONS(self):
        if not self._origin_allowed():
            self.send_response(403)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(204)
        self._send_cors()
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path.startswith("/media/"):
            self._serve_media(path[len("/media/"):])
            return

        if path == "/api/status":
            sample_file = VOICE_DIR / "creator_sample.wav"
            has_voice = sample_file.exists() and sample_file.stat().st_size > 1000
            vs_online = is_voicestudio_running(timeout=0.8)
            vs_profiles = list_voicestudio_profiles(timeout=1.0) if vs_online else []
            skills = count_skills()
            styles = get_styles_catalog()
            hw = probe_hardware()
            with LOG_LOCK:
                logs_snapshot = list(LOG_BUFFER[-80:])
            yt_status = get_youtube_status(refresh_channel=False)
            yt_subs = (yt_status.get("channel") or {}).get("subscribers")

            self._send_json({
                "studio": "CreatorRadar",
                "version": "2.0",
                "hardware": hw,
                "skills_count": len(skills),
                "skills": skills,
                "styles_count": len(styles),
                "has_voice_sample": has_voice,
                "voice_sample_url": "/media/assets/voices/creator_sample.wav" if has_voice else None,
                "voice_sample_bytes": sample_file.stat().st_size if has_voice else 0,
                "voicestudio": {
                    "url": VOICE_STUDIO_URL,
                    "online": vs_online,
                    "profiles": vs_profiles,
                },
                "youtube": {
                    "connected": yt_status["connected"],
                    "has_client_secret": yt_status["has_client_secret"],
                    "channel": yt_status["channel"],
                    "profiles": yt_status.get("profiles"),
                },
                "subscribers": yt_subs if yt_subs else 11000,
                "operating_cost": "$0.00",
                "active_jobs": list(ACTIVE_JOBS.values()),
                "projects_count": len(list_projects()),
                "logs": logs_snapshot,
                "timestamp": time.time(),
            })
            return

        if path == "/api/styles":
            qs = urllib.parse.parse_qs(parsed.query)
            q = (qs.get("q", [""])[0]).lower().strip()
            catalog_filter = (qs.get("catalog", [""])[0]).lower().strip()
            styles = get_styles_catalog()
            if catalog_filter:
                styles = [s for s in styles if s.get("catalog") == catalog_filter]
            if q:
                styles = [
                    s for s in styles
                    if q in s["style_id"].lower()
                    or q in s.get("name", "").lower()
                    or q in s.get("best_for", "").lower()
                    or q in s.get("mood", "").lower()
                ]
            self._send_json({"count": len(styles), "styles": styles})
            return

        if path == "/api/queue":
            self._send_json({"items": parse_ideas_queue()})
            return

        if path == "/api/projects":
            self._send_json({"projects": list_projects()})
            return

        if path.startswith("/api/projects/"):
            slug = path[len("/api/projects/"):].strip("/")
            detail = get_project_detail(slug)
            if not detail:
                self._send_json({"error": f"Project '{slug}' not found"}, 404)
                return
            self._send_json(detail)
            return

        if path == "/api/clipper/status":
            self._send_json(get_live_clipper_status())
            return

        if path == "/api/youtube/status":
            qs = urllib.parse.parse_qs(parsed.query)
            refresh = qs.get("refresh", ["0"])[0] in ("1", "true", "yes")
            profile = (qs.get("profile") or ["studio"])[0]
            st = get_youtube_status(refresh_channel=refresh, profile=profile)
            with UPLOAD_LOCK:
                st["active_uploads"] = list(ACTIVE_UPLOADS.values())
            st["uploads"] = list_youtube_uploads()
            self._send_json(st)
            return

        if path == "/api/youtube/oauth/callback":
            qs = urllib.parse.parse_qs(parsed.query)
            if "error" in qs:
                err = qs["error"][0]
                self._send_html(
                    f"<!doctype html><html><body style='background:#080d16;color:#f8fafc;font-family:system-ui;padding:48px;text-align:center'>"
                    f"<h2 style='color:#fb7185'>YouTube Login Cancelled</h2><p>{err}</p>"
                    f"<p><a href='http://localhost:3000/?tab=youtube' style='color:#38bdf8'>Return to CreatorRadar Studio</a></p></body></html>",
                    400,
                )
                return
            code = (qs.get("code") or [""])[0]
            state = (qs.get("state") or [""])[0]
            if not code:
                self._send_html("<h3>Missing OAuth code.</h3>", 400)
                return
            try:
                res = complete_oauth_callback(code=code, state=state)
                ch = res.get("channel") or {}
                prof = res.get("profile") or "studio"
                prof_label = res.get("profile_label") or PROFILE_LABELS.get(prof, prof)
                token_file = Path(res.get("token_path") or "config/youtube_token.json").name
                log(f"[YouTube:{prof}] Connected {prof_label}: {ch.get('title')} ({ch.get('subscribers', 0):,} subs)")
                self._send_html(
                    "<!doctype html><html><head><meta charset='utf-8'><title>YouTube Connected</title></head>"
                    "<body style='background:#080d16;color:#f8fafc;font-family:system-ui;padding:56px;text-align:center'>"
                    "<div style='max-width:480px;margin:0 auto;background:#0f1726;border:1px solid #1e2d48;border-radius:18px;padding:32px'>"
                    "<div style='font-size:38px'>✅</div>"
                    f"<h2 style='color:#34d399;margin:12px 0 8px'>{prof_label} Connected!</h2>"
                    f"<p style='color:#e2e8f0;font-size:16px'><strong>{ch.get('title', 'Channel')}</strong></p>"
                    f"<p style='color:#94a3b8;font-size:13px'>{ch.get('custom_url') or ''} · {int(ch.get('subscribers', 0)):,} subscribers</p>"
                    f"<p style='color:#94a3b8;font-size:12px;margin-top:16px'>Refresh token saved locally in <code>config/{token_file}</code>.</p>"
                    "<p style='margin-top:24px'><a href='http://localhost:3000/?tab=youtube' style='display:inline-block;padding:10px 18px;background:#f47750;color:#080d16;font-weight:700;border-radius:10px;text-decoration:none'>Back to CreatorRadar Studio</a></p>"
                    "</div>"
                    f"<script>try{{if(window.opener){{window.opener.postMessage({{type:'youtube_connected',profile:'{prof}'}},'*');}}}}catch(e){{}}</script>"
                    "</body></html>"
                )
            except Exception as exc:
                log(f"[YouTube] OAuth callback failed: {exc}")
                self._send_html(
                    f"<!doctype html><html><body style='background:#080d16;color:#f8fafc;font-family:system-ui;padding:48px;text-align:center'>"
                    f"<h2 style='color:#fb7185'>YouTube Login Error</h2><pre style='color:#fda4af'>{exc}</pre>"
                    f"<p><a href='http://localhost:3000/?tab=youtube' style='color:#38bdf8'>Return to CreatorRadar Studio</a></p></body></html>",
                    500,
                )
            return

        if path == "/api/clipper/discover":
            try:
                qs = urllib.parse.parse_qs(parsed.query)
                game = (qs.get("game") or [None])[0]
                lang = (qs.get("lang") or [None])[0]
                limit = int((qs.get("limit") or ["16"])[0])
                self._send_json(run_live_discover(game=game, lang=lang, limit=limit))
            except Exception as exc:
                self._send_json({"error": str(exc)}, 500)
            return

        if path == "/api/clipper/publish":
            try:
                self._send_json(get_publish_snapshot())
            except Exception as exc:
                self._send_json({"error": str(exc)}, 500)
            return

        if path == "/":
            self._send_json({
                "service": "CreatorRadar Studio Engine API",
                "ui": "Run `cd dashboard-next && npm run dev` -> http://localhost:3000",
                "endpoints": [
                    "GET /api/status",
                    "GET /api/styles",
                    "GET /api/queue",
                    "POST /api/queue",
                    "GET /api/projects",
                    "GET /api/projects/<slug>",
                    "POST /api/projects/<slug>/approve",
                    "POST /api/render",
                    "POST /api/upload-voice",
                    "POST /api/voice/preview",
                    "POST /api/tools/hookscore",
                    "POST /api/tools/lint-title",
                    "GET /api/clipper/status",
                    "POST /api/clipper/start",
                    "POST /api/clipper/stop",
                    "POST /api/clipper/approve",
                    "GET /api/youtube/status",
                    "POST /api/youtube/credentials",
                    "POST /api/youtube/auth/start",
                    "GET /api/youtube/oauth/callback",
                    "POST /api/youtube/disconnect",
                    "POST /api/youtube/preview-metadata",
                    "POST /api/youtube/upload",
                ],
            })
            return

        self._send_json({"error": "Not found"}, 404)

    def do_POST(self):
        if not self._origin_allowed():
            self._send_json({"error": "Origin not allowed"}, 403)
            return

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/render":
            try:
                payload = self._read_json()
                job = run_render_job(payload)
                self._send_json({"status": "STARTED", "job": job})
            except Exception as e:
                self._send_json({"error": str(e)}, 400)
            return

        if path == "/api/queue":
            try:
                payload = self._read_json()
                if not payload.get("topic"):
                    self._send_json({"error": "topic is required"}, 400)
                    return
                created = append_idea_to_queue(payload)
                log(f"Added queue idea [{created['id']}]: {created['topic']}")
                self._send_json({"status": "CREATED", "item": created, "items": parse_ideas_queue()})
            except Exception as e:
                self._send_json({"error": str(e)}, 400)
            return

        if path == "/api/upload-voice":
            try:
                length = int(self.headers.get("Content-Length", 0))
                if length <= 0:
                    self._send_json({"error": "Empty audio payload"}, 400)
                    return
                raw_audio = self.rfile.read(length)
                raw_path = VOICE_DIR / "creator_sample_raw.webm"
                wav_path = VOICE_DIR / "creator_sample.wav"
                raw_path.write_bytes(raw_audio)

                subprocess.run(
                    ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw_path), "-ar", "48000", "-ac", "2", str(wav_path)],
                    check=True,
                )
                log(f"Voice profile enrolled: assets/voices/creator_sample.wav ({wav_path.stat().st_size} bytes)")
                self._send_json({
                    "status": "SAVED",
                    "path": str(wav_path),
                    "url": "/media/assets/voices/creator_sample.wav",
                    "bytes": wav_path.stat().st_size,
                    "message": "Voice profile enrolled and mastered to 48kHz stereo WAV.",
                })
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        if path == "/api/voice/preview":
            try:
                payload = self._read_json()
                text = (payload.get("text") or "CreatorRadar Studio voice check. Broadcast loudness locked to minus fourteen LUFS.").strip()
                voice_id = payload.get("voice") or DEFAULT_PROFILE_ID
                edge_voice = payload.get("edge_voice") or DEFAULT_EDGE_VOICE
                preview_dir = RENDERS_DIR / "_voice_previews"
                preview_dir.mkdir(parents=True, exist_ok=True)
                out_name = f"preview_{int(time.time())}.wav"
                out_path = preview_dir / out_name
                res = generate_narration(text, out_path, voice_name=voice_id, edge_voice=edge_voice)
                log(f"Generated voice preview via {res['engine']}")
                self._send_json({
                    "status": "OK",
                    "engine": res["engine"],
                    "voicestudio_active": res["voicestudio_active"],
                    "audio_url": f"/media/renders/_voice_previews/{out_name}",
                })
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        if path.startswith("/api/projects/") and path.endswith("/approve"):
            slug = path[len("/api/projects/"):-len("/approve")].strip("/")
            checklist_path = EXPORTS_DIR / slug / "checklist.md"
            manifest_path = EXPORTS_DIR / slug / "project.json"
            if not checklist_path.exists():
                self._send_json({"error": "Checklist not found"}, 404)
                return
            payload = self._read_json()
            approved = bool(payload.get("approved", True))
            text = checklist_path.read_text(encoding="utf-8")
            if approved:
                text = re.sub(r"- \[ \]", "- [x]", text)
            else:
                text = re.sub(r"- \[x\]", "- [ ]", text, flags=re.I)
            checklist_path.write_text(text, encoding="utf-8")
            if manifest_path.exists():
                m = json.loads(manifest_path.read_text(encoding="utf-8"))
                m["human_approved"] = approved
                manifest_path.write_text(json.dumps(m, indent=2), encoding="utf-8")
            log(f"Human approval for '{slug}' set to: {approved} (manual YouTube upload still required per Rule 4)")
            self._send_json({"status": "UPDATED", "slug": slug, "human_approved": approved})
            return

        if path == "/api/tools/hookscore":
            try:
                payload = self._read_json()
                hook = (payload.get("hook") or "").strip()
                if not hook:
                    self._send_json({"error": "hook is required"}, 400)
                    return
                tool = SKILLS_DIR / "yt-script" / "hookscore.py"
                res = subprocess.run(
                    [studio_python(), str(tool), "--hook", hook, "--json"],
                    capture_output=True, text=True, timeout=10,
                )
                if res.returncode != 0:
                    self._send_json({"error": res.stderr or "hookscore failed"}, 500)
                    return
                self._send_json({"result": json.loads(res.stdout)})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        if path == "/api/tools/lint-title":
            try:
                payload = self._read_json()
                title = (payload.get("title") or "").strip()
                thumb = (payload.get("thumb") or "").strip()
                if not title:
                    self._send_json({"error": "title is required"}, 400)
                    return
                tool = SKILLS_DIR / "yt-package" / "title.py"
                cmd = [studio_python(), str(tool), "--title", title, "--json"]
                if thumb:
                    cmd.extend(["--thumb", thumb])
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if res.returncode != 0:
                    self._send_json({"error": res.stderr or "title linter failed"}, 500)
                    return
                self._send_json({"result": json.loads(res.stdout)})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        if path == "/api/clipper/start":
            try:
                payload = self._read_json()
                res = start_live_clipper(payload)
                self._send_json(res)
            except Exception as e:
                self._send_json({"error": str(e)}, 400)
            return

        if path == "/api/clipper/start-batch":
            try:
                payload = self._read_json()
                res = start_parallel_batch(payload)
                self._send_json(res)
            except Exception as e:
                self._send_json({"error": str(e)}, 400)
            return

        if path == "/api/clipper/auto-scout":
            try:
                payload = self._read_json()
                res = set_auto_scout(payload)
                self._send_json(res)
            except Exception as e:
                self._send_json({"error": str(e)}, 400)
            return

        if path == "/api/clipper/publish/run":
            try:
                payload = self._read_json() or {}
                res = run_publish_pass(
                    dry_run=bool(payload.get("dry_run")),
                    force_publish=bool(payload.get("force_publish")),
                )
                if res.get("status") == "BUSY":
                    self._send_json(res, 409)
                elif res.get("status") == "FAILED":
                    self._send_json(res, 500)
                else:
                    self._send_json(res)
            except Exception as e:
                self._send_json({"error": str(e)}, 400)
            return

        if path == "/api/clipper/publish/config":
            try:
                payload = self._read_json() or {}
                from scripts.publish_agent import load_publish_config, save_publish_config

                cfg = load_publish_config()
                for key in (
                    "enabled",
                    "dry_run",
                    "require_verdict",
                    "keep_local_after_publish",
                    "max_publish_per_run",
                    "max_delete_per_run",
                    "review_interval_sec",
                    "peak_window",
                ):
                    if key in payload:
                        cfg[key] = payload[key]
                save_publish_config(cfg)
                ensure_publish_scheduler()
                self._send_json({"status": "OK", "config": cfg})
            except Exception as e:
                self._send_json({"error": str(e)}, 400)
            return

        if path == "/api/clipper/publish/decide":
            try:
                payload = self._read_json() or {}
                video_id = str(payload.get("video_id") or "").strip()
                if not video_id:
                    self._send_json({"error": "video_id required"}, 400)
                    return
                from scripts.publish_agent import manual_decision

                res = manual_decision(
                    video_id,
                    str(payload.get("action") or ""),
                    log=lambda m: log(f"[PublishAgent] {m}"),
                )
                self._send_json(res, 200 if res.get("status") == "OK" else 400)
            except Exception as e:
                self._send_json({"error": str(e)}, 400)
            return

        if path == "/api/clipper/batch-review":
            try:
                payload = self._read_json()
                batch_size = max(1, min(3, int(payload.get("batch_size", 3))))
                unreviewed: list[Path] = []
                if LIVE_CLIPS_DIR.exists():
                    all_dirs = [
                        d for ch in LIVE_CLIPS_DIR.iterdir() if ch.is_dir()
                        for d in ch.iterdir() if d.is_dir() and list(d.glob("*.mp4"))
                    ]
                    all_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                    for d in all_dirs:
                        if read_cached_groq_review(d) is None:
                            unreviewed.append(d)
                        if len(unreviewed) >= batch_size:
                            break
                reviewed = groq_batch_review_clips(unreviewed, max_batch=batch_size) if unreviewed else []
                self._send_json({
                    "status": "OK",
                    "requested": len(unreviewed),
                    "reviewed_count": len(reviewed),
                    "reviewed": reviewed,
                    "groq_usage": get_groq_usage_summary(),
                })
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        if path == "/api/clipper/human-review":
            try:
                payload = self._read_json()
                ch_in = slugify(payload.get("channel") or "")
                cid_in = (payload.get("clip_id") or "").strip()
                force = bool(payload.get("force", False))
                if ch_in and cid_in:
                    if "/" in cid_in or "\\" in cid_in or ".." in cid_in:
                        self._send_json({"error": "Invalid clip_id"}, 400)
                        return
                    target_dir = (LIVE_CLIPS_DIR / ch_in / cid_in).resolve()
                    if not str(target_dir).startswith(str(LIVE_CLIPS_DIR.resolve()) + os.sep) or not target_dir.is_dir():
                        self._send_json({"error": "Clip not found"}, 404)
                        return
                    res = review_clip_as_human(target_dir, force=force)
                    self._send_json({"status": "OK", "reviews": [res] if res else [], "groq_usage": get_groq_usage_summary()})
                    return

                # Review unreviewed A-TIER / S-TIER clips first (highest score wins)
                max_count = max(1, min(3, int(payload.get("limit", 3))))
                candidates: list[tuple[float, Path]] = []
                if LIVE_CLIPS_DIR.exists():
                    for ch_d in LIVE_CLIPS_DIR.iterdir():
                        if not ch_d.is_dir():
                            continue
                        for c_d in ch_d.iterdir():
                            if not c_d.is_dir() or not list(c_d.glob("*.mp4")):
                                continue
                            if (not force) and read_cached_human_review(c_d) is not None:
                                continue
                            sc = 0.0
                            tier = "B-TIER"
                            mj_p = c_d / "moment.json"
                            if mj_p.exists():
                                try:
                                    fus = json.loads(mj_p.read_text(encoding="utf-8")).get("fusion") or {}
                                    sc = float(fus.get("total_score") or 0.0)
                                    tier = str(fus.get("tier") or "B-TIER")
                                except Exception:
                                    pass
                            if tier in AUTO_REVIEW_TIERS or sc >= 85.0:
                                candidates.append((sc, c_d))
                candidates.sort(key=lambda x: -x[0])
                out_reviews = []
                for _, c_d in candidates[:max_count]:
                    r = review_clip_as_human(c_d, force=force)
                    if r:
                        out_reviews.append({"clip_id": c_d.name, **r})
                self._send_json({
                    "status": "OK",
                    "reviewed_count": len(out_reviews),
                    "reviews": out_reviews,
                    "groq_usage": get_groq_usage_summary(),
                })
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        if path == "/api/clipper/stop":
            payload = self._read_json()
            ch = (payload.get("channel") or "").strip() or None
            self._send_json(stop_live_clipper(ch))
            return

        if path == "/api/clipper/approve":
            payload = self._read_json()
            channel = slugify(payload.get("channel") or "")
            clip_id = (payload.get("clip_id") or "").strip()
            approved = bool(payload.get("approved", True))
            if not channel or not clip_id or "/" in clip_id or ".." in clip_id:
                self._send_json({"error": "Valid channel and clip_id required"}, 400)
                return
            check_path = LIVE_CLIPS_DIR / channel / clip_id / "checklist.md"
            if not check_path.exists():
                self._send_json({"error": "Checklist not found"}, 404)
                return
            text = check_path.read_text(encoding="utf-8")
            text = re.sub(r"- \[ \]", "- [x]", text) if approved else re.sub(r"- \[x\]", "- [ ]", text, flags=re.I)
            check_path.write_text(text, encoding="utf-8")
            if approved:
                try:
                    fb = record_clip_feedback(check_path.parent, "approved", channel=channel)
                    log(f"Taste memory reinforced (+1 approved): {fb.get('family')}")
                except Exception:
                    pass
            log(f"Live clip '{channel}/{clip_id}' human approval set to {approved} (Rule 4)")
            self._send_json({"status": "UPDATED", "human_approved": approved, "taste_memory": get_taste_memory_summary()})
            return

        if path == "/api/clipper/delete":
            payload = self._read_json()
            channel = slugify(payload.get("channel") or "")
            clip_id = (payload.get("clip_id") or "").strip()
            if not channel or not clip_id or "/" in clip_id or "\\" in clip_id or ".." in clip_id:
                self._send_json({"error": "Valid channel and clip_id required"}, 400)
                return
            target_dir = (LIVE_CLIPS_DIR / channel / clip_id).resolve()
            if not str(target_dir).startswith(str(LIVE_CLIPS_DIR.resolve()) + os.sep) or not target_dir.is_dir():
                self._send_json({"error": "Clip not found"}, 404)
                return
            try:
                fb = record_clip_feedback(target_dir, "deleted", channel=channel)
                log(f"Taste memory recorded (-1 deleted): {fb.get('family')}")
            except Exception:
                pass
            freed_bytes = sum(f.stat().st_size for f in target_dir.rglob("*") if f.is_file())
            freed_mb = round(freed_bytes / (1024 * 1024), 2)
            # Move, never delete: keep the mp4 + sidecars so an accidental click is reversible.
            dest = DELETED_CLIPS_DIR / channel / clip_id
            if dest.exists():
                dest = dest.with_name(f"{clip_id}__{int(time.time())}")
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(target_dir), str(dest))
                (dest / "_deleted.json").write_text(
                    json.dumps({
                        "channel": channel,
                        "clip_id": clip_id,
                        "deleted_at": round(time.time(), 1),
                        "reason": str(payload.get("reason") or "dashboard-delete"),
                        "size_mb": freed_mb,
                        "restore_to": str(target_dir),
                    }, indent=2),
                    encoding="utf-8",
                )
            except Exception as exc:
                log(f"Could not move live clip '{channel}/{clip_id}' to trash: {exc}")
                self._send_json({"error": f"Delete failed: {exc}"}, 500)
                return
            log(f"Deleted live clip '{channel}/{clip_id}' -> trash {dest} ({freed_mb} MB kept recoverable)")
            self._send_json({
                "status": "DELETED",
                "channel": channel,
                "clip_id": clip_id,
                "freed_mb": 0.0,
                "kept_mb": freed_mb,
                "trash_path": str(dest.relative_to(STUDIO_ROOT)),
                "taste_memory": get_taste_memory_summary(),
            })
            return

        if path == "/api/clipper/restore":
            payload = self._read_json()
            channel = slugify(payload.get("channel") or "")
            clip_id = (payload.get("clip_id") or "").strip()
            if not channel or not clip_id or "/" in clip_id or "\\" in clip_id or ".." in clip_id:
                self._send_json({"error": "Valid channel and clip_id required"}, 400)
                return
            src = (DELETED_CLIPS_DIR / channel / clip_id).resolve()
            if not str(src).startswith(str(DELETED_CLIPS_DIR.resolve()) + os.sep) or not src.is_dir():
                self._send_json({"error": "Deleted clip not found in trash"}, 404)
                return
            dest = (LIVE_CLIPS_DIR / channel / clip_id).resolve()
            if not str(dest).startswith(str(LIVE_CLIPS_DIR.resolve()) + os.sep):
                self._send_json({"error": "Invalid restore path"}, 400)
                return
            if dest.exists():
                self._send_json({"error": "A live clip with that id already exists"}, 409)
                return
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dest))
                manifest = dest / "_deleted.json"
                if manifest.exists():
                    manifest.unlink()
            except Exception as exc:
                self._send_json({"error": f"Restore failed: {exc}"}, 500)
                return
            log(f"Restored live clip '{channel}/{clip_id}' from trash")
            self._send_json({"status": "RESTORED", "channel": channel, "clip_id": clip_id})
            return

        if path == "/api/youtube/credentials":
            try:
                payload = self._read_json()
                profile = (payload.get("profile") or "").strip() or None
                info = save_client_secret(payload, profile=profile)
                log(f"[YouTube] Saved Google Cloud OAuth credentials ({info.get('client_type')}, project={info.get('project_id')})")
                self._send_json({"status": "SAVED", "credentials": info, "youtube": get_youtube_status()})
            except Exception as exc:
                self._send_json({"error": str(exc)}, 400)
            return

        if path == "/api/youtube/auth/start":
            try:
                payload = self._read_json()
                redirect_uri = (payload.get("redirect_uri") or "").strip() or None
                profile = (payload.get("profile") or "studio").strip()
                data = build_oauth_url(redirect_uri=redirect_uri, profile=profile)
                log(f"[YouTube:{data['profile']}] Generated OAuth login link (callback: {data['redirect_uri']})")
                self._send_json(data)
            except Exception as exc:
                self._send_json({"error": str(exc)}, 400)
            return

        if path == "/api/youtube/disconnect":
            payload = self._read_json()
            profile = (payload.get("profile") or "studio").strip()
            res = disconnect_youtube(profile=profile)
            log(f"[YouTube:{res['profile']}] Disconnected YouTube channel & cleared saved token.")
            self._send_json(res)
            return

        if path == "/api/youtube/preview-metadata":
            try:
                payload = self._read_json()
                target = (payload.get("target") or payload.get("slug") or payload.get("clip_id") or "").strip()
                if not target:
                    self._send_json({"error": "target is required"}, 400)
                    return
                meta = build_upload_metadata(
                    target,
                    target_type=payload.get("type"),
                    channel=payload.get("channel"),
                    overrides=payload.get("overrides"),
                )
                self._send_json(meta)
            except Exception as exc:
                self._send_json({"error": str(exc)}, 400)
            return

        if path == "/api/youtube/upload":
            try:
                payload = self._read_json()
                job = start_youtube_upload(payload)
                self._send_json({"status": "STARTED", "job": job})
            except PermissionError as exc:
                self._send_json({"error": str(exc), "code": "RULE4_APPROVAL_REQUIRED"}, 403)
            except Exception as exc:
                self._send_json({"error": str(exc)}, 400)
            return

        self._send_json({"error": "Not found"}, 404)


def main():
    port = PORT
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass

    hw = probe_hardware()
    styles = get_styles_catalog()
    skills = count_skills()
    log(
        f"CreatorRadar Studio API v2 ready on http://127.0.0.1:{port} | "
        f"GPU: {hw.get('gpu') or 'CPU'} (NVENC={'ON' if hw.get('nvenc') else 'OFF'}) | "
        f"{len(skills)} skills | {len(styles)} styles"
    )
    httpd = ThreadingHTTPServer(("127.0.0.1", port), StudioAPIHandler)
    try:
        ensure_publish_scheduler()
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down Studio API.")


if __name__ == "__main__":
    main()
