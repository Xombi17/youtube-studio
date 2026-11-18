#!/usr/bin/env python3
"""
CreatorRadar Live Stream Viral Clipper Agent (v2 — Multimodal Highlight Model)
Watches live Twitch and YouTube streams (or local videos/VODs), detects viral
moments via 5 fused signals + cross-modal synergy, and automatically clips
30s BEFORE chat explosions (accounting for stream + human reaction latency)
into 9:16 Shorts with word-level kinetic captions via Cactus Whistle & NVENC.

Multimodal Virality Model (0-100):
  1. Live Chat Explosion (Twitch IRC + YouTube pytchat, 0-55 pts):
     - Rolling Median + MAD z-score (5s micro-window vs 3-min baseline)
     - Chat velocity acceleration (catches leading edge of explosions)
     - Unique-chatter diversity (ignores 1-person spam)
     - 7TV/BTTV/Twitch/YouTube hype emotes, emojis, ALL-CAPS & elongated words
     - SuperChat / Membership boost (YouTube Live)
     - Tech-complaint damping (ignores "lag", "mic muted", "ads" spikes)
  2. Acoustic Emotion DSP (0-35 pts):
     - RMS loudness z-score + 0.5s shout/laugh burst ratio
     - Vocal excitement band (2-6 kHz spectral ratio vs low bass rumble)
     - Silence-to-explosion contrast (quiet tension -> sudden pop-off)
  3. Visual Motion & Scene-Cut Energy (0-18 pts):
     - Low-res 1 fps frame differencing + scene flash/cut ratio
  4. Cactus-Compute/whistle ASR + 7-Category Viral Lexicon (0-40 pts):
     - 16.9 MB local CPU model with word timestamps (0 GPU VRAM used)
     - 7 weighted viral categories in config/clipper-signals.json + custom --keywords
     - Streamer speech-rate surge vs personal rolling words-per-second baseline
  5. Cross-Modal Synergy & False-Positive Damping (-12 to +22 pts):
     - Chat Explosion + Audio Peak -> +20 synergy bonus
     - Chat Explosion + Visual Chaos -> +12 synergy bonus
     - Audio spike alone while active chat is silent -> -12 penalty (filters ads/cutscenes)

Smart Clip Windowing:
  - Chat-triggered clips look back 30s BEFORE the chat peak (--chat-pre-pad 30)
    to cover 5-10s stream/reaction delay + 20s buildup, plus 12s post-reaction.
  - Dynamic Peak Extension: if the next segment escalates higher, extends clip window
    up to --max-clip-sec (60s) instead of chopping mid-climax.
  - Whistle Sentence-Boundary Snap: trims leading dead-air / cut-off half-words.

Studio Rules Compliance:
  - Rule 4: Never auto-uploads. Saves MP4 + metadata.md + checklist.md for human review.
  - Rule 5: Logs stream attribution & clip-rights clearance checkbox.
"""

import argparse
import collections
import datetime
import io
import json
import math
import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import numpy as np
import soundfile as sf
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"
# The repo root must be importable for `from scripts.<module> import ...` (Groq batch review,
# human reviewer, uploader, metadata builder). Without it every such import fails silently in
# the try/except guards and reviews simply never run.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from caption_polisher import polish_and_align_captions  # noqa: E402

CONFIG_SIGNALS_PATH = ROOT / "config" / "clipper-signals.json"
RENDERS_BUFFER_DIR = ROOT / "renders" / "live_buffer"
LIVE_STATE_FILE = RENDERS_BUFFER_DIR / "live_clipper_state.json"
EXPORTS_CLIPS_DIR = ROOT / "exports" / "live-clips"
EXPORTS_QUARANTINE_DIR = ROOT / "exports" / "live-clips-quarantine"
HOOKSCORE_SCRIPT = ROOT / "skills" / "yt-script" / "hookscore.py"


def quarantine_clip(out_dir: Path, reason: str, score: float | None = None) -> Path | None:
    """Move a rendered clip out of exports/live-clips without destroying it.

    The dashboard hides anything outside `exports/live-clips`, so a quarantined clip stops
    showing up as a publishable reel, yet the MP4 still exists if the score was wrong.
    """
    out_dir = Path(out_dir)
    if not out_dir.is_dir():
        return None
    dest = EXPORTS_QUARANTINE_DIR / out_dir.parent.name / out_dir.name
    if dest.exists():
        dest = EXPORTS_QUARANTINE_DIR / out_dir.parent.name / f"{out_dir.name}_{int(time.time())}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(out_dir), str(dest))

    index = EXPORTS_QUARANTINE_DIR / "index.jsonl"
    record = {
        "clip_id": out_dir.name,
        "channel": out_dir.parent.name,
        "score": score,
        "reason": reason,
        "quarantined_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "path": str(dest),
    }
    try:
        with open(index, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except Exception:
        pass
    return dest


def prune_old_exported_clips(channel_dir: Path, max_keep: int = 20) -> int:
    """Prune oldest unapproved clips in channel_dir on the go so count does not exceed max_keep."""
    channel_dir = Path(channel_dir)
    if not channel_dir.is_dir() or max_keep <= 0:
        return 0
    try:
        clip_dirs = [p for p in channel_dir.iterdir() if p.is_dir()]
        if len(clip_dirs) <= max_keep:
            return 0

        # Sort oldest first by filesystem creation/modification time
        clip_dirs.sort(key=lambda p: p.stat().st_mtime)

        excess = len(clip_dirs) - max_keep
        deleted = 0
        for cd in clip_dirs:
            if deleted >= excess:
                break
            # Protect human_approved or staged/uploaded clips
            is_protected = False
            moment_f = cd / "moment.json"
            if moment_f.exists():
                try:
                    meta = json.loads(moment_f.read_text(encoding="utf-8"))
                    if meta.get("human_approved") or meta.get("staged") or meta.get("uploaded"):
                        is_protected = True
                except Exception:
                    pass

            if is_protected:
                continue

            try:
                shutil.rmtree(cd, ignore_errors=True)
                print(f"  [Cleanup] Pruned old clip {cd.name} on the go (limit={max_keep})", flush=True)
                deleted += 1
            except Exception as e:
                print(f"  [Cleanup] Failed to prune {cd.name}: {e}", flush=True)
        return deleted
    except Exception as exc:
        print(f"  [Cleanup] Pruning error in {channel_dir}: {exc}", flush=True)
        return 0


def auto_review_tier_clips(dirs, tag: str = "AutoReview") -> int:
    """Run the simulated human viewer on every A/S-tier clip that has no cached review.

    Reads the tier from moment.json (never the folder label), so a clip re-scored below the
    gate after Groq review is skipped. Cached reviews cost zero API calls.
    """
    from scripts.human_clip_reviewer import needs_human_review, review_clip_as_human

    reviewed = 0
    for cdir in list(dirs):
        cdir = Path(cdir)
        try:
            if not needs_human_review(cdir):
                continue
            rev = review_clip_as_human(cdir)
            if rev:
                reviewed += 1
                print(
                    f"  [{tag}] {cdir.name}: {rev.get('verdict')} "
                    f"({rev.get('human_score')}/100) — {rev.get('gut_reaction')}",
                    flush=True,
                )
        except Exception as exc:
            print(f"  [{tag}] {cdir.name} failed: {exc}", flush=True)
    return reviewed


def write_live_state(state: dict, state_file: Path = LIVE_STATE_FILE):
    """Atomically persist live telemetry for the Next.js Live Clipper Web Dashboard (supports multi-stream)."""
    try:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = state_file.with_suffix(".tmp.json")
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        tmp.replace(state_file)
    except Exception:
        pass


def load_signal_config() -> dict:
    if CONFIG_SIGNALS_PATH.exists():
        return json.loads(CONFIG_SIGNALS_PATH.read_text(encoding="utf-8"))
    return {
        "timing": {
            "segment_sec": 10,
            "chat_pre_pad_sec": 30,
            "audio_pre_pad_sec": 20,
            "post_pad_sec": 12,
            "max_clip_sec": 60,
            "cooldown_sec": 45,
        },
        "transcript_categories": {},
        "chat_hype_tokens": ["kekw", "lul", "pog", "clip", "wtf", "omg", "insane", "clutch", "w"],
        "chat_hype_emojis": ["💀", "😭", "🔥", "😂", "😱"],
        "chat_noise_complaints": ["lag", "muted", "no audio", "buffering", "ads"],
    }


def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return s[:48] or "stream"


def detect_nvenc() -> bool:
    try:
        probe = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.1",
                "-c:v", "h264_nvenc", "-f", "null", "-",
            ],
            capture_output=True,
            timeout=8,
        )
        return probe.returncode == 0
    except Exception:
        return False


def extract_twitch_channel(url: str) -> str | None:
    m = re.search(r"twitch\.tv/([a-zA-Z0-9_]+)", url, re.I)
    if m:
        ch = m.group(1).lower()
        if ch not in ("videos", "directory", "downloads", "settings", "clip"):
            return ch
    return None


