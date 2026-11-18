#!/usr/bin/env python3
"""
CreatorRadar Live Audio Code Listener (PipeWire/PulseAudio -> CUDA Hinglish Whisper -> Instant Gmail Dispatch)
=============================================================================================================
Listens directly to the local desktop/browser audio monitor playing Mythpat's
livestream, transcribes every 6-second chunk on local RTX GPU via
Oriserve/Whisper-Hindi2Hinglish-Apex, extracts newly announced giveaway code
digits, and dispatches the email immediately via `gmail mutate send` (or SMTP
fallback) the moment all 6 digits are confirmed.
"""

from __future__ import annotations

import argparse
import collections
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from giveaway_code_tracker import send_gmail_smtp  # noqa: E402

RENDERS_BUFFER_DIR = ROOT / "renders" / "live_buffer"
TRANSCRIPT_LOG = RENDERS_BUFFER_DIR / "mythpat_live_transcript.log"
ALERTS_LOG = RENDERS_BUFFER_DIR / "mythpat_code_alerts.log"
STATE_FILE = RENDERS_BUFFER_DIR / "giveaway_code_state.json"
ASR_WORKER_SCRIPT = SCRIPTS_DIR / "whisper_asr_worker.py"
VOICESTUDIO_PYTHON = ROOT / "VoiceStudio" / ".venv" / "bin" / "python"

# Spoken digit words (carefully guarded against common Hindi non-digit idioms like "ek second", "bata do", "saath mein")
SPOKEN_DIGITS: dict[str, str] = {
    "0": "0", "zero": "0", "shunya": "0", "sunya": "0",
    "1": "1", "one": "1", "ek": "1",
    "2": "2", "two": "2", "do": "2",
    "3": "3", "three": "3", "teen": "3", "tin": "3",
    "4": "4", "four": "4", "char": "4", "chaar": "4",
    "5": "5", "five": "5", "panch": "5", "paanch": "5",
    "6": "6", "six": "6", "chhe": "6", "che": "6", "chhah": "6",
    "7": "7", "seven": "7", "saat": "7", "sat": "7",
    "8": "8", "eight": "8", "aath": "8", "ath": "8",
    "9": "9", "nine": "9", "nau": "9",
}

DIGIT_TOKEN_PAT = (
    r"(?:[0-9]|zero|shunya|sunya|one|ek|two|do|three|teen|tin|four|char|chaar|"
    r"five|panch|paanch|six|chhe|che|chhah|seven|saat|sat|eight|aath|ath|nine|nau)"
)

CODE_MENTION_RE = re.compile(
    r"\b(code|kod|digit|digits|number|mail|email|gmail|giveaway|fifth|sixth|5th|6th|paanchva|panchva|chhatha|aakhri|last\s+digit|final\s+digit|next\s+digit|agla\s+digit|7523)\b",
    re.I,
)

# Guard phrases where "ek"/"do"/"saat" are NOT digits
NON_DIGIT_FOLLOWERS = {
    "second", "sec", "minute", "min", "baat", "baar", "bar", "mein", "me",
    "digit", "digits", "code", "codes", "number", "numbers", "sath", "saath",
    "baje", "ghanta", "mahine", "saal", "din", "banda", "ladka", "log",
}
NON_DIGIT_PREDECESSORS = {
    "bata", "batao", "de", "kar", "karo", "chhod", "chhodo", "bol", "bolo",
    "bhej", "bhejo", "dikh", "dekho", "jaane", "jane", "ruko", "sun", "suno",
    "ham", "hum", "aap", "tum",
}