def extract_youtube_video_id(url: str) -> str | None:
    patterns = [
        r"(?:youtube\.com/watch\?.*?v=|youtu\.be/|youtube\.com/live/)([a-zA-Z0-9_-]{11})",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def resolve_stream_url(url: str, quality: str = "best", retries: int = 3) -> str:
    """Resolve direct live HLS media URL via streamlink or yt-dlp (with automatic retry on CDN blips)."""
    streamlink_bin = str(ROOT / ".venv" / "bin" / "streamlink")
    if not Path(streamlink_bin).exists():
        streamlink_bin = shutil.which("streamlink") or ""
    ytdlp_bin = shutil.which("yt-dlp") or str(Path.home() / ".local" / "bin" / "yt-dlp")

    for attempt in range(retries):
        if streamlink_bin:
            try:
                res = subprocess.run(
                    [streamlink_bin, "--stream-url", url, quality],
                    capture_output=True,
                    text=True,
                    timeout=25,
                )
                if res.returncode == 0 and res.stdout.strip().startswith("http"):
                    return res.stdout.strip().splitlines()[0]
            except Exception:
                pass

        if Path(ytdlp_bin).exists():
            try:
                cmd = [ytdlp_bin, "--no-warnings", "--js-runtimes", "node", "-g", "-f", "best[height<=1080][acodec!=none]/best[height<=1080]/best", url]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if res.returncode == 0 and res.stdout.strip():
                    return res.stdout.strip().splitlines()[0]
            except Exception:
                pass

        if attempt + 1 < retries:
            time.sleep(2.5)

    raise RuntimeError(
        f"Could not resolve live stream URL for {url}. Confirm the stream is currently live."
    )


class BaseChatMonitor:
    """
    Shared rolling chat explosion, weird/glitch radar, and SuperChat/Twitch Bits monitor:
      - Median + MAD z-score velocity, acceleration, unique-chatter diversity
      - Hype emote/CAPS density + technical-complaint filtering
      - Weirdness / Wonky Glitch chat bucket (AYO, PAUSE, SUS, GLITCH, BUG, RAGDOLL, 💀)
      - Paid SuperChat / Twitch Bits / Donation bot parser with weirdness scoring
        and a 15-second reaction watch window so we capture BOTH the dono & streamer reaction!
    """

    def __init__(self, cfg: dict):
        self.hype_tokens = set(t.lower() for t in cfg.get("chat_hype_tokens", []))
        self.hype_emojis = tuple(cfg.get("chat_hype_emojis", []))
        self.weird_tokens = set(t.lower() for t in cfg.get("chat_weird_glitch_tokens", []))
        self.weird_emojis = tuple(cfg.get("chat_weird_glitch_emojis", []))
        self.weird_dono_cues = tuple(p.lower() for p in cfg.get("weird_dono_cues", []))
        self.noise_phrases = tuple(p.lower() for p in cfg.get("chat_noise_complaints", []))
        # Each event: (timestamp, author, is_hype, is_caps_or_elongated, is_noise, is_paid, is_weird, weird_hit_list)
        self.events: collections.deque[tuple[float, str, bool, bool, bool, bool, bool, list[str]]] = collections.deque(maxlen=8000)
        # Paid events: dict(ts, author, msg, amount_str, amount_num, source, weird_score, cues)
        self.paid_events: collections.deque[dict] = collections.deque(maxlen=200)
        self.dono_watch_until: float = 0.0
        self.baseline_rates: collections.deque[float] = collections.deque(maxlen=90)
        self.prev_rate: float = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.connected = False
        self.platform = "none"
        self.on_message_callbacks: list = []

    def score_weird_donation(self, msg: str, amount_num: float = 0.0) -> tuple[float, list[str]]:
        """Score a SuperChat / Twitch Bits / TTS donation (0-100) for weird/unhinged/clip-worthy bait."""
        clean = re.sub(r"\s+", " ", (msg or "")).strip()
        low = clean.lower()
        cues = [c for c in self.weird_dono_cues if re.search(rf"(?<!\w){re.escape(c)}(?!\w)", low)]
        score = 18.0  # baseline for any real paid message
        if len(clean) >= 18:
            score += 10.0  # actual readable message/roast instead of "hi"
        if "?" in clean:
            score += 10.0  # bait question / challenge to the streamer
        if cues:
            score += min(45.0, 22.0 + (len(cues) - 1) * 12.0)
        if any(e in clean for e in self.weird_emojis):
            score += 10.0
        if amount_num >= 20.0 or amount_num >= 1000.0:  # big dollar dono / 1000+ bits / big INR superchat
            score += 14.0
        elif amount_num >= 5.0 or amount_num >= 300.0:
            score += 7.0
        return round(min(100.0, score), 1), cues[:5]

    def record_paid_event(
        self,
        author: str,
        msg: str,
        amount_str: str = "",
        amount_num: float = 0.0,
        source: str = "paid",
    ):
        now = time.time()
        weird_score, cues = self.score_weird_donation(msg, amount_num=amount_num)
        ev = {
            "ts": round(now, 2),
            "author": author,
            "msg": re.sub(r"\s+", " ", (msg or "")).strip()[:220],
            "amount_str": amount_str,
            "amount_num": amount_num,
            "source": source,
            "weird_score": weird_score,
            "cues": cues,
        }
        with self._lock:
            self.paid_events.append(ev)
            # Open 15-second reaction watch window so we capture the streamer's reaction to the dono!
            watch_sec = 18.0 if weird_score >= 42.0 else 12.0
            self.dono_watch_until = max(self.dono_watch_until, now + watch_sec)

    def record_message(self, author: str, msg: str, is_paid: bool = False):
        now = time.time()
        low = msg.lower().strip()
        words = set(re.findall(r"[a-z0-9']+", low))

        weird_hits = sorted(words & self.weird_tokens)
        has_weird_emoji = any(e in msg for e in self.weird_emojis)
        is_weird = bool(weird_hits) or has_weird_emoji

        has_hype_word = bool(words & self.hype_tokens) or any(e in msg for e in self.hype_emojis) or is_weird
        # Elongated hype like "NOOOOO", "WWWWWW", "AHAHAHA", "????"
        elongated = bool(re.search(r"(.)\1{3,}", low)) or "???" in msg or "!!!" in msg
        alpha = [c for c in msg if c.isalpha()]
        is_caps = len(alpha) >= 4 and (sum(1 for c in alpha if c.isupper()) / len(alpha)) >= 0.72
        is_noise = any(np_phrase in low for np_phrase in self.noise_phrases) and not has_hype_word

        with self._lock:
            self.events.append((now, author.lower(), has_hype_word, is_caps or elongated, is_noise, is_paid, is_weird, weird_hits[:3]))

        for cb in self.on_message_callbacks:
            try:
                cb(author, msg)
            except Exception:
                pass

    def sample_window_score(self, window_sec: float = 10.0) -> dict:
        now = time.time()
        cutoff = now - window_sec
        micro_cutoff = now - min(5.0, window_sec)
        dono_cutoff = now - 16.0  # Keep recent SuperChats/Bits visible through the 15s reaction window

        with self._lock:
            win = [e for e in self.events if e[0] >= cutoff]
            micro = [e for e in win if e[0] >= micro_cutoff]
            recent_paid = [p for p in self.paid_events if p["ts"] >= dono_cutoff]
            dono_watch_active = now <= self.dono_watch_until

        total_msgs = len(win)
        unique_authors = len({e[1] for e in win})
        hype_msgs = sum(1 for e in win if e[2])
        shout_msgs = sum(1 for e in win if e[3])
        noise_msgs = sum(1 for e in win if e[4])
        paid_msgs = sum(1 for e in win if e[5])
        weird_msgs = sum(1 for e in win if e[6])

        weird_tok_counts: collections.Counter[str] = collections.Counter()
        for e in win:
            for tok in e[7]:
                weird_tok_counts[tok] += 1
        weird_tokens_hit = [tok for tok, _ in weird_tok_counts.most_common(6)]

        rate = total_msgs / max(1.0, window_sec)
        micro_rate = len(micro) / max(1.0, min(5.0, window_sec))
        peak_rate = max(rate, micro_rate)

        # Robust rolling Median + MAD (resists single-spike distortion of baseline)
        if len(self.baseline_rates) >= 5:
            arr = np.array(self.baseline_rates, dtype=float)
            med = float(np.median(arr))
            mad = float(np.median(np.abs(arr - med)))
            robust_sd = max(0.35, 1.4826 * mad)
            mad_z = (peak_rate - med) / robust_sd
        else:
            med = max(0.4, rate)
            mad_z = 0.0

        accel = peak_rate - self.prev_rate
        self.prev_rate = peak_rate
        self.baseline_rates.append(rate)

        ratio = peak_rate / max(0.25, med)
        hype_ratio = (hype_msgs + 0.5 * shout_msgs) / max(1, total_msgs)
        weird_ratio = weird_msgs / max(1, total_msgs)
        noise_ratio = noise_msgs / max(1, total_msgs)
        diversity = unique_authors / max(1, total_msgs)

        # Weird/Glitch chat spike: chat flooding AYO / PAUSE / SUS / GLITCH / BUG / 💀
        is_weird_spike = (weird_msgs >= 4 and weird_ratio >= 0.22 and unique_authors >= 4) or (weird_msgs >= 8 and unique_authors >= 5)

        top_weird_dono = max(recent_paid, key=lambda x: x.get("weird_score", 0.0)) if recent_paid else None
        max_dono_weird = float(top_weird_dono.get("weird_score", 0.0)) if top_weird_dono else 0.0

        # Explosion requires genuine crowd activity (>= 5 unique chatters or paid hype or weird spike)
        score = 0.0
        is_explosion = False
        if unique_authors >= 5 or paid_msgs >= 1 or recent_paid or is_weird_spike:
            z_pts = max(0.0, min(24.0, (mad_z - 1.2) * 6.5))
            ratio_pts = max(0.0, min(16.0, (ratio - 1.6) * 7.5))
            accel_pts = max(0.0, min(8.0, accel * 2.5)) if accel > 0.5 else 0.0
            hype_pts = min(13.0, hype_ratio * 20.0)
            weird_pts = min(16.0, (weird_ratio * 26.0) + (6.0 if is_weird_spike else 0.0)) if weird_msgs >= 3 else 0.0
            paid_pts = min(18.0, paid_msgs * 5.0 + (max_dono_weird * 0.20 if top_weird_dono else 0.0))

            raw_score = z_pts + ratio_pts + accel_pts + hype_pts + weird_pts + paid_pts

            if diversity < 0.45 and not recent_paid:
                raw_score *= 0.45
            if noise_ratio > 0.40:
                raw_score *= 0.15

            score = min(58.0, raw_score)
            is_explosion = (score >= 24.0) or (ratio >= 2.8 and unique_authors >= 6 and noise_ratio < 0.35)

        return {
            "platform": self.platform,
            "connected": self.connected,
            "active_chat": (len(self.baseline_rates) >= 5 and med >= 0.4),
            "msgs_in_window": total_msgs,
            "unique_authors": unique_authors,
            "hype_msgs": hype_msgs,
            "shout_msgs": shout_msgs,
            "noise_msgs": noise_msgs,
            "paid_msgs": max(paid_msgs, len(recent_paid)),
            "weird_glitch_msgs": weird_msgs,
            "weird_glitch_ratio": round(weird_ratio, 3),
            "weird_tokens_hit": weird_tokens_hit,
            "is_weird_spike": is_weird_spike,
            "dono_watch_active": dono_watch_active,
            "top_weird_dono": top_weird_dono,
            "paid_events": recent_paid[-4:],
            "peak_rate": round(peak_rate, 2),
            "baseline_median": round(med, 2),
            "ratio": round(ratio, 2),
            "mad_z": round(mad_z, 2),
            "is_explosion": is_explosion,
            "score": round(score, 1),
        }

    def stop(self):
        self._stop.set()


def _parse_twitch_irc_tags(raw_tags: str) -> dict[str, str]:
    tags: dict[str, str] = {}
    for pair in raw_tags.lstrip("@").split(";"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            tags[k] = v.replace("\\s", " ").replace("\\:", ";")
    return tags


_DONO_BOT_AUTHORS = {"streamelements", "streamlabs", "nightbot", "moobot", "fossabot", "donationalerts"}
_DONO_BOT_RE = re.compile(
    r"(?:donated|tipped|cheered|sent)\s+([$€£₹]\s?\d+(?:[.,]\d+)?|\d+\s*(?:bits|inr|usd|rupees))",
    flags=re.I,
)


class TwitchChatMonitor(BaseChatMonitor):
    """
    Anonymous read-only Twitch IRCv3 monitor (zero auth):
      - Requests `twitch.tv/tags` + `twitch.tv/commands` to capture live Bits/Cheers,
        Subs/Resubs/Gifted Subs (`USERNOTICE`), and StreamElements/Streamlabs donation alerts!
    """

    def __init__(self, channel: str, cfg: dict):
        super().__init__(cfg)
        self.channel = channel.lower().lstrip("#")
        self.platform = "twitch"
        self._thread: threading.Thread | None = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            sock = None
            try:
                sock = socket.create_connection(("irc.chat.twitch.tv", 6667), timeout=15)
                nick = f"justinfan{int(time.time()) % 90000 + 10000}"
                sock.sendall(
                    (
                        "CAP REQ :twitch.tv/tags twitch.tv/commands\r\n"
                        f"NICK {nick}\r\n"
                        f"JOIN #{self.channel}\r\n"
                    ).encode("utf-8")
                )
                sock.settimeout(5.0)
                self.connected = True
                buf = ""
                while not self._stop.is_set():
                    try:
                        chunk = sock.recv(4096).decode("utf-8", errors="ignore")
                    except socket.timeout:
                        continue
                    if not chunk:
                        break
                    buf += chunk
                    while "\r\n" in buf:
                        line, buf = buf.split("\r\n", 1)
                        if line.startswith("PING"):
                            sock.sendall(b"PONG :tmi.twitch.tv\r\n")
                            continue

                        tags: dict[str, str] = {}
                        body = line
                        if line.startswith("@"):
                            raw_tags, _, body = line.partition(" ")
                            tags = _parse_twitch_irc_tags(raw_tags)

                        if " PRIVMSG " in body:
                            prefix, _, rest = body.partition(" PRIVMSG ")
                            author = tags.get("display-name") or prefix.split("!", 1)[0].lstrip(":") or "anon"
                            msg = rest.split(" :", 1)[-1] if " :" in rest else ""

                            bits_val = 0
                            try:
                                bits_val = int(tags.get("bits") or 0)
                            except ValueError:
                                bits_val = 0

                            # Strip cheer emote tokens (e.g. Cheer100) to check if viewer wrote an actual readable message
                            clean_bits_msg = re.sub(r"\b[a-z]+\d+\b", "", msg, flags=re.I).strip()
                            is_paid = bits_val >= 100 and len(clean_bits_msg) >= 12
                            if is_paid:
                                self.record_paid_event(
                                    author=author,
                                    msg=clean_bits_msg,
                                    amount_str=f"{bits_val} Bits",
                                    amount_num=float(bits_val) / 100.0,
                                    source="twitch_bits",
                                )
                            elif author.lower() in _DONO_BOT_AUTHORS:
                                dm = _DONO_BOT_RE.search(msg)
                                if dm and len(msg.strip()) >= 16:
                                    is_paid = True
                                    amt_s = dm.group(1)
                                    num_m = re.search(r"\d+(?:\.\d+)?", amt_s)
                                    self.record_paid_event(
                                        author=author,
                                        msg=msg,
                                        amount_str=amt_s,
                                        amount_num=float(num_m.group(0)) if num_m else 5.0,
                                        source="twitch_dono_bot",
                                    )
                            self.record_message(author, msg, is_paid=is_paid)

                        elif " USERNOTICE " in body:
                            msg_id = (tags.get("msg-id") or "").lower()
                            # ONLY track resubs where the viewer actually typed a custom message (ignore auto sub-gifts/raids!)
                            if msg_id == "resub":
                                _, _, rest = body.partition(" USERNOTICE ")
                                user_msg = (rest.split(" :", 1)[-1] if " :" in rest else "").strip()
                                if len(user_msg) >= 14:
                                    author = tags.get("display-name") or tags.get("login") or "subscriber"
                                    months = tags.get("msg-param-cumulative-months") or ""
                                    amt_lbl = f"{months}mo Resub" if months else "Resub"
                                    self.record_paid_event(
                                        author=author,
                                        msg=user_msg,
                                        amount_str=amt_lbl,
                                        amount_num=5.0,
                                        source="twitch_resub",
                                    )
                                    self.record_message(author, user_msg, is_paid=True)
            except Exception:
                self.connected = False
                time.sleep(5)
            finally:
                if sock:
                    try:
                        sock.close()
                    except Exception:
                        pass


class YouTubeChatMonitor(BaseChatMonitor):
    """Live YouTube chat & SuperChat weirdness monitor via pytchat (no API key required)."""

    def __init__(self, video_id: str, cfg: dict):
        super().__init__(cfg)
        self.video_id = video_id
        self.platform = "youtube"
        self._thread: threading.Thread | None = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        try:
            import pytchat
        except ImportError:
            self.connected = False
            return

        while not self._stop.is_set():
            chat = None
            try:
                chat = pytchat.create(video_id=self.video_id, interruptable=False)
                self.connected = True
                while not self._stop.is_set() and chat.is_alive():
                    for item in chat.get().sync_items():
                        author = getattr(item.author, "name", "yt_user") or "yt_user"
                        msg = getattr(item, "message", "") or ""
                        item_type = getattr(item, "type", "") or ""
                        is_paid = item_type == "superChat" and len(msg.strip()) >= 8
                        if is_paid:
                            amount_str = str(getattr(item, "amountString", "") or "SuperChat")
                            try:
                                amount_val = float(getattr(item, "amountValue", 0.0) or 0.0)
                            except (TypeError, ValueError):
                                amount_val = 5.0
                            self.record_paid_event(
                                author=author,
                                msg=msg,
                                amount_str=amount_str,
                                amount_num=amount_val,
                                source=f"youtube_{item_type}",
                            )
                        self.record_message(author, msg, is_paid=is_paid)
                    time.sleep(0.5)
            except Exception:
                self.connected = False
                time.sleep(5)
            finally:
                if chat:
                    try:
                        chat.terminate()
                    except Exception:
                        pass


class ASRManager:
    """
    Unified local + Modal serverless ASR router:
      - 'modal': Remote NVIDIA T4 GPU on Modal (modal_workers/studio_gpu.py) -> 0% laptop GPU!
      - 'hinglish' (default): Local Oriserve/Whisper-Hindi2Hinglish-Apex (CUDA FP16, 1.62GB)
      - 'whisper': Local openai/whisper-small (CUDA FP16, multilingual)
      - 'whistle': Local 16.9 MB Cactus-Compute/whistle CPU model (7 European languages)
    """

    def __init__(self, backend: str = "hinglish", model_id: str | None = None, language: str = "auto"):
        self.backend = backend
        self._modal_cls = None
        if model_id:
            self.model_id = model_id
        elif backend == "hinglish":
            self.model_id = "Oriserve/Whisper-Hindi2Hinglish-Apex"
        else:
            self.model_id = "openai/whisper-small"
        self.language = language
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self.engine_label = "cactus-whistle"

        if backend == "modal":
            try:
                import modal

                self._modal_cls = modal.Cls.from_name("creatorradar-gpu", "HinglishASR")()
                self.engine_label = "Modal T4 · Whisper-Hinglish-Apex"
                print("[ASR] Connected to Modal Cloud GPU (creatorradar-gpu / HinglishASR) — 0% laptop GPU!", flush=True)
                return
            except Exception as e:
                print(
                    f"[ASR] Modal GPU not connected ({e}). Run '.venv/bin/modal setup && .venv/bin/modal deploy modal_workers/studio_gpu.py'. "
                    "Falling back to local Hinglish-Apex...",
                    flush=True,
                )
                self.backend = "hinglish"
                self.model_id = "Oriserve/Whisper-Hindi2Hinglish-Apex"

        vs_py = ROOT / "VoiceStudio" / ".venv" / "bin" / "python"
        worker_script = ROOT / "scripts" / "whisper_asr_worker.py"
        if self.backend in ("hinglish", "whisper") and vs_py.exists() and worker_script.exists():
            try:
                print(f"[ASR] Loading persistent CUDA Whisper worker ({self.model_id}, lang={language})...", flush=True)
                self._proc = subprocess.Popen(
                    [str(vs_py), str(worker_script), "--model", self.model_id, "--language", language],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    bufsize=1,
                )
                assert self._proc.stdout is not None
                for _ in range(25):
                    ready_line = self._proc.stdout.readline()
                    if not ready_line:
                        break
                    s = ready_line.strip()
                    if s.startswith("{"):
                        meta = json.loads(s)
                        if meta.get("ready"):
                            self.engine_label = meta.get("engine", "whisper-cuda")
                            print(f"[ASR] Ready: {self.engine_label}", flush=True)
                            return
                raise RuntimeError("Whisper worker failed to send ready handshake")
            except Exception as e:
                print(f"[ASR] Whisper worker unavailable ({e}); falling back to Cactus Whistle.", flush=True)
                self.close()
                self.backend = "whistle"
        else:
            self.backend = "whistle"

    def transcribe(self, wav_16k_path: Path) -> dict:
        if self.backend == "modal" and self._modal_cls is not None:
            try:
                wav_bytes = wav_16k_path.read_bytes()
                data = self._modal_cls.transcribe_wav_bytes.remote(wav_bytes, self.language)
                if isinstance(data, dict) and data.get("ok"):
                    return {
                        "engine": data.get("engine", self.engine_label),
                        "text": data.get("text", ""),
                        "raw_text": data.get("raw_text", ""),
                        "words": data.get("words", []),
                    }
            except Exception as e:
                print(f"[ASR] Modal remote call error ({e}); falling back to Whistle for this chunk.", flush=True)
        if self.backend in ("hinglish", "whisper") and self._proc and self._proc.poll() is None:
            with self._lock:
                try:
                    assert self._proc.stdin and self._proc.stdout
                    req = json.dumps({"wav": str(wav_16k_path.resolve()), "language": self.language})
                    self._proc.stdin.write(req + "\n")
                    self._proc.stdin.flush()
                    for _ in range(15):
                        resp_line = self._proc.stdout.readline()
                        if not resp_line:
                            break
                        s = resp_line.strip()
                        if s.startswith("{"):
                            data = json.loads(s)
                            if data.get("ok"):
                                return {
                                    "engine": data.get("engine", self.engine_label),
                                    "text": data.get("text", ""),
                                    "raw_text": data.get("raw_text", ""),
                                    "words": data.get("words", []),
                                }
                            break
                except Exception:
                    pass
        return transcribe_whistle(wav_16k_path)

    def close(self):
        if self._proc and self._proc.poll() is None:
            try:
                if self._proc.stdin:
                    self._proc.stdin.write(json.dumps({"cmd": "quit"}) + "\n")
                    self._proc.stdin.flush()
                self._proc.wait(timeout=3)
            except Exception:
                self._proc.kill()
        self._proc = None


def transcribe_whistle(wav_16k_path: Path) -> dict:
    """Transcribe 16kHz mono WAV via Cactus-Compute/whistle with exact word timestamps."""
    try:
        os.environ.setdefault("CACTUS_TELEMETRY", "0")
        import cactus

        res = cactus.transcribe(str(wav_16k_path), word_timestamps=True)
        text = (res.get("text") or "").strip()
        raw_words = res.get("words") or []
        words = []
        for w in raw_words:
            if isinstance(w, dict):
                token = str(w.get("word") or w.get("text") or "").strip()
                if not token:
                    continue
                words.append({
                    "word": token,
                    "start": float(w.get("start", 0.0)),
                    "end": float(w.get("end", w.get("start", 0.0) + 0.15)),
                    "probability": float(w.get("probability", w.get("prob", 1.0))),
                })
        return {"engine": "cactus-whistle", "text": text, "words": words}
    except Exception as e:
        return {"engine": f"unavailable ({e})", "text": "", "words": []}


def extract_wav_16k(media_path: Path, wav_out: Path) -> bool:
    res = subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(media_path),
            "-vn", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
            str(wav_out),
        ],
        capture_output=True,
    )
    return res.returncode == 0 and wav_out.exists()


def analyze_audio_emotion(wav_path: Path, rms_history: collections.deque[float]) -> dict:
    """
    Acoustic emotion DSP:
      - Rolling Median+MAD RMS loudness spike
      - 0.5s shout/laugh burst ratio
      - 2-6 kHz vocal excitement spectral ratio (separates human screams/laughs from bass rumble)
      - Silence-to-explosion dynamic contrast
    """
    data, sr = sf.read(str(wav_path), dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)
    if len(data) < sr // 4:
        return {
            "rms_db": -90.0, "peak_db": -90.0, "mad_z": 0.0,
            "burst_ratio": 0.0, "vocal_excitement": 0.0, "contrast_db": 0.0, "score": 0.0,
        }

    rms = float(np.sqrt(np.mean(data ** 2)) + 1e-9)
    rms_db = 20.0 * math.log10(rms)
    peak_db = 20.0 * math.log10(float(np.max(np.abs(data)) + 1e-9))

    # 0.5-second sub-windows for burst & silence-to-explosion contrast
    win = max(1, sr // 2)
    frames = [data[i:i + win] for i in range(0, len(data) - win + 1, win)]
    sub_rms = np.array([float(np.sqrt(np.mean(f ** 2)) + 1e-9) for f in frames])
    sub_db = 20.0 * np.log10(sub_rms)
    burst_ratio = float(np.max(sub_rms) / (float(np.median(sub_rms)) + 1e-9))
    contrast_db = float(np.max(sub_db) - np.percentile(sub_db, 20))

    # Vocal excitement band (1.5 kHz - 5.5 kHz) vs low rumble (40 Hz - 400 Hz)
    fft_mag = np.abs(np.fft.rfft(data))
    freqs = np.fft.rfftfreq(len(data), d=1.0 / sr)
    high_band = float(np.mean(fft_mag[(freqs >= 1500) & (freqs <= 5500)]) + 1e-9)
    low_band = float(np.mean(fft_mag[(freqs >= 40) & (freqs <= 400)]) + 1e-9)
    vocal_excitement = high_band / low_band

    if len(rms_history) >= 4:
        arr = np.array(rms_history, dtype=float)
        med = float(np.median(arr))
        mad = max(1.2, 1.4826 * float(np.median(np.abs(arr - med))))
        mad_z = (rms_db - med) / mad
    else:
        mad_z = 0.0
    rms_history.append(rms_db)

    if rms_db < -42.0:
        score = 0.0
    else:
        z_pts = max(0.0, min(16.0, (mad_z - 0.6) * 7.5))
        burst_pts = max(0.0, min(10.0, (burst_ratio - 1.7) * 4.5))
        contrast_pts = max(0.0, min(6.0, (contrast_db - 10.0) * 0.5))
        vocal_pts = max(0.0, min(6.0, (vocal_excitement - 0.28) * 14.0))
        score = min(35.0, z_pts + burst_pts + contrast_pts + vocal_pts)

    return {
        "rms_db": round(rms_db, 2),
        "peak_db": round(peak_db, 2),
        "mad_z": round(mad_z, 2),
        "burst_ratio": round(burst_ratio, 2),
        "vocal_excitement": round(vocal_excitement, 3),
        "contrast_db": round(contrast_db, 1),
        "score": round(score, 1),
    }


def _crop_facecam_region(frame: np.ndarray, facecam_pos: str = "top-right") -> np.ndarray:
    """Slice out the streamer facecam corner (~28% width x 34% height) for isolated physical-antics detection."""
    h, w = frame.shape[:2]
    fh = max(8, int(h * 0.34))
    fw = max(12, int(w * 0.28))
    if facecam_pos == "top-left":
        return frame[:fh, :fw]
    if facecam_pos == "bottom-left":
        return frame[h - fh:, :fw]
    if facecam_pos == "bottom-right":
        return frame[h - fh:, w - fw:]
    return frame[:fh, w - fw:]


def analyze_visual_motion(
    media_path: Path,
    motion_history: collections.deque[float] | None = None,
    facecam_history: collections.deque[float] | None = None,
    facecam_pos: str = "top-right",
) -> dict:
    """
    Visual action + isolated facecam-antics detector (1 fps @ 160x90 grayscale, zero VRAM):
      - Full-frame pixel delta + MAD z-score for gameplay plays, chases, explosions
      - Isolated facecam corner delta + MAD z-score to detect chair-jumps, standing up,
        leaning into camera, or physical freakouts even when gameplay is calm!
    """
    empty = {
        "mean_delta": 0.0, "max_delta": 0.0, "scene_cuts": 0, "mad_z": 0.0,
        "facecam_delta": 0.0, "facecam_z": 0.0, "facecam_antics": False, "score": 0.0,
    }
    try:
        res = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-i", str(media_path),
                "-vf", "fps=1,scale=160:90,format=gray",
                "-f", "image2pipe", "-vcodec", "png", "-",
            ],
            capture_output=True,
            timeout=10,
        )
        raw = res.stdout
        if not raw:
            return empty

        sig = b"\x89PNG\r\n\x1a\n"
        chunks = [sig + c for c in raw.split(sig)[1:]]
        frames = []
        for ch in chunks:
            try:
                im = Image.open(io.BytesIO(ch))
                frames.append(np.asarray(im, dtype=np.float32) / 255.0)
            except Exception:
                continue

        if len(frames) < 2:
            return empty

        deltas = [float(np.mean(np.abs(frames[i] - frames[i - 1]))) for i in range(1, len(frames))]
        mean_d = float(np.mean(deltas))
        max_d = float(np.max(deltas))
        cuts = sum(1 for d in deltas if d >= 0.18)

        # Isolated facecam motion (catches Speed jumping/standing/freaking out on cam)
        fc_crops = [_crop_facecam_region(fr, facecam_pos) for fr in frames]
        fc_deltas = [float(np.mean(np.abs(fc_crops[i] - fc_crops[i - 1]))) for i in range(1, len(fc_crops))]
        fc_mean = float(np.mean(fc_deltas))
        fc_max = float(np.max(fc_deltas))

        mad_z = 0.0
        if motion_history is not None:
            if len(motion_history) >= 4:
                arr = np.array(motion_history, dtype=float)
                med = float(np.median(arr))
                mad = max(0.012, 1.4826 * float(np.median(np.abs(arr - med))))
                mad_z = (mean_d - med) / mad
            motion_history.append(mean_d)

        fc_z = 0.0
        if facecam_history is not None:
            if len(facecam_history) >= 4:
                arr = np.array(facecam_history, dtype=float)
                med = float(np.median(arr))
                mad = max(0.010, 1.4826 * float(np.median(np.abs(arr - med))))
                fc_z = (fc_mean - med) / mad
            facecam_history.append(fc_mean)

        fc_ratio = fc_mean / max(0.015, mean_d)
        facecam_antics = (
            (fc_z >= 2.2 and fc_mean >= 0.055)
            or (fc_ratio >= 1.95 and fc_mean >= 0.065 and fc_max >= 0.10)
        )

        motion_pts = max(0.0, min(14.0, (mean_d - 0.03) * 85.0))
        z_pts = max(0.0, min(10.0, (mad_z - 0.8) * 5.0))
        cut_pts = min(10.0, cuts * 3.5 + (4.0 if max_d >= 0.25 else 0.0))
        fc_pts = 9.0 if facecam_antics else max(0.0, min(5.0, (fc_z - 1.2) * 3.5))
        score = min(34.0, motion_pts + z_pts + cut_pts + fc_pts)

        return {
            "mean_delta": round(mean_d, 3),
            "max_delta": round(max_d, 3),
            "scene_cuts": cuts,
            "mad_z": round(mad_z, 2),
            "facecam_delta": round(fc_mean, 3),
            "facecam_z": round(fc_z, 2),
            "facecam_antics": facecam_antics,
            "score": round(score, 1),
        }
    except Exception:
        return empty


def score_transcript_v2(
    text: str,
    words: list[dict],
    duration_sec: float,
    cfg: dict,
    custom_keywords: list[str],
    wps_history: collections.deque[float],
) -> dict:
    if not text:
        return {
            "score": 0.0,
            "archetype": "SILENT / VISUAL",
            "matched_categories": {},
            "matched_keywords": [],
            "wps": 0.0,
            "wps_surge": 1.0,
        }

    low = text.lower()
    categories = cfg.get("transcript_categories", {})
    matched_categories: dict[str, list[str]] = {}
    cat_score = 0.0
    top_label = "SPEECH MOMENT"
    top_weight = 0.0

    for cat_key, cat_def in categories.items():
        hits = [
            p for p in cat_def.get("phrases", [])
            if re.search(rf"(?<!\w){re.escape(p.lower())}(?!\w)", low)
        ]
        if hits:
            matched_categories[cat_key] = hits
            w = float(cat_def.get("weight", 10))
            pts = w + min(w * 0.6, (len(hits) - 1) * (w * 0.4))
            cat_score += pts
            if pts > top_weight:
                top_weight = pts
                top_label = cat_def.get("label", cat_key.upper())

    matched_keywords = [
        k for k in custom_keywords
        if k and re.search(rf"(?<!\w){re.escape(k.lower())}(?!\w)", low)
    ]
    kw_pts = min(28.0, len(matched_keywords) * 16.0)
    if matched_keywords and top_weight < kw_pts:
        top_label = f"KEYWORD: {matched_keywords[0].upper()}"

    word_count = len(words) if words else len(text.split())
    wps = word_count / max(1.0, duration_sec)
    if len(wps_history) >= 4:
        base_wps = max(1.0, float(np.median(wps_history)))
        wps_surge = wps / base_wps
    else:
        wps_surge = 1.0
    if word_count >= 4:
        wps_history.append(wps)

    pace_pts = max(0.0, min(10.0, (wps_surge - 1.25) * 14.0))
    punct_pts = min(6.0, (text.count("!") + text.count("?")) * 2.5)

    total = min(40.0, cat_score + kw_pts + pace_pts + punct_pts)
    return {
        "score": round(total, 1),
        "archetype": top_label,
        "matched_categories": matched_categories,
        "matched_keywords": matched_keywords,
        "wps": round(wps, 2),
        "wps_surge": round(wps_surge, 2),
    }


_DONO_STOPWORDS = {
    "this", "that", "with", "from", "have", "your", "just", "what", "when", "where",
    "they", "them", "been", "will", "would", "could", "should", "about", "there",
    "their", "here", "like", "dont", "cant", "wont", "bro", "dude", "chat", "please",
    "thanks", "thank", "stream", "live", "playing", "game", "good", "very", "much",
    "tier", "subscribed", "gifted", "months", "month", "prime", "community",
}

_DONO_READ_CALLOUT_RE = re.compile(
    r"\b(?:super\s*chat|who\s+(?:sent|donated|typed)|thank\s+you\s+for\s+the\s+(?:\d+|five|ten|twenty|fifty|hundred|bits|dono|donation|super)|"
    r"thanks\s+for\s+the\s+(?:bits|dono|donation|super)|appreciate\s+the\s+(?:bits|dono|donation|super)|"
    r"for\s+the\s+(?:\d+\s*)?bits|read\s+that\s+again|what\s+did\s+he\s+(?:just\s+)?(?:say|send|donate))\b",
    flags=re.I,
)


def match_streamer_read_dono(transcript_text: str, paid_events: list[dict] | None) -> tuple[dict | None, str]:
    """
    Verify that the streamer ACTUALLY READ or acknowledged a paid SuperChat / Twitch Bits /
    resub message in speech — prevents false 'WEIRD SUPERCHAT' tags from unread chat spam.
    Returns (matched_dono_dict, match_reason) or (None, '').
    """
    if not transcript_text or not paid_events:
        return None, ""
    tx_low = re.sub(r"[^a-z0-9\s']", " ", transcript_text.lower())
    tx_words = {w for w in tx_low.split() if len(w) >= 4 and w not in _DONO_STOPWORDS}
    if not tx_words:
        return None, ""

    best_dono: dict | None = None
    best_overlap = 0
    best_reason = ""

    for ev in paid_events:
        msg = str(ev.get("msg") or "").strip()
        if len(msg) < 8:
            continue
        author = str(ev.get("author") or "").strip().lower()
        msg_low = re.sub(r"[^a-z0-9\s']", " ", msg.lower())
        msg_words = {w for w in msg_low.split() if len(w) >= 4 and w not in _DONO_STOPWORDS}

        overlap = tx_words & msg_words
        author_hit = len(author) >= 4 and (author in tx_low)
        # Require >= 2 meaningful content words matched OR (author named + 1 content word)
        if len(overlap) >= 2 or (author_hit and len(overlap) >= 1):
            score = len(overlap) + (2 if author_hit else 0)
            if score > best_overlap:
                best_overlap = score
                best_dono = ev
                best_reason = f"read_overlap:{','.join(sorted(overlap)[:3])}"

    if best_dono:
        return best_dono, best_reason

    # Fallback: explicit donation-read phrase spoken while a weird/high-score user-written paid message arrived
    if _DONO_READ_CALLOUT_RE.search(transcript_text):
        weird_cands = [e for e in paid_events if float(e.get("weird_score", 0.0)) >= 40.0 and len(str(e.get("msg") or "")) >= 12]
        if weird_cands:
            top = max(weird_cands, key=lambda x: float(x.get("weird_score", 0.0)))
            return top, "explicit_dono_callout"

    return None, ""


def fuse_multimodal_score(
    audio: dict,
    visual: dict,
    txt: dict,
    chat: dict,
    recent_audio_peak: float = 0.0,
    recent_visual_peak: float = 0.0,
    recent_txt_sum: float = 0.0,
    channel: str = "",
    transcript_text: str = "",
) -> dict:
    """
    Fuse all 4 modalities + Viral Style Blueprint + Self-Improving Taste Memory:
      1. Lag-aware Chat Explosion synergy (chat peaks 10-20s after scream/play)
      2. Streamer-Read Verified SuperChat / Twitch Bits synergy (ONLY when streamer reads it!)
      3. Chat AYO / SUS / GLITCH / BUG radar (catches wonky gameplay & weird moments)
      4. Isolated Facecam Antics (chair-jumps, camera freakouts even on static gameplay)
      5. Quiet-Chat Cool Moment & 30s Story/Comedy detection
      6. Adaptive Taste Memory multiplier learned from Approve / Upload / Delete actions!
    """
    a = audio["score"]
    v = visual["score"]
    t = txt["score"]
    c = chat["score"]
    eff_a = max(a, recent_audio_peak)
    eff_v = max(v, recent_visual_peak)

    synergy = 0.0
    reasons: list[str] = []
    cool_play = False
    cool_story = False

    matched_dono, dono_match_reason = match_streamer_read_dono(transcript_text, chat.get("paid_events"))
    dono_read_verified = matched_dono is not None
    if dono_read_verified:
        chat["dono_read_verified"] = True
        chat["matched_dono"] = matched_dono
        chat["dono_match_reason"] = dono_match_reason
    else:
        chat["dono_read_verified"] = False

    has_weird_dono = dono_read_verified
    has_weird_glitch = bool(chat.get("is_weird_spike")) or ("wonky_glitch_weird" in (txt.get("matched_categories") or {}))
    has_facecam_antics = bool(visual.get("facecam_antics"))

    # 1. Verified Streamer-Read SuperChat / Twitch Bits + Reaction
    if dono_read_verified:
        synergy += 24.0
        reasons.append(f"STREAMER READ DONO (+24 · {dono_match_reason})")

    # 2. Chat Weirdness / Wonky Glitch Radar (AYO, PAUSE, SUS, GLITCH, BUG, 💀)
    if chat.get("is_weird_spike"):
        synergy += 18.0
        toks = "/".join((chat.get("weird_tokens_hit") or [])[:3]).upper() or "AYO/GLITCH"
        reasons.append(f"CHAT {toks} RADAR (+18)")

    # 3. Isolated Facecam Antics (chair jump / camera freakout)
    if has_facecam_antics:
        synergy += 14.0
        reasons.append("FACECAM ANTICS (+14)")

    # 4. Standard Chat Explosion synergy
    if chat.get("is_explosion") and eff_a >= 11.0:
        synergy += 20.0
        reasons.append("CHAT+AUDIO EXPLOSION (+20)")
    elif chat.get("is_explosion") and t >= 12.0:
        synergy += 14.0
        reasons.append("CHAT+TRANSCRIPT MATCH (+14)")

    if chat.get("is_explosion") and eff_v >= 8.0:
        synergy += 10.0
        reasons.append("CHAT+VISUAL CHAOS (+10)")

    # 5. Cool Stream Moment WITHOUT Chat Explosion
    if v >= 15.0 and (a >= 9.0 or t >= 11.0):
        synergy += 16.0
        cool_play = True
        reasons.append("COOL PLAY / ACTION (+16)")
    elif a >= 15.0 and t >= 13.0:
        synergy += 12.0
        cool_play = True
        reasons.append("SHOUT+REACTION PHRASE (+12)")

    # 6. Rolling 30s Cool Story / Comedy / Roast detector (even when chat is calm!)
    if recent_txt_sum >= 24.0 and t >= 10.0 and not chat.get("is_explosion"):
        synergy += 14.0
        cool_story = True
        reasons.append("30S COOL STORY / COMEDY (+14)")

    # False-positive filter: ONLY damp static loud noise with no weirdness, dono, or facecam antics
    if (
        chat.get("active_chat")
        and c < 3.0
        and a >= 15.0
        and v < 10.0
        and t < 12.0
        and not has_weird_dono
        and not has_weird_glitch
        and not has_facecam_antics
    ):
        synergy -= 12.0
        reasons.append("STATIC LOUD NOISE DAMP (-12)")

    synergy = max(-15.0, min(30.0, synergy))
    base_total = max(0.0, min(100.0, a + v + t + c + synergy))

    if dono_read_verified:
        trigger_source = "weird_dono"
        archetype = "SUPERCHAT / DONO READ"
    elif has_weird_glitch:
        trigger_source = "weird_glitch"
        archetype = "WONKY GLITCH / AYO MOMENT"
    elif has_facecam_antics and (a >= 8.0 or c >= 10.0 or v >= 12.0):
        trigger_source = "facecam_antics"
        archetype = f"FACECAM ANTICS · {txt['archetype']}" if t >= 10.0 else "FACECAM FREAKOUT"
    elif chat.get("is_explosion") or (c >= 20.0 and c >= max(a, v)):
        trigger_source = "chat_explosion"
        archetype = "CHAT EXPLOSION" if t < 12.0 else f"CHAT + {txt['archetype']}"
    elif cool_play:
        trigger_source = "cool_play"
        archetype = f"COOL PLAY · {txt['archetype']}" if t >= 11.0 else "COOL GAMEPLAY ACTION"
    elif cool_story:
        trigger_source = "cool_story"
        archetype = f"STORY / COMEDY · {txt['archetype']}"
    else:
        trigger_source = "audio_speech"
        archetype = txt["archetype"] if t >= 10.0 else ("COOL ACTION" if v >= 16.0 else ("AUDIO PEAK" if a >= 15.0 else "VISUAL MOMENT"))

    # Apply Viral Style Blueprint + Learned Taste Memory multiplier
    taste_info = {"family": "neutral", "multiplier": 1.0, "blueprint_weight": 1.0, "taste_weight": 1.0, "reason": "neutral"}
    try:
        from scripts.clipper_taste_memory import get_taste_multiplier

        taste_info = get_taste_multiplier(
            archetype=archetype,
            channel=channel,
            matched_keywords=txt.get("matched_keywords"),
            matched_categories=list((txt.get("matched_categories") or {}).keys()),
            weird_tokens=chat.get("weird_tokens_hit"),
            has_weird_dono=has_weird_dono,
            has_weird_glitch=has_weird_glitch,
            has_facecam_antics=has_facecam_antics,
        )
    except Exception:
        pass

    mult = float(taste_info.get("multiplier", 1.0))
    total = round(max(0.0, min(100.0, base_total * mult)), 1)
    if abs(mult - 1.0) >= 0.03:
        reasons.append(f"BLUEPRINT/TASTE ({mult:.2f}x)")

    # Strict Viral Blueprint v2 tier thresholds: S-TIER >= 90, A-TIER >= 72, B-TIER < 72
    tier = "S-TIER" if total >= 90.0 else ("A-TIER" if total >= 72.0 else "B-TIER")
    return {
        "total_score": total,
        "base_score": round(base_total, 1),
        "taste_multiplier": mult,
        "taste_family": taste_info.get("family", "neutral"),
        "taste_reason": taste_info.get("reason", "neutral"),
        "synergy": round(synergy, 1),
        "synergy_reasons": reasons,
        "trigger_source": trigger_source,
        "archetype": archetype,
        "tier": tier,
    }