def detect_active_monitor_source() -> str:
    """Find the active PipeWire/PulseAudio monitor source."""
    res = subprocess.run(
        ["pactl", "list", "short", "sources"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    running_monitors = []
    idle_monitors = []
    all_monitors = []
    for line in res.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        name = parts[1].strip()
        state = parts[-1].strip().upper() if len(parts) >= 5 else ""
        if ".monitor" in name:
            all_monitors.append(name)
            if state == "RUNNING":
                running_monitors.append(name)
            elif state == "IDLE":
                idle_monitors.append(name)
    if running_monitors:
        return running_monitors[0]
    if idle_monitors:
        return idle_monitors[0]
    if all_monitors:
        return all_monitors[0]
    raise RuntimeError("No PipeWire/PulseAudio .monitor source found.")


def _parse_digit_token(tok: str, prev_tok: str = "", next_tok: str = "") -> str | None:
    t = tok.lower().strip(".,!?;:\"'()")
    if t not in SPOKEN_DIGITS:
        return None
    if t in ("ek", "do", "saat", "sat"):
        if next_tok.lower().strip(".,!?") in NON_DIGIT_FOLLOWERS:
            return None
        if t == "do" and prev_tok.lower().strip(".,!?") in NON_DIGIT_PREDECESSORS:
            return None
    return SPOKEN_DIGITS[t]


def extract_code_updates_from_text(text: str, current_digits: dict[int, str], code_length: int = 6) -> list[tuple[int, str, str]]:
    """
    Extract high-confidence (slot, digit, reason) updates from Hinglish/English ASR text.
    Only locks digits when phrased as explicit code/digit announcements.
    """
    if not text or not CODE_MENTION_RE.search(text):
        return []

    clean = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
    clean = re.sub(r"\s+", " ", clean).strip()
    updates: list[tuple[int, str, str]] = []

    prefix = "".join(current_digits.get(i, "") for i in range(1, 5))

    # 1) Full 6-digit sequence spoken aloud starting with known prefix (e.g. "7 5 2 3 8 9" or "752389")
    if len(prefix) == 4:
        # Map spoken words to digits in a normalized digit-stream only near the prefix
        p_pat = r"\s*".join(list(prefix))
        m_full = re.search(rf"\b{p_pat}\s*({DIGIT_TOKEN_PAT})\s*(?:and|aur)?\s*({DIGIT_TOKEN_PAT})\b", clean)
        if m_full:
            d5 = _parse_digit_token(m_full.group(1))
            d6 = _parse_digit_token(m_full.group(2))
            if d5 and 5 not in current_digits:
                updates.append((5, d5, f"full_code_spoken: {m_full.group(0)}"))
            if d6 and 6 not in current_digits:
                updates.append((6, d6, f"full_code_spoken: {m_full.group(0)}"))
            if updates:
                return updates

        m_five = re.search(rf"\b{p_pat}\s*({DIGIT_TOKEN_PAT})\b", clean)
        if m_five:
            d5 = _parse_digit_token(m_five.group(1))
            if d5 and 5 not in current_digits:
                updates.append((5, d5, f"five_digit_spoken: {m_five.group(0)}"))
                return updates

    # 2) Both last digits announced together ("last two digits are 8 and 9", "last do digit 8 9", "fifth and sixth digit 8 9")
    m_pair = re.search(
        rf"\b(?:last\s+(?:two|2|do)|final\s+(?:two|2|do)|aakhri\s+(?:two|2|do)|dono|fifth\s+and\s+sixth|5th\s+and\s+6th|5th\s+6th)\s+"
        rf"(?:digits?|codes?|numbers?)\s*(?:are|is|hain|hai)?\s*({DIGIT_TOKEN_PAT})\s*(?:and|aur|or)?\s*({DIGIT_TOKEN_PAT})\b",
        clean,
    )
    if m_pair:
        d5 = _parse_digit_token(m_pair.group(1))
        d6 = _parse_digit_token(m_pair.group(2))
        if d5 and 5 not in current_digits:
            updates.append((5, d5, f"pair_spoken: {m_pair.group(0)}"))
        if d6 and 6 not in current_digits:
            updates.append((6, d6, f"pair_spoken: {m_pair.group(0)}"))
        if updates:
            return updates

    # Also catch 2-digit number right after "last two digits are 89"
    m_pair2 = re.search(
        r"\b(?:last\s+(?:two|2|do)|final\s+(?:two|2|do)|aakhri\s+(?:two|2|do)|dono)\s+"
        r"(?:digits?|codes?|numbers?)\s*(?:are|is|hain|hai)?\s*(\d)(\d)\b",
        clean,
    )
    if m_pair2:
        if 5 not in current_digits:
            updates.append((5, m_pair2.group(1), f"pair2_spoken: {m_pair2.group(0)}"))
        if 6 not in current_digits:
            updates.append((6, m_pair2.group(2), f"pair2_spoken: {m_pair2.group(0)}"))
        if updates:
            return updates

    # 3) Explicit 5th digit announcement
    if 5 not in current_digits:
        m5 = re.search(
            rf"\b(?:5th|fifth|paanchva|panchva|panchwa|paanchwa|next|agla|agle)\s+"
            rf"(?:digit|code|kod|number)\s*(?:is|hai|hoga|rahega)?\s*({DIGIT_TOKEN_PAT})\b",
            clean,
        )
        if m5:
            tok = m5.group(1)
            after = clean[m5.end():].strip().split()[:1]
            next_tok = after[0] if after else ""
            d5 = _parse_digit_token(tok, prev_tok="is", next_tok=next_tok)
            if d5:
                updates.append((5, d5, f"explicit_5th: {m5.group(0)}"))

        # Reverse Hindi phrasing: "5th digit ... 8 hai" or "agla digit ... 8 hai"
        if not updates:
            m5_hi = re.search(
                rf"\b(?:5th|fifth|paanchva|panchva|next|agla)\s+(?:digit|code|kod|number)\s+\w{{0,12}}\s*({DIGIT_TOKEN_PAT})\s+(?:hai|he)\b",
                clean,
            )
            if m5_hi:
                d5 = _parse_digit_token(m5_hi.group(1), prev_tok="code", next_tok="hai")
                if d5:
                    updates.append((5, d5, f"explicit_5th_hi: {m5_hi.group(0)}"))

    # 4) Explicit 6th / last / final digit announcement
    if 6 not in current_digits:
        m6 = re.search(
            rf"\b(?:6th|sixth|chhatha|chatha|last|final|aakhri|aakhiri)\s+"
            rf"(?:digit|code|kod|number)\s*(?:is|hai|hoga|rahega)?\s*({DIGIT_TOKEN_PAT})\b",
            clean,
        )
        if m6:
            tok = m6.group(1)
            after = clean[m6.end():].strip().split()[:1]
            next_tok = after[0] if after else ""
            d6 = _parse_digit_token(tok, prev_tok="is", next_tok=next_tok)
            if d6:
                updates.append((6, d6, f"explicit_6th: {m6.group(0)}"))

        if not any(u[0] == 6 for u in updates):
            m6_hi = re.search(
                rf"\b(?:6th|sixth|chhatha|last|final|aakhri)\s+(?:digit|code|kod|number)\s+\w{{0,12}}\s*({DIGIT_TOKEN_PAT})\s+(?:hai|he)\b",
                clean,
            )
            if m6_hi:
                d6 = _parse_digit_token(m6_hi.group(1), prev_tok="code", next_tok="hai")
                if d6:
                    updates.append((6, d6, f"explicit_6th_hi: {m6_hi.group(0)}"))

    return updates


def dispatch_email_now(to_email: str, subject: str, body: str) -> dict:
    """
    Dispatch email immediately:
      1) Try official Antigravity `gmail mutate send` CLI first (connected OAuth account)
      2) Fall back to Gmail SMTP (`GMAIL_USER` / `GMAIL_APP_PASSWORD`) if `gmail` CLI unavailable
    """
    gmail_bin = shutil.which("gmail") or str(Path.home() / ".gemini" / "antigravity" / "bin" / "gmail")
    if Path(gmail_bin).exists():
        try:
            res = subprocess.run(
                [gmail_bin, "mutate", "send", "--to", to_email, "--subject", subject, "--body", body],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if res.returncode == 0:
                return {
                    "ok": True,
                    "method": "gmail_plugin_cli",
                    "to": to_email,
                    "subject": subject,
                    "stdout": res.stdout.strip(),
                    "sent_at": datetime.datetime.now().isoformat(),
                }
            cli_err = (res.stderr or res.stdout or "").strip()
        except Exception as exc:
            cli_err = str(exc)
    else:
        cli_err = "gmail CLI not found"

    smtp_res = send_gmail_smtp(to_email, subject, body)
    if smtp_res.get("ok"):
        smtp_res["method"] = "gmail_smtp"
        return smtp_res
    return {
        "ok": False,
        "method": "failed",
        "gmail_cli_error": cli_err,
        "smtp_error": smtp_res.get("error"),
    }


class PersistentWhisperClient:
    def __init__(self, model_id: str = "Oriserve/Whisper-Hindi2Hinglish-Apex", language: str = "hi"):
        self.model_id = model_id
        self.language = language
        py_bin = str(VOICESTUDIO_PYTHON) if VOICESTUDIO_PYTHON.exists() else sys.executable
        cmd = [py_bin, str(ASR_WORKER_SCRIPT), "--model", self.model_id, "--device", "auto"]
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,
            text=True,
            bufsize=1,
        )
        ready_line = self.proc.stdout.readline() if self.proc.stdout else ""
        info = json.loads(ready_line) if ready_line.strip().startswith("{") else {}
        if not info.get("ready"):
            raise RuntimeError(f"Whisper ASR worker failed to initialize: {ready_line!r}")
        self.engine = info.get("engine", self.model_id)

    def transcribe(self, wav_path: Path) -> str:
        if not self.proc or self.proc.poll() is not None:
            return ""
        req = json.dumps({"wav": str(wav_path.resolve()), "language": self.language})
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(req + "\n")
        self.proc.stdin.flush()
        resp_line = self.proc.stdout.readline()
        if not resp_line:
            return ""
        data = json.loads(resp_line)
        return str(data.get("text") or "").strip()

    def close(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=4)
            except Exception:
                self.proc.kill()


def save_state(digits: dict[int, str], meta: dict[int, dict], target_email: str, code_length: int,
               auto_send: bool, recent_transcripts: list[dict], code_alerts: list[dict],
               dispatched: dict | None):
    masked = "".join(digits.get(i, "_") for i in range(1, code_length + 1))
    payload = {
        "updated_at": datetime.datetime.now().isoformat(),
        "mode": "live_audio_whisper",
        "target_email": target_email,
        "code_length": code_length,
        "current_code": masked,
        "is_complete": all(i in digits for i in range(1, code_length + 1)),
        "auto_send_enabled": auto_send,
        "digits": {str(k): meta[k] for k in sorted(meta.keys())},
        "dispatched": dispatched,
        "code_alerts": code_alerts[-20:],
        "recent_transcripts": recent_transcripts[-15:],
    }
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)


def main():
    parser = argparse.ArgumentParser(description="Live Audio Transcriber & Auto-Email Giveaway Code Listener")
    parser.add_argument("--pulse-source", default=None, help="PipeWire/PulseAudio monitor source (auto-detected if omitted)")
    parser.add_argument("--seed", default="7523", help="Already confirmed leading digits (default: 7523)")
    parser.add_argument("--length", type=int, default=6, help="Total code digits (default: 6)")
    parser.add_argument("--email", default="code.mythpat@gmail.com", help="Recipient email")
    parser.add_argument("--subject", default="{code}", help="Email subject template")
    parser.add_argument("--body", default="{code}", help="Email body template")
    parser.add_argument("--chunk-sec", type=int, default=6, help="Audio transcription chunk duration in seconds (default: 6)")
    parser.add_argument("--auto-send", action="store_true", help="Automatically dispatch email as soon as all 6 digits lock")
    parser.add_argument("--stop-when-complete", action="store_true", help="Exit cleanly right after email dispatch")
    parser.add_argument("--model", default="Oriserve/Whisper-Hindi2Hinglish-Apex", help="Whisper model ID")
    args = parser.parse_args()

    source = args.pulse_source or detect_active_monitor_source()
    digits: dict[int, str] = {}
    meta: dict[int, dict] = {}
    for i, ch in enumerate(re.sub(r"\D", "", args.seed)[: args.length], start=1):
        digits[i] = ch
        meta[i] = {
            "digit": ch,
            "source": "seed",
            "confirmed_at": datetime.datetime.now().isoformat(),
            "evidence": f"Seeded prefix '{args.seed}'",
        }

    work_dir = RENDERS_BUFFER_DIR / "audio_code_watch"
    if work_dir.exists():
        shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    print(f"[AudioCodeListener] Loading CUDA Hinglish Whisper ({args.model})...", flush=True)
    asr = PersistentWhisperClient(model_id=args.model, language="hi")
    print(
        f"[AudioCodeListener] ARMED & LISTENING LIVE!\n"
        f"  Audio source : {source}\n"
        f"  ASR engine   : {asr.engine}\n"
        f"  Code so far  : {''.join(digits.get(i, '_') for i in range(1, args.length + 1))}\n"
        f"  Target email : {args.email} | Auto-send: {'ON' if args.auto_send else 'OFF'}\n"
        f"  Transcript   : {TRANSCRIPT_LOG}\n",
        flush=True,
    )

    ff_cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "pulse", "-i", source,
        "-ac", "1", "-ar", "16000",
        "-f", "segment", "-segment_time", str(args.chunk_sec),
        "-reset_timestamps", "1",
        str(work_dir / "chunk_%06d.wav"),
    ]
    rec = subprocess.Popen(ff_cmd)

    processed: set[Path] = set()
    recent_transcripts: list[dict] = []
    code_alerts: list[dict] = []
    prev_text = ""
    silent_streak = 0
    dispatched: dict | None = None

    save_state(digits, meta, args.email, args.length, args.auto_send, recent_transcripts, code_alerts, dispatched)

    try:
        while True:
            chunks = sorted(work_dir.glob("chunk_*.wav"))
            completed = chunks[:-1] if rec.poll() is None else chunks

            for wav in completed:
                if wav in processed:
                    continue
                processed.add(wav)

                try:
                    samples, _ = sf.read(str(wav))
                    rms = float(np.sqrt(np.mean(samples ** 2))) if len(samples) else 0.0
                except Exception:
                    rms = 0.0

                ts = datetime.datetime.now().strftime("%H:%M:%S")
                if rms < 0.0004:
                    silent_streak += 1
                    if silent_streak in (3, 10, 30):
                        print(f"[{ts}] [AudioCodeListener] WARNING: Stream audio is SILENT (rms={rms:.5f}). Unmute the YouTube player!", flush=True)
                    wav.unlink(missing_ok=True)
                    continue

                silent_streak = 0
                text = asr.transcribe(wav)
                wav.unlink(missing_ok=True)
                if not text:
                    continue

                line = f"[{ts}] {text}"
                print(line, flush=True)
                with TRANSCRIPT_LOG.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")

                recent_transcripts.append({"time": ts, "text": text})
                if len(recent_transcripts) > 40:
                    recent_transcripts = recent_transcripts[-40:]

                # Scan combined window (prev tail + current) so digits split across chunk boundaries are caught!
                combined = (prev_text[-120:] + " " + text).strip()
                prev_text = text

                if CODE_MENTION_RE.search(text):
                    alert_entry = {"time": ts, "text": text}
                    code_alerts.append(alert_entry)
                    with ALERTS_LOG.open("a", encoding="utf-8") as f:
                        f.write(f"[{ts}] CODE MENTION: {text}\n")
                    print(f"\a[{ts}] >>> CODE MENTION DETECTED: {text}", flush=True)

                updates = extract_code_updates_from_text(combined, digits, args.length)
                for slot, dig, reason in updates:
                    if slot not in digits:
                        digits[slot] = dig
                        meta[slot] = {
                            "digit": dig,
                            "source": "live_audio_whisper",
                            "confirmed_at": datetime.datetime.now().isoformat(),
                            "evidence": f"{reason} | {text[:160]}",
                        }
                        masked = "".join(digits.get(i, "_") for i in range(1, args.length + 1))
                        print(
                            f"\a\n========================================================\n"
                            f"[{ts}] >>> LOCKED DIGIT #{slot} = {dig} | CODE: {masked}\n"
                            f"    Reason: {reason}\n"
                            f"    Audio : {text}\n"
                            f"========================================================\n",
                            flush=True,
                        )

                if all(i in digits for i in range(1, args.length + 1)) and dispatched is None:
                    full_code = "".join(digits[i] for i in range(1, args.length + 1))
                    print(
                        f"\a\a\n"
                        f"********************************************************\n"
                        f"  ALL {args.length} DIGITS TRANSCRIBED: {full_code}\n"
                        f"********************************************************\n",
                        flush=True,
                    )
                    if args.auto_send:
                        subj = args.subject.format(code=full_code)
                        body = args.body.format(code=full_code)
                        dispatched = dispatch_email_now(args.email, subj, body)
                        print(f"[AudioCodeListener] EMAIL DISPATCH RESULT: {json.dumps(dispatched)}", flush=True)
                    else:
                        dispatched = {"ok": False, "dry_run": True, "code": full_code}

                    save_state(digits, meta, args.email, args.length, args.auto_send, recent_transcripts, code_alerts, dispatched)
                    if args.stop_when_complete:
                        return

                save_state(digits, meta, args.email, args.length, args.auto_send, recent_transcripts, code_alerts, dispatched)

            if rec.poll() is not None:
                print("[AudioCodeListener] ffmpeg audio recorder stopped; restarting...", flush=True)
                time.sleep(1.0)
                rec = subprocess.Popen(ff_cmd)

            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[AudioCodeListener] Stopped by user.", flush=True)
    finally:
        if rec.poll() is None:
            rec.terminate()
            try:
                rec.wait(timeout=3)
            except Exception:
                rec.kill()
        asr.close()
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