def find_smart_trim_offset(words: list[dict], max_trim_sec: float = 7.0) -> float:
    """
    Find a clean sentence/pause boundary within the first few seconds of the stitched
    clip so Shorts open right on a crisp hook instead of dead air or mid-word speech.
    """
    if not words:
        return 0.0
    # If leading silence > 1.2s, trim to 0.25s before first word
    if words[0]["start"] > 1.2 and words[0]["start"] <= max_trim_sec:
        return max(0.0, round(words[0]["start"] - 0.25, 2))

    # Look for a sentence end (., ?, !) or >0.55s pause within first 6.5s
    for i in range(len(words) - 1):
        cur, nxt = words[i], words[i + 1]
        if nxt["start"] > max_trim_sec:
            break
        if nxt["start"] < 1.0:
            continue
        gap = nxt["start"] - cur["end"]
        if cur["word"].endswith((".", "?", "!")) or gap >= 0.55:
            return max(0.0, round(nxt["start"] - 0.18, 2))
    return 0.0


def format_ass_time(sec: float) -> str:
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    cs = min(99, int(round((sec - int(sec)) * 100)))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def build_kinetic_ass_captions(
    words: list[dict],
    out_ass: Path,
    width: int,
    height: int,
    layout: str = "facecam-split",
    hook_banner: str = "",
):
    """
    Pro Viral Shorts Typography (Hormozi / Submagic style):
      - Bold Adwaita Sans Black with heavy 8px outline + 5px drop shadow
      - Smooth animated bounce pop on active word in vibrant Cyber Yellow (#FFE600)
      - On facecam-split: placed right at eye-line across the facecam/gameplay seam (y=755)
        so viewers read words WITHOUT looking away from the streamer's face!
      - Optional 3.5-second opening Hook Badge at top of frame with fade-in/out
    """
    is_vertical = height > width
    is_split = is_vertical and layout == "facecam-split"
    font_size = 72 if is_vertical else 54
    margin_v = int(height * 0.24) if is_vertical else int(height * 0.10)
    margin_lr = 85 if is_vertical else 120
    max_chars = 20 if is_vertical else 34

    # Alignment 5 = middle-center (for exact \pos on split seam), 2 = bottom-center
    align = 5 if is_split else 2

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Kinetic,Adwaita Sans,{font_size},&H00FFFFFF,&H0000E6FF,&H00080808,&HC8000000,-1,0,0,0,100,100,1.2,0,1,8,5,{align},{margin_lr},{margin_lr},{margin_v},1
Style: HookBadge,Adwaita Sans,38,&H00FFFFFF,&H005077F4,&H000B111E,&HD80B111E,-1,0,0,0,100,100,2.0,0,3,14,0,8,60,60,52,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]

    # Opening 3.5s Hook Pill Badge (stops scroll in first 0.5s)
    if hook_banner and is_vertical:
        safe_hook = hook_banner.replace("{", "").replace("}", "").replace("\\", "").upper()[:40]
        lines.append(
            f"Dialogue: 2,0:00:00.15,0:00:03.60,HookBadge,,0,0,0,,{{\\fad(220,320)\\3c&H005077F4&}}  {safe_hook}  \n"
        )

    groups: list[list[dict]] = []
    cur: list[dict] = []
    cur_chars = 0
    for w in words:
        wlen = len(w["word"]) + 1
        if cur and (len(cur) >= 3 or (cur_chars + wlen) > max_chars or (w["start"] - cur[-1]["end"]) > 0.55):
            groups.append(cur)
            cur = []
            cur_chars = 0
        cur.append(w)
        cur_chars += wlen
    if cur:
        groups.append(cur)

    pos_prefix = r"{\pos(540,765)}" if is_split else ""
    for grp in groups:
        for active_idx, w in enumerate(grp):
            t_start = w["start"]
            raw_end = grp[active_idx + 1]["start"] if active_idx + 1 < len(grp) else max(w["end"], w["start"] + 0.28)
            t_end = min(raw_end, t_start + 1.20)
            if t_end <= t_start:
                t_end = t_start + 0.16
            tokens = []
            for j, tok in enumerate(grp):
                safe = tok["word"].replace("{", "").replace("}", "").replace("\\", "").upper()
                if j == active_idx:
                    # Vibrant Cyber Yellow (#FFE600 -> ASS &H0000E6FF&) with snappy bounce pop!
                    tokens.append(
                        r"{\c&H0000E6FF&\t(0,70,\fscx112\fscy112)\t(70,170,\fscx104\fscy104)}"
                        + safe
                        + r"{\c&H00FFFFFF&\fscx100\fscy100}"
                    )
                else:
                    tokens.append(safe)
            lines.append(
                f"Dialogue: 1,{format_ass_time(t_start)},{format_ass_time(t_end)},Kinetic,,0,0,0,,{pos_prefix}{' '.join(tokens)}\n"
            )

    out_ass.write_text("".join(lines), encoding="utf-8")


def score_hook_cli(line: str) -> str:
    if not HOOKSCORE_SCRIPT.exists() or not line.strip():
        return ""
    try:
        res = subprocess.run(
            [sys.executable, str(HOOKSCORE_SCRIPT), "--hook", line[:160]],
            capture_output=True,
            text=True,
            timeout=5,
        )
        lines = [l.strip() for l in (res.stdout or "").splitlines() if l.strip()]
        verdict = next((l for l in lines if l.startswith("VERDICT")), "")
        weakest = next((l for l in lines if l.startswith("weakest")), "")
        parts = [p for p in (verdict, weakest) if p]
        return " — ".join(parts) if parts else (lines[0] if lines else "")
    except Exception:
        return ""


def build_facecam_split_filter(facecam_pos: str = "top-right", duration_sec: float = 35.0) -> str:
    """
    Zero-Gap Pro 9:16 Split-Screen:
      - Top 732px: Streamer facecam edge-to-edge (color-graded, sharpened)
      - Bottom 1188px: Gameplay cropped 12% top/bottom (eliminates ALL GTA 6 cutscene black letterbox bars!)
      - Clean 4px animated CreatorRadar orange (#f47750) progress bar directly on the seam — ZERO black gap!
    """
    pos_map = {
        "top-right": "iw*0.236:ih*0.280:iw*0.764:0",
        "top-left": "iw*0.236:ih*0.280:0:0",
        "bottom-right": "iw*0.236:ih*0.280:iw*0.764:ih*0.720",
        "bottom-left": "iw*0.236:ih*0.280:0:ih*0.720",
    }
    cam_crop = pos_map.get(facecam_pos, pos_map["top-right"])
    dur = max(1.0, float(duration_sec))
    return (
        f"split[cam_in][game_in];"
        f"[cam_in]crop={cam_crop},scale=1080:732:flags=lanczos:force_original_aspect_ratio=increase,crop=1080:732,"
        f"eq=contrast=1.06:saturation=1.14:brightness=0.015,unsharp=5:5:0.7:5:5:0.0[cam];"
        f"[game_in]crop=iw:ih*0.76:0:ih*0.12,scale=-2:1188:flags=lanczos,crop=1080:1188,"
        f"eq=contrast=1.07:saturation=1.16,unsharp=5:5:0.75:5:5:0.0[game];"
        f"[cam][game]vstack=inputs=2,"
        f"drawbox=x=0:y=730:w=1080:h=4:color=0x1e2d48@0.85:t=fill,"
        f"drawbox=x=0:y=730:w='min(1080,max(12,1080*t/{dur:.2f}))':h=4:color=0xf47750@1.0:t=fill"
    )


def build_pip_overlay_filter(facecam_pos: str = "top-right", duration_sec: float = 35.0) -> str:
    """
    Full-Screen 9:16 Gameplay + Floating Framed Facecam Card (Zero Split Seam!):
      - Full 1080x1920 vertical gameplay filling the entire phone screen (cutscene bars cropped out)
      - Crisp framed facecam card (460x320) floating at top-right with thin #f47750 accent border
      - Thin bottom-safe animated progress bar
    """
    pos_map = {
        "top-right": "iw*0.236:ih*0.280:iw*0.764:0",
        "top-left": "iw*0.236:ih*0.280:0:0",
        "bottom-right": "iw*0.236:ih*0.280:iw*0.764:ih*0.720",
        "bottom-left": "iw*0.236:ih*0.280:0:ih*0.720",
    }
    cam_crop = pos_map.get(facecam_pos, pos_map["top-right"])
    dur = max(1.0, float(duration_sec))
    return (
        f"split[game_in][cam_in];"
        f"[game_in]crop=iw:ih*0.76:0:ih*0.12,scale=-2:1920:flags=lanczos,crop=1080:1920,"
        f"eq=contrast=1.07:saturation=1.15,unsharp=5:5:0.7:5:5:0.0[bg];"
        f"[cam_in]crop={cam_crop},scale=444:312:flags=lanczos:force_original_aspect_ratio=increase,crop=444:312,"
        f"eq=contrast=1.06:saturation=1.14,unsharp=5:5:0.7:5:5:0.0,pad=452:320:4:4:color=0xf47750[pip];"
        f"[bg][pip]overlay=W-w-36:130,"
        f"drawbox=x=0:y=1912:w='min(1080,max(12,1080*t/{dur:.2f}))':h=8:color=0xf47750@1.0:t=fill"
    )


SFX_DIR = ROOT / "assets" / "sfx"


def detect_reaction_peaks(
    wav_path: Path,
    trim_offset: float,
    clip_dur: float,
    words: list[dict] | None = None,
    max_peaks: int = 2,
) -> list[float]:
    """
    Detect up to 2 crisp acoustic/vocal reaction peaks inside [trim_offset, trim_offset + clip_dur]
    (returns clip-relative timestamps in seconds). Zero VRAM, <20ms CPU.
    """
    try:
        data, sr = sf.read(str(wav_path), dtype="float32")
        if data.ndim > 1:
            data = data.mean(axis=1)
        s0 = max(0, int(trim_offset * sr))
        s1 = min(len(data), int((trim_offset + clip_dur) * sr))
        seg = data[s0:s1]
        if len(seg) < int(sr * 3.0):
            return []

        hop = max(1, int(sr * 0.25))
        win = max(1, int(sr * 0.50))
        energies: list[tuple[float, float]] = []
        for pos in range(0, max(1, len(seg) - win), hop):
            frame = seg[pos:pos + win]
            rms = float(np.sqrt(np.mean(frame ** 2)) + 1e-9)
            # Boost vocal excitement energy (1.5 - 5.5 kHz) so laughs/screams beat bass rumble
            spec = np.abs(np.fft.rfft(frame))
            freqs = np.fft.rfftfreq(len(frame), d=1.0 / sr)
            vocal = float(np.mean(spec[(freqs >= 1500) & (freqs <= 5500)]) + 1e-9)
            t_sec = pos / float(sr)
            if 1.1 <= t_sec <= max(1.5, clip_dur - 1.5):
                energies.append((t_sec, rms * (1.0 + min(3.0, vocal * 4.0))))

        if not energies:
            return []

        vals = np.array([e[1] for e in energies], dtype=float)
        med = float(np.median(vals))
        mad = max(1e-6, 1.4826 * float(np.median(np.abs(vals - med))))

        ranked = sorted(energies, key=lambda x: -x[1])
        peaks: list[float] = []
        for t_sec, val in ranked:
            if val < med + 0.8 * mad and peaks:
                break
            if any(abs(t_sec - p) < 4.5 for p in peaks):
                continue
            # Snap within +/-0.35s to the nearest spoken word onset so zoom + SFX land on the punchline
            if words:
                nearest = min(words, key=lambda w: abs(float(w.get("start", 0.0)) - t_sec))
                if abs(float(nearest.get("start", 0.0)) - t_sec) <= 0.35:
                    t_sec = max(1.0, min(clip_dur - 1.4, float(nearest["start"])))
            peaks.append(round(t_sec, 2))
            if len(peaks) >= max_peaks:
                break

        peaks.sort()
        return peaks
    except Exception:
        return []


def build_punch_zoom_expr(clip_dur: float, peaks: list[float], zoom_boost: float = 0.13) -> str:
    """
    Build a smooth per-frame FFmpeg zoom factor expression:
      - Subtle continuous 1.00 -> 1.035 Ken Burns drift across the clip
      - Snappy +13% punch-in zoom on each reaction peak (0.15s attack, 1.15s hold, 0.45s ease-out)
    """
    dur = max(3.0, float(clip_dur))
    terms = [f"1+0.035*t/{dur:.2f}"]
    for p in peaks[:2]:
        a1 = round(p + 0.15, 2)
        h1 = round(p + 1.30, 2)
        e1 = round(p + 1.75, 2)
        terms.append(
            f"{zoom_boost:.2f}*("
            f"between(t,{p:.2f},{a1:.2f})*(t-{p:.2f})/0.15+"
            f"between(t,{a1:.2f},{h1:.2f})+"
            f"between(t,{h1:.2f},{e1:.2f})*({e1:.2f}-t)/0.45)"
        )
    return "+".join(terms)


def build_sfx_mix_plan(peaks: list[float], clip_dur: float) -> list[dict]:
    """
    Choose copyright-free local studio SFX hits synchronized to opening hook + reaction peaks.
    Returns list of {path, delay_ms, volume, label}.
    """
    plan: list[dict] = []
    pop_wav = SFX_DIR / "sfx_pop_click.wav"
    whoosh_wav = SFX_DIR / "whoosh.wav"
    bass_wav = SFX_DIR / "sfx_bass_hit.wav"
    impact_wav = SFX_DIR / "impact.wav"

    # 1. Crisp 80ms opening hook pop
    if pop_wav.exists() and clip_dur >= 4.0:
        plan.append({"path": pop_wav, "delay_ms": 80, "volume": 0.16, "label": "hook_pop"})

    # 2. Climax reaction peak #1 -> whoosh lead-in + bass/impact hit
    if peaks:
        p0 = peaks[0]
        if whoosh_wav.exists() and p0 >= 0.25:
            plan.append({"path": whoosh_wav, "delay_ms": max(0, int((p0 - 0.12) * 1000)), "volume": 0.18, "label": "zoom_whoosh_1"})
        hit1 = bass_wav if bass_wav.exists() else impact_wav
        if hit1.exists():
            plan.append({"path": hit1, "delay_ms": int(p0 * 1000), "volume": 0.26, "label": "peak_hit_1"})

    # 3. Secondary reaction peak #2 -> subtle whoosh + crisp impact
    if len(peaks) >= 2:
        p1 = peaks[1]
        if whoosh_wav.exists():
            plan.append({"path": whoosh_wav, "delay_ms": max(0, int((p1 - 0.10) * 1000)), "volume": 0.15, "label": "zoom_whoosh_2"})
        if impact_wav.exists():
            plan.append({"path": impact_wav, "delay_ms": int(p1 * 1000), "volume": 0.22, "label": "peak_hit_2"})

    return plan


def render_dono_card_png(dono: dict, out_png: Path, width: int = 920) -> Path | None:
    """
    Render a crisp, rounded SuperChat / Twitch Cheer cutout card PNG (transparent background +
    soft drop shadow) to overlay above the 16:9 gameplay frame while the streamer reads it!
    """
    try:
        import textwrap
        from PIL import ImageDraw, ImageFilter, ImageFont

        author = str(dono.get("author") or "Viewer").strip()[:28]
        amount = str(dono.get("amount_str") or "DONATION").strip()[:22]
        msg = re.sub(r"\s+", " ", str(dono.get("msg") or "")).strip()[:180]
        if not msg:
            return None

        src = str(dono.get("source") or "").lower()
        is_yt = "youtube" in src or "super" in src
        header_bg = (218, 41, 28, 255) if is_yt else (145, 70, 255, 255)  # YouTube SuperChat Red vs Twitch Purple
        badge_bg = (255, 214, 0, 255) if is_yt else (255, 230, 0, 255)
        body_bg = (18, 24, 38, 242)
        border_col = (255, 214, 0, 220) if is_yt else (184, 134, 255, 220)
        platform_tag = "SUPER CHAT" if is_yt else ("TWITCH BITS" if "bits" in src else "STREAM CHAT")

        font_bold_path = "/usr/share/fonts/adwaita-sans-fonts/AdwaitaSans-Bold.ttf"
        font_reg_path = "/usr/share/fonts/adwaita-sans-fonts/AdwaitaSans-Regular.ttf"
        if not Path(font_bold_path).exists():
            font_bold_path = "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf"
        if not Path(font_reg_path).exists():
            font_reg_path = "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf"

        f_author = ImageFont.truetype(font_bold_path, 34) if Path(font_bold_path).exists() else ImageFont.load_default()
        f_badge = ImageFont.truetype(font_bold_path, 26) if Path(font_bold_path).exists() else ImageFont.load_default()
        f_msg = ImageFont.truetype(font_bold_path, 36) if Path(font_bold_path).exists() else ImageFont.load_default()
        f_sub = ImageFont.truetype(font_reg_path, 22) if Path(font_reg_path).exists() else ImageFont.load_default()

        wrapped = textwrap.wrap(msg, width=38)[:3]
        pad = 26
        header_h = 84
        line_h = 48
        body_h = 34 + len(wrapped) * line_h + 26
        card_w = width - pad * 2
        card_h = header_h + body_h
        total_h = card_h + pad * 2

        canvas = Image.new("RGBA", (width, total_h), (0, 0, 0, 0))
        shadow = Image.new("RGBA", (width, total_h), (0, 0, 0, 0))
        sdraw = ImageDraw.Draw(shadow)
        sdraw.rounded_rectangle([pad + 4, pad + 10, pad + card_w + 4, pad + card_h + 10], radius=28, fill=(0, 0, 0, 175))
        shadow = shadow.filter(ImageFilter.GaussianBlur(14))
        canvas.alpha_composite(shadow)

        card = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
        cdraw = ImageDraw.Draw(card)
        cdraw.rounded_rectangle([0, 0, card_w - 1, card_h - 1], radius=26, fill=body_bg)
        # Colored top header clipped cleanly inside rounded mask
        hdr_layer = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
        hdraw = ImageDraw.Draw(hdr_layer)
        hdraw.rectangle([0, 0, card_w, header_h], fill=header_bg)
        mask = Image.new("L", (card_w, card_h), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, card_w - 1, card_h - 1], radius=26, fill=255)
        card.paste(hdr_layer, (0, 0), mask)

        cdraw = ImageDraw.Draw(card)
        # Initial circle avatar
        cdraw.ellipse([24, 16, 76, 68], fill=(255, 255, 255, 48), outline=(255, 255, 255, 190), width=2)
        cdraw.text((50, 42), author[0].upper(), font=f_author, fill=(255, 255, 255, 255), anchor="mm")
        cdraw.text((92, 16), author, font=f_author, fill=(255, 255, 255, 255))
        cdraw.text((92, 54), platform_tag, font=f_sub, fill=(255, 255, 255, 210))

        # Amount pill on top-right
        bbox = cdraw.textbbox((0, 0), amount, font=f_badge)
        tw = bbox[2] - bbox[0]
        pill_x1 = card_w - 24
        pill_x0 = pill_x1 - tw - 32
        cdraw.rounded_rectangle([pill_x0, 20, pill_x1, 64], radius=22, fill=badge_bg)
        cdraw.text(((pill_x0 + pill_x1) // 2, 42), amount, font=f_badge, fill=(15, 23, 38, 255), anchor="mm")

        # Message text
        y_cur = header_h + 24
        for line in wrapped:
            cdraw.text((28, y_cur), line, font=f_msg, fill=(255, 255, 255, 255))
            y_cur += line_h

        # Outer glowing border
        cdraw.rounded_rectangle([1, 1, card_w - 2, card_h - 2], radius=26, outline=border_col, width=3)

        canvas.alpha_composite(card, (pad, pad))
        canvas.save(str(out_png), "PNG")
        return out_png
    except Exception:
        return None


def export_clip_package(
    concat_media: Path,
    source_url: str,
    channel: str,
    moment_info: dict,
    out_dir: Path,
    layout: str = "split-blur",
    use_nvenc: bool = True,
    smart_trim: bool = True,
    asr_manager: ASRManager | None = None,
    facecam_pos: str = "top-right",
    max_clip_sec: float = 32.0,
    enable_punch_zoom: bool = True,
    enable_sfx: bool = True,
) -> Path:
    """Export vertical/landscape clip with Hindi/English Whisper or Whistle smart-trim + punch-in zooms + SFX + kinetic captions + -14 LUFS."""
    out_dir.mkdir(parents=True, exist_ok=True)
    clip_id = out_dir.name
    final_mp4 = out_dir / f"{clip_id}.mp4"
    ass_path = out_dir / "captions.ass"
    transcript_json = out_dir / "transcript.json"
    moment_json = out_dir / "moment.json"

    with tempfile.TemporaryDirectory(prefix="cr_clip_export_") as tmp:
        tmp_wav = Path(tmp) / "clip_16k.wav"
        extract_wav_16k(concat_media, tmp_wav)
        # Prefer Groq whisper-large-v3-turbo (~0.35s, 0 local VRAM) ONLY for strong A/S-tier candidates (>=65) to protect free-tier quota
        pre_score = float((moment_info.get("fusion") or {}).get("total_score") or 50.0)
        asr = None
        try:
            from scripts.groq_clip_brain import groq_transcribe_wav
            lang_hint = getattr(asr_manager, "language", "auto") if asr_manager else "auto"
            asr = groq_transcribe_wav(
                tmp_wav,
                language=lang_hint,
                prompt_hint=f"Live gaming stream clip from {channel}. GTA 6, Vice City, Leonida, Lucia, Jason, Twitch chat.",
                clip_score=pre_score,
            )
        except Exception:
            asr = None
        if not asr:
            asr = asr_manager.transcribe(tmp_wav) if asr_manager else transcribe_whistle(tmp_wav)
        raw_words = asr.get("words") or []
        game_ctx = "GTA 6" if "gta" in channel.lower() else "Live Gaming"
        streamer_ctx = re.sub(r"[-_]*(?:gta6|gtavi|live|valorant|minecraft)$", "", channel, flags=re.I).replace("-", " ").title() or channel
        polished = polish_and_align_captions(
            raw_words,
            wav_path=tmp_wav,
            use_llm=(pre_score >= 65.0),
            streamer=streamer_ctx,
            game=game_ctx,
        )

        aligned_words = polished["words"] if "words" in polished else raw_words
        trim_offset = find_smart_trim_offset(aligned_words) if smart_trim else 0.0

        # Shift word timestamps by trim_offset so captions stay frame-accurate after smart trim
        words = []
        for w in aligned_words:
            if w["end"] <= trim_offset:
                continue
            words.append({
                "word": w["word"],
                "start": round(max(0.0, w["start"] - trim_offset), 3),
                "end": round(max(0.05, w["end"] - trim_offset), 3),
                "probability": w["probability"],
            })
        transcript_text = " ".join(w["word"] for w in words).strip() or (polished.get("text") or "").strip()

        # Probe exact duration and enforce hard Shorts max_clip_sec cap (keeps every Short tight ~30s!)
        raw_dur = 32.0
        try:
            pr = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(concat_media)],
                capture_output=True, text=True, timeout=6,
            )
            if pr.returncode == 0 and pr.stdout.strip():
                raw_dur = max(3.0, float(pr.stdout.strip()))
        except Exception:
            pass

        # If stitched buffer is longer than max_clip_sec (e.g. wide HLS keyframes), keep the climax tail of max_clip_sec!
        max_cap = max(10.0, float(max_clip_sec))
        if (raw_dur - trim_offset) > max_cap:
            extra_skip = (raw_dur - trim_offset) - max_cap
            trim_offset = round(trim_offset + extra_skip, 2)
            words = [
                {
                    "word": w["word"],
                    "start": round(max(0.0, w["start"] - extra_skip), 3),
                    "end": round(max(0.05, w["end"] - extra_skip), 3),
                    "probability": w["probability"],
                }
                for w in words
                if w["end"] > extra_skip
            ]
            transcript_text = " ".join(w["word"] for w in words).strip() or transcript_text

        clip_dur = min(max_cap, max(3.0, raw_dur - trim_offset))

        # Viral Blueprint v2 abrupt punchline snap: trim dead air to <=1.2s after final word for loopable Shorts (keeping >=11s)
        if smart_trim and words:
            last_word_end = max(float(w.get("end", 0.0)) for w in words)
            if last_word_end >= 10.0 and (clip_dur - last_word_end) > 1.6:
                clip_dur = round(max(11.0, min(clip_dur, last_word_end + 1.2)), 2)

        # Detect acoustic/vocal reaction peaks for synchronized Punch-In Zooms + Crisp SFX hits
        reaction_peaks = detect_reaction_peaks(tmp_wav, trim_offset, clip_dur, words=words, max_peaks=2) if (enable_punch_zoom or enable_sfx) else []
        sfx_plan = build_sfx_mix_plan(reaction_peaks, clip_dur) if enable_sfx else []

    z_expr = build_punch_zoom_expr(clip_dur, reaction_peaks, zoom_boost=0.13) if enable_punch_zoom else ""

    if layout == "landscape":
        w, h = 1920, 1080
        base_vf = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2"
    elif layout == "crop":
        w, h = 1080, 1920
        if enable_punch_zoom and z_expr:
            base_vf = (
                f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
                f"scale=w='trunc(1080*({z_expr})/2)*2':h='trunc(1920*({z_expr})/2)*2':eval=frame:flags=bilinear,"
                f"crop=1080:1920:(iw-1080)/2:(ih-1920)/2,eq=contrast=1.06:saturation=1.14,unsharp=5:5:0.7:5:5:0.0"
            )
        else:
            base_vf = "scale=-2:1920,crop=1080:1920,eq=contrast=1.06:saturation=1.14,unsharp=5:5:0.7:5:5:0.0"
    elif layout == "facecam-split":
        w, h = 1080, 1920
        base_vf = build_facecam_split_filter(facecam_pos, duration_sec=clip_dur)
        if enable_punch_zoom and z_expr:
            base_vf = (
                f"{base_vf}[vpre];"
                f"[vpre]scale=w='trunc(1080*({z_expr})/2)*2':h='trunc(1920*({z_expr})/2)*2':eval=frame:flags=bilinear,"
                f"crop=1080:1920:(iw-1080)/2:(ih-1920)/2"
            )
    elif layout == "pip-overlay":
        w, h = 1080, 1920
        base_vf = build_pip_overlay_filter(facecam_pos, duration_sec=clip_dur)
        if enable_punch_zoom and z_expr:
            base_vf = (
                f"{base_vf}[vpre];"
                f"[vpre]scale=w='trunc(1080*({z_expr})/2)*2':h='trunc(1920*({z_expr})/2)*2':eval=frame:flags=bilinear,"
                f"crop=1080:1920:(iw-1080)/2:(ih-1920)/2"
            )
    else:
        # Pro Split-Blur: full uncropped 16:9 foreground with dynamic Punch-In Zooms over dreamy ambient blur.
        # No template chrome (AGENTS.md rule 8): no hook badge, no progress bar, no source bar.
        w, h = 1080, 1920
        if enable_punch_zoom and z_expr:
            fg_chain = (
                f"[fg]scale=w='trunc(1080*({z_expr})/2)*2':h='trunc(608*({z_expr})/2)*2':eval=frame:flags=bilinear,"
                f"crop=1080:608:(iw-1080)/2:(ih-608)/2,eq=contrast=1.06:saturation=1.12,unsharp=5:5:0.6:5:5:0.0[f];"
            )
        else:
            fg_chain = "[fg]scale=1080:-2:flags=lanczos,eq=contrast=1.06:saturation=1.12,unsharp=5:5:0.6:5:5:0.0[f];"
        base_vf = (
            f"split[bg][fg];"
            f"[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=32:4,eq=brightness=-0.16:saturation=1.15[b];"
            f"{fg_chain}"
            f"[b][f]overlay=(W-w)/2:(H-h)/2"
        )

    # Probe first decodable video keyframe PTS in concat_media so we NEVER start video after audio (eliminates 1-5s frozen starts!)
    first_v_pts = 0.0
    try:
        vpr = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=start_time", "-of", "default=noprint_wrappers=1:nokey=1",
                str(concat_media),
            ],
            capture_output=True, text=True, timeout=6,
        )
        apr = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "a:0",
                "-show_entries", "stream=start_time", "-of", "default=noprint_wrappers=1:nokey=1",
                str(concat_media),
            ],
            capture_output=True, text=True, timeout=6,
        )
        if vpr.returncode == 0 and apr.returncode == 0 and vpr.stdout.strip() and apr.stdout.strip():
            v_st = float(vpr.stdout.strip())
            a_st = float(apr.stdout.strip())
            if v_st > a_st + 0.04:
                first_v_pts = round(v_st - a_st + 0.04, 2)
    except Exception:
        pass

    if first_v_pts > trim_offset:
        shift_delta = first_v_pts - trim_offset
        trim_offset = first_v_pts
        words = [
            {
                "word": w["word"],
                "start": round(max(0.0, w["start"] - shift_delta), 3),
                "end": round(max(0.05, w["end"] - shift_delta), 3),
                "probability": w["probability"],
            }
            for w in words
            if w["end"] > shift_delta
        ]
        transcript_text = " ".join(w["word"] for w in words).strip() or transcript_text
        clip_dur = min(max_cap, max(3.0, raw_dur - trim_offset))

    fusion_meta = moment_info.get("fusion") or {}
    chat_meta = moment_info.get("chat") or {}

    # Optional SuperChat / Twitch Cheer floating cutout card — ONLY when verified that the streamer actually read it!
    dono_card_png: Path | None = None
    matched_dono = chat_meta.get("matched_dono")
    if chat_meta.get("dono_read_verified") and isinstance(matched_dono, dict) and layout != "landscape":
        dono_card_png = render_dono_card_png(matched_dono, out_dir / "dono_card.png", width=920)

    # Decode-accurate filter trim + zero-based PTS reset so BOTH video & audio start at EXACTLY 0.000s (zero frozen frames!)
    v_trim_prefix = f"[0:v]trim=start={trim_offset:.3f}:duration={clip_dur:.3f},setpts=PTS-STARTPTS[vtrim];[vtrim]"
    if words:
        build_kinetic_ass_captions(words, ass_path, w, h, layout=layout)
        ass_escaped = str(ass_path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        video_graph = f"{v_trim_prefix}{base_vf}[v0];[v0]ass='{ass_escaped}'[vsub]"
    else:
        video_graph = f"{v_trim_prefix}{base_vf}[vsub]"

    vcodec_args = (
        ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "20", "-b:v", "0", "-g", "60", "-keyint_min", "30"]
        if use_nvenc
        else ["-c:v", "libx264", "-preset", "medium", "-crf", "19", "-g", "60", "-keyint_min", "30"]
    )
    af_base = f"atrim=start={trim_offset:.3f}:duration={clip_dur:.3f},asetpts=PTS-STARTPTS,highpass=f=75,acompressor=threshold=-18dB:ratio=3:attack=15:release=100"

    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-fflags", "+genpts", "-i", str(concat_media)]
    next_input_idx = 1

    if dono_card_png and dono_card_png.exists():
        cmd += ["-loop", "1", "-t", f"{clip_dur:.2f}", "-i", str(dono_card_png)]
        card_idx = next_input_idx
        next_input_idx += 1
        card_end = round(min(9.5, max(4.5, clip_dur - 1.2)), 2)
        card_y = 140 if layout == "split-blur" else 90
        video_graph = (
            f"{video_graph};"
            f"[{card_idx}:v]format=rgba,fade=t=in:st=0.35:d=0.25:alpha=1,fade=t=out:st={max(1.0, card_end - 0.35):.2f}:d=0.35:alpha=1[dcard];"
            f"[vsub][dcard]overlay=(W-w)/2:{card_y}:enable='between(t,0.35,{card_end:.2f})':shortest=1[vout]"
        )
    else:
        video_graph = f"{video_graph};[vsub]null[vout]"

    if sfx_plan:
        sfx_start_idx = next_input_idx
        for item in sfx_plan:
            cmd += ["-i", str(item["path"])]
        audio_parts = [f"[0:a]{af_base}[a0]"]
        mix_inputs = ["[a0]"]
        for offset, item in enumerate(sfx_plan):
            inp_i = sfx_start_idx + offset
            d_ms = int(item["delay_ms"])
            vol = float(item["volume"])
            audio_parts.append(
                f"[{inp_i}:a]aresample=48000,aformat=channel_layouts=stereo,volume={vol:.2f},adelay={d_ms}|{d_ms}[sfx{offset + 1}]"
            )
            mix_inputs.append(f"[sfx{offset + 1}]")
        audio_parts.append(
            f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=first:dropout_transition=0:normalize=0,"
            f"loudnorm=I=-14:LRA=7:TP=-1.5[aout]"
        )
        full_graph = f"{video_graph};{';'.join(audio_parts)}"
        cmd += ["-filter_complex", full_graph, "-map", "[vout]", "-map", "[aout]"]
    else:
        full_graph = f"{video_graph};[0:a]{af_base},loudnorm=I=-14:LRA=7:TP=-1.5[aout]"
        cmd += ["-filter_complex", full_graph, "-map", "[vout]", "-map", "[aout]"]

    cmd += [
        *vcodec_args,
        "-pix_fmt", "yuv420p",
        "-fps_mode", "cfr",
        "-avoid_negative_ts", "make_zero",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart",
        str(final_mp4),
    ]
    subprocess.run(cmd, check=True)

    asr_out = {
        "engine": asr.get("engine"),
        "polisher": {
            "raw_count": polished.get("raw_count", len(raw_words)),
            "polished_count": polished.get("polished_count", len(aligned_words)),
            "llm_used": polished.get("llm_used", False),
        },
        "raw_text": asr.get("text", ""),
        "trim_offset_sec": trim_offset,
        "text": transcript_text,
        "words": words,
    }
    transcript_json.write_text(json.dumps(asr_out, indent=2), encoding="utf-8")

    fusion = moment_info.get("fusion", {})
    # Re-apply strict S-TIER >= 90 / A-TIER >= 72 thresholds (Groq batch review runs in groups of 2-3 clips to save free-tier API calls!)
    cur_sc = float(fusion.get("total_score") or 50.0)
    fusion["tier"] = "S-TIER" if cur_sc >= 90.0 else ("A-TIER" if cur_sc >= 72.0 else "B-TIER")
    moment_info["final_mp4"] = str(final_mp4)
    moment_info["smart_trim_offset_sec"] = trim_offset
    moment_info["reaction_peaks_sec"] = reaction_peaks
    moment_info["punch_zoom_enabled"] = enable_punch_zoom
    moment_info["sfx_applied"] = [{"label": s["label"], "delay_ms": s["delay_ms"]} for s in sfx_plan]
    moment_info["transcript"] = transcript_text
    moment_info["word_count"] = len(words)
    moment_json.write_text(json.dumps(moment_info, indent=2), encoding="utf-8")

    snippet = re.sub(r"\s+", " ", transcript_text).strip()
    title_hook = (snippet[:58] + "...") if len(snippet) > 60 else (snippet or f"Insane {fusion.get('archetype', 'Live')} Moment from {channel}")
    draft_desc_hook = f"{fusion.get('archetype', 'Highlight')} clipped live from {channel}."
    try:
        from scripts.youtube_uploader import _generate_viral_clip_metadata
        viral_meta = _generate_viral_clip_metadata(channel, transcript_text, moment_info, clip_id=clip_id)
        if viral_meta.get("title"):
            title_hook = f"{viral_meta['title']} #Shorts" if "#shorts" not in viral_meta["title"].lower() else viral_meta["title"]
        if viral_meta.get("hook_line"):
            draft_desc_hook = viral_meta["hook_line"]
    except Exception:
        pass
    hook_eval = score_hook_cli(title_hook)

    public_source = source_url if str(source_url or "").startswith(("http://", "https://")) else ""
    credit_md = f"Credit: {channel} ({public_source})" if public_source else f"Credit: {channel}"
    (out_dir / "metadata.md").write_text(
        f"""# Draft Viral Clip Metadata — `{clip_id}`

- **Virality Tier:** `{fusion.get('tier', 'B-TIER')}` — Score **`{fusion.get('total_score', 0)}/100`**
- **Archetype / Trigger:** `{fusion.get('archetype', 'MOMENT')}` (Triggered by `{fusion.get('trigger_source', 'unknown')}`)
- **Draft Title:** {title_hook}
- **Hook Score Note:** `{hook_eval or 'n/a'}`
- **Channel / Source:** `{channel}`{f' ({public_source})' if public_source else ''}
- **Signal Breakdown:** Chat `{moment_info['chat']['score']}` | Audio `{moment_info['audio']['score']}` | Visual `{moment_info['visual']['score']}` | Transcript `{moment_info['transcript_score']['score']}` | Synergy `{fusion.get('synergy', 0)}` ({', '.join(fusion.get('synergy_reasons', [])) or 'none'})
- **Lookback Window:** `{moment_info.get('pre_pad_used', 0)}s` pre-pad + `{moment_info.get('post_pad_used', 0)}s` post-pad (smart-trimmed `{trim_offset}s` leading silence)
- **Layout:** `{layout}` (`{w}x{h}`)

## Description (Draft)
{draft_desc_hook}

{credit_md}

_AI disclosure: captions and editing were produced with AI assistance. All GTA VI facts cited in this description come from official Rockstar Games, PlayStation, or Xbox sources._

## Transcript ({asr.get('engine', 'ASR')})
> {transcript_text or '(No speech detected)'}
""",
        encoding="utf-8",
    )

    (out_dir / "checklist.md").write_text(
        f"""# Human Approval & Rights Clearance Checklist — `{clip_id}`

> **CreatorRadar Studio Rule 4 & Rule 5:** Never upload clips autonomously. Complete all checks before manual upload.

- [ ] **Rights Clearance (Rule 5):** Confirmed clip is from our own stream, has creator permission, or qualifies for transformative commentary; logged in `assets/clearance-log.md`.
- [ ] **Hook & Framing Check:** Watched `{final_mp4.name}` end-to-end; buildup starts cleanly (30s pre-explosion lookback), climax lands, captions sync tightly.
- [ ] **Audio Check:** `-14 LUFS` normalized audio is clean with no harsh clipping.
- [ ] **Metadata & Disclosure:** Title, source attribution, and AI disclosure verified in `metadata.md`.
- [ ] **Final Owner Sign-Off:** Approved for manual upload to YouTube Studio.
""",
        encoding="utf-8",
    )
    return final_mp4


def stitch_segments(segment_paths: list[Path], out_file: Path):
    list_file = out_file.with_suffix(".concat.txt")
    list_file.write_text("".join(f"file '{p.resolve()}'\n" for p in segment_paths if p.exists()), encoding="utf-8")
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "concat", "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            str(out_file),
        ],
        check=True,
    )
    list_file.unlink(missing_ok=True)


def compute_clip_window(idx: int, pre_segs: int, post_segs: int, max_clip_segs: int) -> tuple[int, int]:
    """Return an inclusive segment window that always contains the trigger segment.

    ``max_clip_segs`` is a *total length* budget, so the post-roll is reserved
    first and the pre-roll lookback is shrunk when the two would not both fit.
    Clamping the total from ``start_idx`` (the old behaviour) could push the end
    before ``idx`` and silently discard the reaction.
    """
    max_clip_segs = max(1, int(max_clip_segs))
    post_use = min(max(0, int(post_segs)), max_clip_segs - 1)
    pre_use = min(max(0, int(pre_segs)), max_clip_segs - 1 - post_use)
    start_idx = max(0, idx - pre_use)
    end_idx = min(idx + post_use, start_idx + max_clip_segs - 1)
    return start_idx, max(idx, end_idx)


def extend_clip_window(
    start_idx: int, end_idx: int, trigger_idx: int, idx: int, post_segs: int, max_clip_segs: int
) -> tuple[int, int]:
    """Ride an escalating moment by extending the tail within the total budget.

    When the original lookback already fills the budget, the head slides forward
    (never past the trigger) so the peak can still be captured instead of the
    extension silently no-oping.
    """
    max_clip_segs = max(1, int(max_clip_segs))
    post_use = min(max(0, int(post_segs)), max_clip_segs - 1)
    new_end = max(end_idx, idx + post_use)
    new_start = max(start_idx, min(trigger_idx, new_end - max_clip_segs + 1))
    new_end = min(new_end, new_start + max_clip_segs - 1)
    return new_start, max(end_idx, new_end)


def run_vod_or_local_mode(args: argparse.Namespace, cfg: dict, use_nvenc: bool):
    src = Path(args.input).resolve()
    if not src.exists():
        raise FileNotFoundError(f"Input video not found: {src}")

    channel = slugify(args.name or src.stem)
    session_dir = RENDERS_BUFFER_DIR / f"{channel}_{int(time.time())}"
    session_dir.mkdir(parents=True, exist_ok=True)
    seg_dur = args.segment_sec

    print(f"[LiveClipper v2] Scanning local video in {seg_dur}s chunks (Whistle + DSP + Visual): {src.name}", flush=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(src),
            "-c", "copy", "-f", "segment", "-segment_time", str(seg_dur),
            "-reset_timestamps", "1",
            str(session_dir / "seg_%06d.ts"),
        ],
        check=True,
    )

    asr_manager = ASRManager(backend=args.asr, language=args.asr_lang)
    segments = sorted(session_dir.glob("seg_*.ts"))
    rms_history: collections.deque[float] = collections.deque(maxlen=40)
    motion_history: collections.deque[float] = collections.deque(maxlen=40)
    facecam_history: collections.deque[float] = collections.deque(maxlen=40)
    wps_history: collections.deque[float] = collections.deque(maxlen=40)
    recent_txt: collections.deque[float] = collections.deque(maxlen=3)
    custom_kw = [k.strip() for k in (args.keywords or "").split(",") if k.strip()]

    last_clip_idx = -999
    cooldown_segs = max(1, int(math.ceil(args.cooldown / seg_dur)))
    pre_segs = max(1, int(math.ceil(args.audio_pre_pad / seg_dur)))
    post_segs = max(1, int(math.ceil(args.post_pad / seg_dur)))
    max_clip_segs = max(3, int(math.ceil(args.max_clip_sec / seg_dur)))
    clips_made = 0

    try:
        for idx, seg in enumerate(segments):
            wav = seg.with_suffix(".16k.wav")
            if not extract_wav_16k(seg, wav):
                continue
            audio_sig = analyze_audio_emotion(wav, rms_history)
            asr = asr_manager.transcribe(wav)
            wav.unlink(missing_ok=True)
            visual_sig = analyze_visual_motion(seg, motion_history, facecam_history, facecam_pos=args.facecam_pos)
            txt_sig = score_transcript_v2(asr["text"], asr["words"], seg_dur, cfg, custom_kw, wps_history)
            chat_sig = {"platform": "offline", "connected": False, "active_chat": False, "is_explosion": False, "score": 0.0}
            fusion = fuse_multimodal_score(
                audio_sig, visual_sig, txt_sig, chat_sig,
                recent_txt_sum=sum(recent_txt),
                channel=channel,
            )
            recent_txt.append(txt_sig["score"])

            ts_label = str(datetime.timedelta(seconds=idx * seg_dur))
            print(
                f"  [{ts_label}] {fusion['tier']:<6} Score={fusion['total_score']:5.1f} "
                f"(aud={audio_sig['score']:4.1f} vis={visual_sig['score']:4.1f} txt={txt_sig['score']:4.1f} syn={fusion['synergy']:+4.1f}) "
                f"[{fusion['archetype']}] | {asr['text'][:65]!r}",
                flush=True,
            )

            if fusion["total_score"] >= args.threshold and (idx - last_clip_idx) >= cooldown_segs:
                gate = float(getattr(args, "min_export_score", 0.0) or 0.0)
                if gate > 0 and fusion["total_score"] < gate:
                    print(
                        f"  >>> SKIPPED (score {fusion['total_score']:.1f} < export gate {gate:.1f}) — B-tier moment not rendered",
                        flush=True,
                    )
                    last_clip_idx = idx
                    continue
                start_i, end_i = compute_clip_window(idx, pre_segs, post_segs, max_clip_segs)
                end_i = min(len(segments) - 1, end_i)
                window = segments[start_i:end_i + 1]
                clip_id = f"{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{channel}_{fusion['tier'].lower()}_s{idx:04d}"
                out_dir = EXPORTS_CLIPS_DIR / channel / clip_id
                raw_stitch = session_dir / f"{clip_id}_raw.ts"

                # Isolate failures per clip: one bad stitch/encode must not abort the VOD scan.
                try:
                    stitch_segments(window, raw_stitch)
                    moment_info = {
                        "clip_id": clip_id,
                        "source": str(src),
                        "stream_offset_sec": idx * seg_dur,
                        "captured_at": datetime.datetime.now().isoformat(),
                        "pre_pad_used": (idx - start_i) * seg_dur,
                        "post_pad_used": (end_i - idx) * seg_dur,
                        "fusion": fusion,
                        "audio": audio_sig,
                        "visual": visual_sig,
                        "transcript_score": txt_sig,
                        "chat": chat_sig,
                    }
                    print(f"  >>> {fusion['tier']} CLIP TRIGGERED! Exporting {clip_id}...", flush=True)
                    mp4 = export_clip_package(
                        raw_stitch, str(src), channel, moment_info, out_dir, args.layout, use_nvenc,
                        smart_trim=not args.no_smart_trim, asr_manager=asr_manager, facecam_pos=args.facecam_pos,
                        max_clip_sec=args.max_clip_sec,
                        enable_punch_zoom=not args.no_punch_zoom,
                        enable_sfx=not args.no_sfx,
                    )
                except Exception as exc:
                    print(
                        f"  >>> EXPORT FAILED for {clip_id}: {exc} — clip skipped, scan continues",
                        flush=True,
                    )
                    raw_stitch.unlink(missing_ok=True)
                    last_clip_idx = idx
                    continue
                raw_stitch.unlink(missing_ok=True)
                print(f"  >>> SAVED: {mp4}", flush=True)
                last_clip_idx = idx
                clips_made += 1
                if args.max_clips and clips_made >= args.max_clips:
                    break
    finally:
        asr_manager.close()
        if not args.keep_buffer:
            shutil.rmtree(session_dir, ignore_errors=True)
    print(f"[LiveClipper v2] Done. Generated {clips_made} clip(s) in {EXPORTS_CLIPS_DIR / channel}", flush=True)


def _spawn_ffmpeg_segmenter(media_url: str, session_dir: Path, segment_sec: int, start_number: int = 0) -> subprocess.Popen:
    ff_cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "warning",
        "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
        "-i", media_url,
        "-c", "copy",
        "-f", "segment",
        "-segment_time", str(segment_sec),
        "-segment_start_number", str(start_number),
        "-reset_timestamps", "1",
        str(session_dir / "seg_%06d.ts"),
    ]
    def _preexec_pdeathsig():
        try:
            import ctypes
            libc = ctypes.CDLL("libc.so.6")
            libc.prctl(1, 15)  # PR_SET_PDEATHSIG, SIGTERM: kills child ffmpeg if python dies
        except Exception:
            pass
    return subprocess.Popen(ff_cmd, preexec_fn=_preexec_pdeathsig)


def run_live_mode(args: argparse.Namespace, cfg: dict, use_nvenc: bool):
    url = args.url
    twitch_ch = extract_twitch_channel(url)
    yt_vid = extract_youtube_video_id(url)
    platform = "twitch" if twitch_ch else ("youtube" if yt_vid else "stream")
    channel = slugify(args.name or twitch_ch or (f"yt-{yt_vid}" if yt_vid else "live-stream"))

    print(f"[LiveClipper v2] Resolving live stream URL for {url}...", flush=True)
    media_url = resolve_stream_url(url, quality=args.quality)
    session_dir = RENDERS_BUFFER_DIR / f"{channel}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    session_dir.mkdir(parents=True, exist_ok=True)

    chat_monitor: BaseChatMonitor | None = None
    if not args.no_chat:
        if twitch_ch:
            chat_monitor = TwitchChatMonitor(twitch_ch, cfg)
            chat_monitor.start()
            print(f"[LiveClipper v2] Attached Twitch IRC explosion monitor -> #{twitch_ch}", flush=True)
        elif yt_vid:
            chat_monitor = YouTubeChatMonitor(yt_vid, cfg)
            chat_monitor.start()
            print(f"[LiveClipper v2] Attached YouTube Live chat & SuperChat monitor -> {yt_vid}", flush=True)

    code_tracker = None
    if getattr(args, "track_code", False):
        from giveaway_code_tracker import GiveawayCodeTracker
        code_tracker = GiveawayCodeTracker(
            target_email=getattr(args, "code_email", "code.mythpat@gmail.com"),
            code_length=getattr(args, "code_length", 6),
            seed_prefix=getattr(args, "code_seed", ""),
            auto_send=getattr(args, "code_auto_send", False),
            subject_template=getattr(args, "code_subject", "{code}"),
            body_template=getattr(args, "code_body", "{code}"),
        )
        if chat_monitor:
            chat_monitor.on_message_callbacks.append(code_tracker.on_chat_message)
        print(
            f"[LiveClipper v2] Giveaway Code Tracker ARMED | Code={code_tracker.current_masked()} "
            f"| Email={code_tracker.target_email} | AutoSend={'ON' if code_tracker.auto_send else 'OFF'}",
            flush=True,
        )

    asr_manager = ASRManager(backend=args.asr, language=args.asr_lang)
    recorder = _spawn_ffmpeg_segmenter(media_url, session_dir, args.segment_sec, start_number=0)

    rms_history: collections.deque[float] = collections.deque(maxlen=40)
    motion_history: collections.deque[float] = collections.deque(maxlen=40)
    facecam_history: collections.deque[float] = collections.deque(maxlen=40)
    wps_history: collections.deque[float] = collections.deque(maxlen=40)
    recent_audio: collections.deque[float] = collections.deque(maxlen=3)
    recent_visual: collections.deque[float] = collections.deque(maxlen=3)
    recent_txt: collections.deque[float] = collections.deque(maxlen=3)
    score_history: collections.deque[dict] = collections.deque(maxlen=36)
    custom_kw = [k.strip() for k in (args.keywords or "").split(",") if k.strip()]

    processed: set[Path] = set()
    pending_clips: list[dict] = []
    failed_clips: list[dict] = []
    groq_batch_queue: list[Path] = []
    groq_queue_since = 0.0
    batch_max_age_sec = 150.0
    exporting_clip: dict | None = None
    export_queue: queue.Queue = queue.Queue()
    export_worker_stop = threading.Event()
    queued_clips: list[dict] = []
    last_trigger_idx = -999
    reconnects = 0
    max_reconnects = 5

    seg_dur = args.segment_sec
    cooldown_segs = max(1, int(math.ceil(args.cooldown / seg_dur)))
    chat_pre_segs = max(1, int(math.ceil(args.chat_pre_pad / seg_dur)))
    audio_pre_segs = max(1, int(math.ceil(args.audio_pre_pad / seg_dur)))
    post_segs = max(1, int(math.ceil(args.post_pad / seg_dur)))
    max_clip_segs = max(3, int(math.ceil(args.max_clip_sec / seg_dur)))
    max_buffer_segs = max(chat_pre_segs + 20, int(math.ceil((args.buffer_minutes * 60) / seg_dur)))

    clips_made = 0
    started_at = time.time()
    latest_segment_data: dict | None = None

    state_file = Path(args.state_file) if getattr(args, "state_file", None) else (RENDERS_BUFFER_DIR / f"state_{channel}.json")

    def persist_state(running: bool = True, status_msg: str = "LISTENING"):
        in_prog = []
        for j in pending_clips:
            in_prog.append({
                "trigger_idx": j["trigger_idx"],
                "stage": "WAITING_POST_PAD",
                "tier": j["moment_info"]["fusion"]["tier"],
                "archetype": j["moment_info"]["fusion"]["archetype"],
                "score": j["peak_score"],
                "start_idx": j["start_idx"],
                "end_idx": j["end_idx"],
                "pre_pad_sec": j["moment_info"]["pre_pad_used"],
                "post_pad_sec": j["moment_info"]["post_pad_used"],
            })
        for q_item in list(queued_clips):
            in_prog.insert(0, {
                "clip_id": q_item["clip_id"],
                "trigger_idx": q_item["trigger_idx"],
                "stage": "QUEUED_RENDER",
                "tier": q_item["tier"],
                "archetype": q_item["archetype"],
                "score": q_item["score"],
            })
        if exporting_clip is not None:
            in_prog.insert(0, exporting_clip)
        payload = {
            "running": running,
            "status": status_msg,
            "pid": os.getpid(),
            "url": url,
            "platform": platform,
            "channel": channel,
            "twitch_channel": twitch_ch,
            "youtube_video_id": yt_vid,
            "started_at": started_at,
            "updated_at": time.time(),
            "threshold": args.threshold,
            "chat_pre_pad": args.chat_pre_pad,
            "audio_pre_pad": args.audio_pre_pad,
            "post_pad": args.post_pad,
            "layout": args.layout,
            "facecam_pos": args.facecam_pos,
            "asr_engine": asr_manager.engine_label,
            "nvenc": use_nvenc,
            "keywords": custom_kw,
            "segments_scanned": len(processed),
            "clips_completed": clips_made,
            "failed_clips": failed_clips[-10:],
            "in_progress_clips": in_prog,
            "latest_segment": latest_segment_data,
            "history": list(score_history),
            "reconnects": reconnects,
            "giveaway_code": code_tracker.get_snapshot() if code_tracker else None,
        }
        write_live_state(payload, state_file)
        write_live_state(payload, LIVE_STATE_FILE)

    persist_state(True, "LISTENING")

    print(
        f"[LiveClipper v2] Listening LIVE | Threshold={args.threshold} | "
        f"Chat-Lookback={args.chat_pre_pad}s | Audio-Lookback={args.audio_pre_pad}s | "
        f"Post-Pad={args.post_pad}s | NVENC={'ON' if use_nvenc else 'CPU'}",
        flush=True,
    )

    def _bg_batch_review_and_upload(
        dirs,
        ch=channel,
        do_auto=bool(getattr(args, "auto_upload", False)),
        min_sc=float(getattr(args, "auto_upload_min_score", 85.0)),
        priv=getattr(args, "upload_privacy", "private"),
        prof=getattr(args, "upload_profile", "clipper"),
        gate=float(getattr(args, "min_export_score", 0.0) or 0.0),
    ):
        reviewed_list = []
        try:
            from scripts.groq_clip_brain import groq_batch_review_clips
            reviewed_list = groq_batch_review_clips(dirs, max_batch=3)
            if reviewed_list:
                summary = ", ".join(
                    f"{r.get('clip_id')}={r.get('final_tier')}({r.get('final_score')})"
                    for r in reviewed_list
                )
                print(f"  [GroqBatch] Reviewed {len(reviewed_list)} clip(s) in 1 API call: {summary}", flush=True)
        except Exception as exc:
            print(f"  [GroqBatch] Skipped batch review ({exc})", flush=True)

        if gate > 0:
            for cdir in list(dirs):
                mj_p = Path(cdir) / "moment.json"
                if not mj_p.exists():
                    continue
                try:
                    fus = json.loads(mj_p.read_text(encoding="utf-8")).get("fusion") or {}
                    sc = float(fus.get("total_score") or 0.0)
                except Exception:
                    continue
                if sc < gate:
                    moved = quarantine_clip(cdir, f"post-review score {sc:.1f} < gate {gate:.1f}", sc)
                    if moved:
                        print(
                            f"  [Gate] Quarantined {Path(cdir).name} (score {sc:.1f} < {gate:.1f}) -> {moved}",
                            flush=True,
                        )

        for cdir in dirs:
            try:
                mj_p = cdir / "moment.json"
                if not mj_p.exists():
                    continue
                mj = json.loads(mj_p.read_text(encoding="utf-8"))
                fus = mj.get("fusion") or {}
                final_sc = float(fus.get("total_score") or 0.0)
                final_tier = str(fus.get("tier") or "").upper()
                from scripts.human_clip_reviewer import AUTO_REVIEW_TIERS, review_clip_as_human
                if final_tier not in AUTO_REVIEW_TIERS and final_sc < min_sc:
                    continue

                h_verdict = "POST"
                try:
                    hrev = review_clip_as_human(cdir)
                    if hrev:
                        h_verdict = str(hrev.get("verdict") or "SKIP")
                        print(
                            f"  [HumanReviewer] {cdir.name}: {h_verdict} ({hrev.get('human_score')}/100) — "
                            f"{hrev.get('gut_reaction')}",
                            flush=True,
                        )
                except Exception as hexc:
                    print(f"  [HumanReviewer] Unavailable ({hexc})", flush=True)

                # In the new workflow, clips are safely staged in the local candidate reel pool.
                # Daily YouTube upload limit & API quota guard protects from exhaustion.
                print(
                    f"  [ReelPool] Candidate staged locally: {cdir.name} (fusion {final_sc}/100, verdict={h_verdict})",
                    flush=True,
                )

                if not do_auto:
                    continue

                from scripts.youtube_uploader import check_daily_upload_quota, upload_video, mark_upload_staged
                from scripts.publish_agent import load_publish_config
                pub_cfg = load_publish_config()
                max_daily = int(pub_cfg.get("daily_upload_limit", 4))
                quota_ok, used_cnt, lim = check_daily_upload_quota(profile=prof, max_per_day=max_daily)
                if not quota_ok:
                    print(
                        f"  [QuotaGuard] YouTube daily limit reached ({used_cnt}/{lim} in 24h). "
                        f"Preserving quota — clip kept in local reel pool for review.",
                        flush=True,
                    )
                    continue

                # Elite curation threshold: Only S-tier POST verdicts trigger direct automated upload
                if h_verdict != "POST" or final_sc < float(pub_cfg.get("min_upload_score", 85.0)):
                    print(
                        f"  [CurationGate] {cdir.name} held in candidate reel (score {final_sc}/100, verdict={h_verdict}). "
                        f"Awaiting scheduled peak window winner selection or manual creator approval.",
                        flush=True,
                    )
                    continue

                print(
                    f"  [YouTube:{prof}] Top S-Tier Winner (score {final_sc}/100 + HUMAN POST) — uploading {cdir.name} ({priv})...",
                    flush=True,
                )
                receipt = upload_video(
                    cdir.name,
                    target_type="clip",
                    channel=ch,
                    overrides={"privacy_status": priv},
                    require_approval=False,
                    approve_now=False,
                    profile=prof,
                    delete_clip_after_upload=False,
                )
                mark_upload_staged(receipt, status="staged")
                try:
                    import scripts.redis_studio as redis_mod
                    redis_mod.push_publish_job(receipt)
                    redis_mod.record_system_event("clip_staged", {
                        "video_id": receipt.get("video_id"),
                        "title": receipt.get("title"),
                        "channel": ch,
                        "score": final_sc,
                    })
                except Exception:
                    pass
                print(
                    f"  >>> UPLOADED ({receipt.get('channel_title') or prof}): "
                    f"{receipt['url']} (Studio: {receipt['studio_url']}) — daily quota {used_cnt + 1}/{lim}",
                    flush=True,
                )
            except Exception as exc:
                print(f"  [YouTube:{prof}] Clip staging/upload note for {cdir.name}: {exc}", flush=True)

    def _export_worker():
        nonlocal clips_made, exporting_clip, groq_queue_since
        while not export_worker_stop.is_set():
            try:
                task = export_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            if task is None:
                export_queue.task_done()
                break

            clip_id = task["clip_id"]
            raw_stitch = task["raw_stitch"]
            out_dir = task["out_dir"]
            tier_tag = task["tier_tag"]
            job_moment_info = task["moment_info"]
            trigger_idx = task["trigger_idx"]
            peak_score = task["peak_score"]

            for idx_q, q_c in enumerate(list(queued_clips)):
                if q_c.get("clip_id") == clip_id:
                    queued_clips.pop(idx_q)
                    break

            exporting_clip = {
                "clip_id": clip_id,
                "trigger_idx": trigger_idx,
                "stage": "EXPORTING_NVENC",
                "tier": job_moment_info["fusion"]["tier"],
                "archetype": job_moment_info["fusion"]["archetype"],
                "score": peak_score,
            }
            persist_state(True, f"EXPORTING {clip_id}")

            try:
                mp4 = export_clip_package(
                    raw_stitch, url, channel, job_moment_info, out_dir, args.layout, use_nvenc,
                    smart_trim=not args.no_smart_trim, asr_manager=asr_manager, facecam_pos=args.facecam_pos,
                    max_clip_sec=args.max_clip_sec,
                    enable_punch_zoom=not args.no_punch_zoom,
                    enable_sfx=not args.no_sfx,
                )
                clips_made += 1
                print(f"  >>> EXPORTED {tier_tag.upper()} CLIP #{clips_made}: {mp4}", flush=True)

                # Prune old clips on the go to maintain keep_max_clips limit
                keep_limit = getattr(args, "keep_max_clips", 20)
                if keep_limit and keep_limit > 0:
                    prune_old_exported_clips(EXPORTS_CLIPS_DIR / channel, max_keep=keep_limit)

                groq_batch_queue.append(out_dir)
                if not groq_queue_since:
                    groq_queue_since = time.time()
                min_auto_sc = float(getattr(args, "auto_upload_min_score", 85.0))
                should_flush = (
                    len(groq_batch_queue) >= 3
                    or float(job_moment_info["fusion"].get("total_score") or 0.0) >= 84.0
                    or (args.max_clips and args.max_clips > 0 and clips_made >= args.max_clips)
                    or (groq_queue_since and time.time() - groq_queue_since >= batch_max_age_sec)
                )
                if should_flush and groq_batch_queue:
                    batch_dirs = list(groq_batch_queue)
                    groq_batch_queue.clear()
                    groq_queue_since = 0.0
                    threading.Thread(
                        target=_bg_batch_review_and_upload,
                        args=(batch_dirs, channel, bool(getattr(args, "auto_upload", False)), min_auto_sc),
                        daemon=True,
                    ).start()
            except Exception as exc:
                print(
                    f"  >>> EXPORT FAILED for {clip_id}: {exc} — clip skipped, session continues",
                    flush=True,
                )
                failed_clips.append({
                    "clip_id": clip_id,
                    "trigger_idx": trigger_idx,
                    "status": "FAILED",
                    "reason": str(exc)[:300],
                    "at": datetime.datetime.now().isoformat(),
                })
            finally:
                raw_stitch.unlink(missing_ok=True)
                exporting_clip = None
                persist_state(True, "LISTENING")
                export_queue.task_done()

    worker_thread = threading.Thread(target=_export_worker, daemon=True)
    worker_thread.start()

    try:
        while True:
            if args.duration_minutes and args.duration_minutes > 0 and (time.time() - started_at) >= args.duration_minutes * 60:
                print("[LiveClipper v2] Reached duration limit. Stopping.", flush=True)
                break

            segs = sorted(session_dir.glob("seg_*.ts"))
            completed = segs[:-1] if recorder.poll() is None else segs

            for seg in completed:
                if seg in processed:
                    continue
                processed.add(seg)
                m = re.search(r"seg_(\d+)\.ts$", seg.name)
                idx = int(m.group(1)) if m else len(processed)

                wav = seg.with_suffix(".16k.wav")
                if not extract_wav_16k(seg, wav):
                    continue

                audio_sig = analyze_audio_emotion(wav, rms_history)
                asr = asr_manager.transcribe(wav)
                wav.unlink(missing_ok=True)
                if code_tracker and asr.get("text"):
                    code_tracker.on_transcript(asr["text"], datetime.datetime.now().strftime("%H:%M:%S"))
                visual_sig = analyze_visual_motion(seg, motion_history, facecam_history, facecam_pos=args.facecam_pos)
                txt_sig = score_transcript_v2(asr["text"], asr["words"], seg_dur, cfg, custom_kw, wps_history)
                chat_sig = (
                    chat_monitor.sample_window_score(seg_dur)
                    if chat_monitor
                    else {"platform": "off", "connected": False, "active_chat": False, "is_explosion": False, "score": 0.0}
                )
                prev_aud_peak = max(recent_audio) if recent_audio else 0.0
                prev_vis_peak = max(recent_visual) if recent_visual else 0.0
                fusion = fuse_multimodal_score(
                    audio_sig, visual_sig, txt_sig, chat_sig,
                    recent_audio_peak=prev_aud_peak,
                    recent_visual_peak=prev_vis_peak,
                    recent_txt_sum=sum(recent_txt),
                    channel=channel,
                    transcript_text=asr["text"],
                )
                recent_audio.append(audio_sig["score"])
                recent_visual.append(visual_sig["score"])
                recent_txt.append(txt_sig["score"])

                now_str = datetime.datetime.now().strftime("%H:%M:%S")
                chat_tag = f"chat={chat_sig['score']:4.1f}({chat_sig.get('ratio', 0):.1f}x)" if chat_monitor else "chat=off"
                print(
                    f"[{now_str}] seg_{idx:04d} | {fusion['tier']:<6} Score={fusion['total_score']:5.1f} "
                    f"({chat_tag} aud={audio_sig['score']:4.1f} vis={visual_sig['score']:4.1f} txt={txt_sig['score']:4.1f} syn={fusion['synergy']:+4.1f}) "
                    f"| {asr['text'][:60]!r}",
                    flush=True,
                )

                latest_segment_data = {
                    "idx": idx,
                    "time": now_str,
                    "total_score": fusion["total_score"],
                    "tier": fusion["tier"],
                    "archetype": fusion["archetype"],
                    "trigger_source": fusion["trigger_source"],
                    "synergy": fusion["synergy"],
                    "synergy_reasons": fusion["synergy_reasons"],
                    "chat": chat_sig,
                    "audio": audio_sig,
                    "visual": visual_sig,
                    "transcript_score": txt_sig,
                    "transcript": asr["text"],
                }
                score_history.append({
                    "idx": idx,
                    "time": now_str,
                    "total": fusion["total_score"],
                    "chat": chat_sig["score"],
                    "audio": audio_sig["score"],
                    "visual": visual_sig["score"],
                    "txt": txt_sig["score"],
                    "tier": fusion["tier"],
                    "triggered": fusion["total_score"] >= args.threshold,
                })

                # Dynamic Peak Extension: if a pending clip is still collecting post-pad and the moment keeps escalating, ride the peak!
                extended_existing = False
                for job in pending_clips:
                    if idx <= job["end_idx"] and fusion["total_score"] >= max(args.threshold * 0.85, job["peak_score"] - 5.0):
                        new_start, new_end = extend_clip_window(
                            job["start_idx"], job["end_idx"], job["trigger_idx"], idx, post_segs, max_clip_segs
                        )
                        if new_end > job["end_idx"]:
                            job["start_idx"] = new_start
                            job["end_idx"] = new_end
                            job["moment_info"]["pre_pad_used"] = (job["trigger_idx"] - new_start) * seg_dur
                            job["moment_info"]["post_pad_used"] = (new_end - job["trigger_idx"]) * seg_dur
                            if fusion["total_score"] > job["peak_score"]:
                                job["peak_score"] = fusion["total_score"]
                                job["moment_info"]["fusion"] = fusion
                                job["moment_info"]["chat"] = chat_sig
                                job["moment_info"]["audio"] = audio_sig
                            print(f"  >>> MOMENT ESCALATING (score {fusion['total_score']})! Extending clip window to seg_{new_end:04d}...", flush=True)
                        extended_existing = True
                        break

                export_gate = float(getattr(args, "min_export_score", 0.0) or 0.0)
                below_gate = export_gate > 0 and fusion["total_score"] < export_gate
                if not extended_existing and below_gate and fusion["total_score"] >= args.threshold:
                    print(
                        f"  >>> GATED (score {fusion['total_score']:.1f} < export gate {export_gate:.1f}) — B-tier moment not rendered",
                        flush=True,
                    )

                if not extended_existing and not below_gate and fusion["total_score"] >= args.threshold and (idx - last_trigger_idx) >= cooldown_segs:
                    last_trigger_idx = idx
                    # KEY FEATURE: Look back 30s BEFORE chat explosions (covering stream lag + buildup!)
                    pre_segs_use = chat_pre_segs if fusion["trigger_source"] == "chat_explosion" else audio_pre_segs
                    start_idx, end_idx = compute_clip_window(idx, pre_segs_use, post_segs, max_clip_segs)

                    pending_clips.append({
                        "trigger_idx": idx,
                        "start_idx": start_idx,
                        "end_idx": end_idx,
                        "peak_score": fusion["total_score"],
                        "moment_info": {
                            "source": url,
                            "stream_offset_sec": idx * seg_dur,
                            "captured_at": datetime.datetime.now().isoformat(),
                            "pre_pad_used": (idx - start_idx) * seg_dur,
                            "post_pad_used": (end_idx - idx) * seg_dur,
                            "fusion": fusion,
                            "audio": audio_sig,
                            "visual": visual_sig,
                            "transcript_score": txt_sig,
                            "chat": chat_sig,
                        },
                    })
                    print(
                        f"  >>> {fusion['tier']} LIVE MOMENT ({fusion['archetype']}, score={fusion['total_score']})! "
                        f"Lookback={(idx - start_idx) * seg_dur}s before peak; collecting {(end_idx - idx) * seg_dur}s post-pad...",
                        flush=True,
                    )

                persist_state(True, "LISTENING")

            latest_completed_idx = -1
            if completed:
                m_last = re.search(r"seg_(\d+)\.ts$", completed[-1].name)
                if m_last:
                    latest_completed_idx = int(m_last.group(1))

            still_pending = []
            for job in pending_clips:
                if latest_completed_idx >= job["end_idx"] or recorder.poll() is not None:
                    window = [
                        session_dir / f"seg_{i:06d}.ts"
                        for i in range(job["start_idx"], job["end_idx"] + 1)
                        if (session_dir / f"seg_{i:06d}.ts").exists()
                    ]
                    if window:
                        tier_tag = job["moment_info"]["fusion"]["tier"].lower()
                        clip_id = f"{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{channel}_{tier_tag}_s{job['trigger_idx']:04d}"
                        out_dir = EXPORTS_CLIPS_DIR / channel / clip_id
                        raw_stitch = session_dir / f"{clip_id}_raw.ts"
                        try:
                            stitch_segments(window, raw_stitch)
                            job["moment_info"]["clip_id"] = clip_id
                            queued_clips.append({
                                "clip_id": clip_id,
                                "trigger_idx": job["trigger_idx"],
                                "tier": job["moment_info"]["fusion"]["tier"],
                                "archetype": job["moment_info"]["fusion"]["archetype"],
                                "score": job["peak_score"],
                            })
                            print(f"  >>> ENQUEUED {tier_tag.upper()} CLIP: {clip_id} (rendering in background without pausing live loop)", flush=True)
                            export_queue.put({
                                "clip_id": clip_id,
                                "raw_stitch": raw_stitch,
                                "out_dir": out_dir,
                                "tier_tag": tier_tag,
                                "moment_info": job["moment_info"],
                                "trigger_idx": job["trigger_idx"],
                                "peak_score": job["peak_score"],
                            })
                        except Exception as exc:
                            print(f"  >>> STITCH FAILED for {clip_id}: {exc}", flush=True)
                            raw_stitch.unlink(missing_ok=True)
                        persist_state(True, "LISTENING")
                else:
                    still_pending.append(job)
            pending_clips = still_pending

            # Protect disk space: prune segments older than max_buffer_segs AND older than any lookback/pending job
            safe_floor = min(
                [j["start_idx"] for j in pending_clips],
                default=max(0, latest_completed_idx - max(chat_pre_segs, audio_pre_segs) - 2),
            )
            if len(completed) > max_buffer_segs:
                for old_seg in completed[:-max_buffer_segs]:
                    m_old = re.search(r"seg_(\d+)\.ts$", old_seg.name)
                    if m_old and int(m_old.group(1)) < safe_floor:
                        old_seg.unlink(missing_ok=True)

            if args.max_clips and args.max_clips > 0 and clips_made >= args.max_clips:
                print(f"[LiveClipper v2] Reached --max-clips={args.max_clips}. Stopping.", flush=True)
                break

            if recorder.poll() is not None:
                if reconnects < max_reconnects:
                    reconnects += 1
                    print(f"[LiveClipper v2] Stream blip detected. Auto-reconnecting ({reconnects}/{max_reconnects})...", flush=True)
                    persist_state(True, f"RECONNECTING ({reconnects}/{max_reconnects})")
                    time.sleep(2.5)
                    try:
                        media_url = resolve_stream_url(url, quality=args.quality)
                        next_num = latest_completed_idx + 1 if latest_completed_idx >= 0 else len(processed)
                        recorder = _spawn_ffmpeg_segmenter(media_url, session_dir, args.segment_sec, start_number=next_num)
                        persist_state(True, "LISTENING")
                        continue
                    except Exception as e:
                        print(f"[LiveClipper v2] Reconnect failed: {e}", flush=True)
                print("[LiveClipper v2] Stream ended or ffmpeg exited.", flush=True)
                break

            time.sleep(1.5)
    except KeyboardInterrupt:
        print("\n[LiveClipper v2] Interrupted by user. Shutting down cleanly...", flush=True)
    finally:
        export_worker_stop.set()
        export_queue.put(None)
        # Flush any A/S clip still queued so it leaves the session with a human verdict.
        if groq_batch_queue:
            auto_review_tier_clips(groq_batch_queue, tag="AutoReview:exit")
        persist_state(False, "STOPPED")
        asr_manager.close()
        if chat_monitor:
            chat_monitor.stop()
        if recorder.poll() is None:
            recorder.terminate()
            try:
                recorder.wait(timeout=5)
            except subprocess.TimeoutExpired:
                recorder.kill()
        if not args.keep_buffer:
            shutil.rmtree(session_dir, ignore_errors=True)
        print(f"[LiveClipper v2] Session complete. Total clips saved: {clips_made}", flush=True)


def main():
    cfg = load_signal_config()
    t_cfg = cfg.get("timing", {})

    parser = argparse.ArgumentParser(
        description="CreatorRadar Live Stream Viral Clipper v2 (Twitch + YouTube Chat Explosions + Audio Emotion + Visual + Whistle)"
    )
    src_group = parser.add_mutually_exclusive_group(required=True)
    src_group.add_argument("--url", help="Live Twitch or YouTube stream URL")
    src_group.add_argument("--input", help="Local video/VOD file path to scan & auto-clip offline")

    parser.add_argument("--name", default=None, help="Channel/project name for output folder")
    parser.add_argument("--keywords", default="", help="Extra comma-separated niche keywords (merged with config/clipper-signals.json)")
    parser.add_argument("--threshold", type=float, default=72.0, help="Virality trigger score 0-100 (default: 72 = A-tier floor; clamped up to --min-export-score)")
    parser.add_argument(
        "--min-export-score",
        type=float,
        default=72.0,
        help="Hard floor for rendering a clip. Moments below this score are never exported "
        "(default: 72 = A-tier floor from config/viral-style-bible.json; set 0 to disable)",
    )
    parser.add_argument("--segment-sec", type=int, default=int(t_cfg.get("segment_sec", 10)), help="Rolling segment chunk size in seconds (default: 10)")
    parser.add_argument("--chat-pre-pad", type=int, default=int(t_cfg.get("chat_pre_pad_sec", 30)), help="Seconds BEFORE a chat explosion to start clip (default: 30)")
    parser.add_argument("--audio-pre-pad", type=int, default=int(t_cfg.get("audio_pre_pad_sec", 20)), help="Seconds BEFORE an audio/speech trigger to start clip (default: 20)")
    parser.add_argument("--post-pad", type=int, default=int(t_cfg.get("post_pad_sec", 12)), help="Seconds AFTER peak to capture reaction (default: 12)")
    parser.add_argument("--max-clip-sec", type=int, default=int(t_cfg.get("max_clip_sec", 60)), help="Maximum clip length during peak escalation (default: 60)")
    parser.add_argument("--cooldown", type=int, default=int(t_cfg.get("cooldown_sec", 45)), help="Minimum seconds between separate clips (default: 45)")
    parser.add_argument("--layout", choices=["split-blur", "facecam-split", "pip-overlay", "crop", "landscape"], default="split-blur", help="Output framing (default: split-blur 9:16)")
    parser.add_argument("--facecam-pos", choices=["top-right", "top-left", "bottom-right", "bottom-left"], default="top-right", help="Streamer webcam corner for facecam-split layout (default: top-right)")
    parser.add_argument("--asr", choices=["modal", "hinglish", "whisper", "whistle"], default="hinglish", help="ASR backend: modal (Remote T4 Cloud GPU), hinglish (Local Whisper-Hinglish-Apex CUDA), whisper (whisper-small CUDA), or whistle (16.9MB EN CPU)")
    parser.add_argument("--asr-lang", choices=["auto", "hi", "en"], default="auto", help="ASR language hint (auto, hi, en)")
    parser.add_argument("--quality", default="best", help="Streamlink quality selector (default: best)")
    parser.add_argument("--buffer-minutes", type=int, default=10, help="Max rolling live buffer kept on disk in minutes (default: 10)")
    parser.add_argument("--duration-minutes", type=float, default=0.0, help="Auto-stop live listener after N minutes (0 = unlimited)")
    parser.add_argument("--max-clips", type=int, default=0, help="Stop after exporting N clips (0 = unlimited)")
    parser.add_argument("--no-chat", action="store_true", help="Disable live Twitch/YouTube chat monitor")
    parser.add_argument("--no-smart-trim", action="store_true", help="Disable Whistle sentence-boundary leading trim")
    parser.add_argument("--no-punch-zoom", action="store_true", help="Disable dynamic reaction-peak punch-in zooms")
    parser.add_argument("--no-sfx", action="store_true", help="Disable synchronized opening pop & reaction-peak SFX hits")
    parser.add_argument("--keep-buffer", action="store_true", help="Keep temporary .ts segments after exit")
    parser.add_argument("--cpu", action="store_true", help="Force CPU libx264 instead of NVIDIA NVENC")
    parser.add_argument("--state-file", default=None, help="Optional per-channel JSON telemetry state file path")
    parser.add_argument("--auto-upload", action="store_true", help="Owner opt-in: automatically stage clips scoring >= --auto-upload-min-score to the connected Live Clipper YouTube channel as PRIVATE drafts for the publish agent")
    parser.add_argument("--auto-upload-min-score", type=float, default=85.0, help="Minimum fusion score to stage as a private draft for --auto-upload (default: 85.0). scripts/publish_agent.py then publishes POST verdicts at the peak window and deletes the rest.")
    parser.add_argument("--upload-privacy", choices=["private", "unlisted", "public"], default="private", help="Privacy for --auto-upload (default: private YouTube Studio drafts)")
    parser.add_argument("--upload-profile", choices=["clipper"], default="clipper", help="Locked to 'clipper' (ClipSurge) so live clips never upload to Paper Trail")
    parser.add_argument("--track-code", action="store_true", help="Enable live giveaway digit-by-digit code tracker (ASR + YouTube chat consensus)")
    parser.add_argument("--code-seed", default="", help="Seed already-confirmed leading giveaway digits (e.g. '7523')")
    parser.add_argument("--code-length", type=int, default=6, help="Total digits in giveaway code (default: 6)")
    parser.add_argument("--code-email", default="code.mythpat@gmail.com", help="Recipient email for auto-dispatching completed code")
    parser.add_argument("--code-auto-send", action="store_true", help="Automatically dispatch Gmail SMTP email once all code digits are confirmed")
    parser.add_argument("--code-subject", default="{code}", help="Subject template for auto-dispatched giveaway email")
    parser.add_argument("--code-body", default="{code}", help="Body template for auto-dispatched giveaway email")
    parser.add_argument("--continuous", action="store_true", help="Run indefinitely without clip count or time limits")
    parser.add_argument("--keep-max-clips", type=int, default=20, help="Max exported clips to retain per channel on disk before auto-pruning oldest clips (default: 20; 0 = unlimited)")
    args = parser.parse_args()

    if args.continuous:
        args.max_clips = 0
        args.duration_minutes = 0.0

    # The export gate is the product contract: a moment that is not good enough to render
    # must never become a clip at all. A lower --threshold (UI preset, stale state file)
    # would only manufacture lower-tier folders that the gate then quarantines, so the
    # trigger score is clamped up to the gate. Set --min-export-score 0 to disable the gate.
    export_gate = float(getattr(args, "min_export_score", 0.0) or 0.0)
    if export_gate > 0 and args.threshold < export_gate:
        print(
            f"[LiveClipper v2] Threshold {args.threshold:g} is below the export gate "
            f"{export_gate:g}; raising trigger to {export_gate:g} so sub-gate clips are never created."
        )
        args.threshold = export_gate

    use_nvenc = (not args.cpu) and detect_nvenc()
    if args.input:
        run_vod_or_local_mode(args, cfg, use_nvenc)
    else:
        run_live_mode(args, cfg, use_nvenc)


if __name__ == "__main__":
    main()
