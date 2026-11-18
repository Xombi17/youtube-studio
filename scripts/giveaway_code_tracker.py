#!/usr/bin/env python3
"""
CreatorRadar Live Giveaway Code Tracker & Auto-Email Dispatcher
===============================================================
Tracks sequential digit-by-digit giveaway codes announced on a livestream by
fusing TWO real-time signals:
  1. Clipper Hinglish/English ASR transcripts (speech announcements)
  2. YouTube Live Chat unique-author consensus (troll/spam resistant)

Works both:
  - Hooked directly inside `orchestration/live_clipper_agent.py` (--track-code)
  - Standalone on live YouTube chat via `pytchat` (even when video capture is paused)

Once all N digits (default: 6) are confirmed, optionally dispatches an email
immediately via Gmail SMTP (using GMAIL_USER + GMAIL_APP_PASSWORD or
config/gmail_smtp.json).
"""

from __future__ import annotations

import argparse
import collections
import datetime
import json
import os
import re
import smtplib
import ssl
import sys
import threading
import time
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RENDERS_BUFFER_DIR = ROOT / "renders" / "live_buffer"
DEFAULT_STATE_FILE = RENDERS_BUFFER_DIR / "giveaway_code_state.json"
DEFAULT_SMTP_CONFIG = ROOT / "config" / "gmail_smtp.json"

# Hindi / Hinglish / English digit vocabulary
DIGIT_WORDS: dict[str, str] = {
    "0": "0", "zero": "0", "shunya": "0", "sunya": "0", "sifar": "0", "oh": "0",
    "1": "1", "one": "1", "ek": "1", "aik": "1",
    "2": "2", "two": "2", "do": "2", "to": "2",
    "3": "3", "three": "3", "teen": "3", "tin": "3",
    "4": "4", "four": "4", "char": "4", "chaar": "4",
    "5": "5", "five": "5", "panch": "5", "paanch": "5",
    "6": "6", "six": "6", "chhe": "6", "che": "6", "chhah": "6",
    "7": "7", "seven": "7", "saat": "7", "sat": "7",
    "8": "8", "eight": "8", "aath": "8", "ath": "8",
    "9": "9", "nine": "9", "nau": "9",
}

ORDINAL_WORDS: dict[str, int] = {
    "1st": 1, "first": 1, "pehla": 1, "pahla": 1, "pehle": 1, "1": 1,
    "2nd": 2, "second": 2, "doosra": 2, "dusra": 2, "2": 2,
    "3rd": 3, "third": 3, "teesra": 3, "tisra": 3, "3": 3,
    "4th": 4, "fourth": 4, "chautha": 4, "chotha": 4, "4": 4,
    "5th": 5, "fifth": 5, "paanchva": 5, "panchva": 5, "panchwa": 5, "paanchwa": 5, "5": 5,
    "6th": 6, "sixth": 6, "chhatha": 6, "chatha": 6, "last": 6, "aakhri": 6, "aakhiri": 6, "final": 6, "6": 6,
}

CODE_CONTEXT_RE = re.compile(
    r"\b(code|kod|digit|number|num|giveaway|mail|email|gmail|entry|entries|agla|next|last|final|fifth|sixth|paanchva|chhatha)\b",
    re.I,
)

QUESTION_OR_SPECULATION_RE = re.compile(
    r"(\?|kya|what|batao|bata\s*do|bolo|plz|please|doooo|de\s*do|guess|calculat|leak|maybe|shayad|lagta|ho\s*skta|sakta|fake|scam|try\s*krke|spam)",
    re.I,
)


def extract_youtube_video_id(url_or_id: str) -> str:
    s = url_or_id.strip()
    if re.fullmatch(r"[a-zA-Z0-9_-]{11}", s):
        return s
    m = re.search(r"(?:youtube\.com/watch\?.*?v=|youtu\.be/|youtube\.com/live/)([a-zA-Z0-9_-]{11})", s)
    if m:
        return m.group(1)
    raise ValueError(f"Could not extract YouTube video ID from: {url_or_id}")


def load_smtp_credentials(config_path: Path = DEFAULT_SMTP_CONFIG) -> dict[str, str]:
    """Load Gmail SMTP credentials from env vars first, then optional config/gmail_smtp.json."""
    user = os.environ.get("GMAIL_USER", "").strip()
    pw = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    from_name = os.environ.get("GMAIL_FROM_NAME", "").strip()
    extra_body = os.environ.get("GMAIL_EXTRA_BODY", "").strip()

    if (not user or not pw) and config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            user = user or str(data.get("gmail_user", "")).strip()
            pw = pw or str(data.get("gmail_app_password", "")).strip()
            from_name = from_name or str(data.get("from_name", "")).strip()
            extra_body = extra_body or str(data.get("extra_body", "")).strip()
        except Exception:
            pass

    return {
        "gmail_user": user,
        "gmail_app_password": pw.replace(" ", ""),
        "from_name": from_name,
        "extra_body": extra_body,
    }


def send_gmail_smtp(
    to_email: str,
    subject: str,
    body: str,
    config_path: Path = DEFAULT_SMTP_CONFIG,
) -> dict:
    """Send an email immediately via Gmail SMTP SSL (port 465)."""
    creds = load_smtp_credentials(config_path)
    user = creds["gmail_user"]
    pw = creds["gmail_app_password"]
    if not user or not pw:
        return {
            "ok": False,
            "error": (
                "Missing Gmail SMTP credentials. Set GMAIL_USER and GMAIL_APP_PASSWORD "
                f"env vars (16-char Google App Password) or create {config_path}."
            ),
        }

    msg = EmailMessage()
    msg["From"] = f"{creds['from_name']} <{user}>" if creds["from_name"] else user
    msg["To"] = to_email
    msg["Subject"] = subject
    full_body = body
    if creds["extra_body"] and creds["extra_body"] not in body:
        full_body = f"{body.rstrip()}\n\n{creds['extra_body']}\n"
    msg.set_content(full_body)

    last_err = ""
    for attempt in range(2):
        try:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx, timeout=15) as server:
                server.login(user, pw)
                server.send_message(msg)
            return {
                "ok": True,
                "from": user,
                "to": to_email,
                "subject": subject,
                "sent_at": datetime.datetime.now().isoformat(),
            }
        except Exception as exc:
            last_err = str(exc)
            if attempt == 0:
                time.sleep(0.8)

    return {"ok": False, "error": last_err}


class GiveawayCodeTracker:
    """
    Real-time digit-by-digit giveaway code tracker combining ASR speech events
    and YouTube Live Chat unique-author consensus.
    """

    def __init__(
        self,
        target_email: str = "code.mythpat@gmail.com",
        code_length: int = 6,
        seed_prefix: str = "",
        auto_send: bool = False,
        subject_template: str = "{code}",
        body_template: str = "{code}",
        state_file: Path = DEFAULT_STATE_FILE,
        smtp_config: Path = DEFAULT_SMTP_CONFIG,
        min_chat_consensus: int = 12,
        asr_boosted_consensus: int = 4,
        burst_consensus: int = 22,
        window_sec: float = 45.0,
        trust_asr_direct: bool = False,
    ):
        self.target_email = target_email.strip()
        self.code_length = max(1, int(code_length))
        self.auto_send = bool(auto_send)
        self.subject_template = subject_template
        self.body_template = body_template
        self.state_file = Path(state_file)
        self.smtp_config = Path(smtp_config)
        self.min_chat_consensus = max(2, int(min_chat_consensus))
        self.asr_boosted_consensus = max(2, int(asr_boosted_consensus))
        self.burst_consensus = max(5, int(burst_consensus))
        self.window_sec = float(window_sec)
        self.trust_asr_direct = bool(trust_asr_direct)

        self._lock = threading.Lock()
        self.digits: dict[int, dict] = {}
        self.completed_codes: list[dict] = []
        self.dispatched_codes: set[str] = set()
        self.asr_mentions: collections.deque[dict] = collections.deque(maxlen=40)
        self.last_asr_code_ts: float = 0.0
        self.asr_digit_hints: dict[int, tuple[str, float, str]] = {}  # slot -> (digit, ts, snippet)

        # Sliding vote buffers: candidate_key -> dict[author_lower, timestamp]
        self._pos_votes: dict[tuple[int, str], dict[str, float]] = collections.defaultdict(dict)
        self._prefix_votes: dict[str, dict[str, float]] = collections.defaultdict(dict)
        self._single_votes: dict[str, dict[str, float]] = collections.defaultdict(dict)
        self._chat_msg_count: int = 0
        self._last_persist_ts: float = 0.0

        self._load_existing_state()
        if seed_prefix:
            clean_seed = re.sub(r"\D", "", seed_prefix)[: self.code_length]
            for i, ch in enumerate(clean_seed, start=1):
                if i not in self.digits:
                    self.digits[i] = {
                        "digit": ch,
                        "source": "seed",
                        "confidence": "seeded",
                        "confirmed_at": datetime.datetime.now().isoformat(),
                        "evidence": f"Seeded prefix '{clean_seed}'",
                    }
        self._persist(force=True)

    def _load_existing_state(self):
        if not self.state_file.exists():
            return
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            for k, v in (data.get("digits") or {}).items():
                pos = int(k)
                if 1 <= pos <= self.code_length and isinstance(v, dict) and v.get("digit"):
                    self.digits[pos] = v
            self.completed_codes = list(data.get("completed_codes") or [])
            for item in self.completed_codes:
                if item.get("dispatched") and item.get("code"):
                    self.dispatched_codes.add(str(item["code"]))
            for m in (data.get("asr_mentions") or [])[-40:]:
                self.asr_mentions.append(m)
        except Exception:
            pass

    def current_prefix(self) -> str:
        """Contiguous confirmed digits starting from slot 1."""
        out = []
        for i in range(1, self.code_length + 1):
            if i in self.digits:
                out.append(self.digits[i]["digit"])
            else:
                break
        return "".join(out)

    def current_masked(self) -> str:
        return "".join(
            self.digits[i]["digit"] if i in self.digits else "_"
            for i in range(1, self.code_length + 1)
        )

    def next_missing_slot(self) -> int | None:
        for i in range(1, self.code_length + 1):
            if i not in self.digits:
                return i
        return None

    def is_complete(self) -> bool:
        return all(i in self.digits for i in range(1, self.code_length + 1))

    def _prune_votes(self, now: float):
        cutoff = now - self.window_sec
        burst_cutoff = now - 18.0
        for bucket in (self._pos_votes, self._prefix_votes):
            empty_keys = []
            for key, authors in bucket.items():
                stale = [a for a, ts in authors.items() if ts < cutoff]
                for a in stale:
                    del authors[a]
                if not authors:
                    empty_keys.append(key)
            for key in empty_keys:
                del bucket[key]

        empty_single = []
        for key, authors in self._single_votes.items():
            stale = [a for a, ts in authors.items() if ts < burst_cutoff]
            for a in stale:
                del authors[a]
            if not authors:
                empty_single.append(key)
        for key in empty_single:
            del self._single_votes[key]

    def _lock_digit(self, slot: int, digit: str, source: str, confidence: str, evidence: str) -> bool:
        if not (1 <= slot <= self.code_length) or digit not in "0123456789":
            return False
        if slot in self.digits:
            return False

        self.digits[slot] = {
            "digit": digit,
            "source": source,
            "confidence": confidence,
            "confirmed_at": datetime.datetime.now().isoformat(),
            "evidence": evidence,
        }
        masked = self.current_masked()
        print(
            f"\a\n[GiveawayTracker] >>> LOCKED DIGIT #{slot} = {digit} ({source}, {confidence}) | "
            f"CODE SO FAR: {masked} | Evidence: {evidence}\n",
            flush=True,
        )
        self._maybe_finalize_locked()
        self._persist(force=True)
        return True

    def _maybe_finalize_locked(self):
        if not self.is_complete():
            return
        full_code = "".join(self.digits[i]["digit"] for i in range(1, self.code_length + 1))
        already_logged = any(c.get("code") == full_code for c in self.completed_codes)
        entry = next((c for c in self.completed_codes if c.get("code") == full_code), None)
        if not already_logged:
            entry = {
                "code": full_code,
                "completed_at": datetime.datetime.now().isoformat(),
                "target_email": self.target_email,
                "digits": {str(k): v for k, v in sorted(self.digits.items())},
                "dispatched": False,
                "dispatch_result": None,
            }
            self.completed_codes.append(entry)

        print(
            f"\a\a\n"
            f"================================================================\n"
            f"  [GiveawayTracker] ALL {self.code_length} DIGITS CONFIRMED: {full_code}\n"
            f"  Target Email: {self.target_email}\n"
            f"================================================================\n",
            flush=True,
        )

        if self.auto_send and full_code not in self.dispatched_codes:
            self.dispatched_codes.add(full_code)
            threading.Thread(
                target=self._dispatch_worker,
                args=(full_code, entry),
                daemon=True,
            ).start()

    def _dispatch_worker(self, full_code: str, entry: dict):
        subj = self.subject_template.format(code=full_code)
        body = self.body_template.format(code=full_code)
        print(f"[GiveawayTracker] Dispatching email to {self.target_email} with code {full_code}...", flush=True)
        res = send_gmail_smtp(self.target_email, subj, body, config_path=self.smtp_config)
        with self._lock:
            entry["dispatched"] = bool(res.get("ok"))
            entry["dispatch_result"] = res
            if not res.get("ok"):
                self.dispatched_codes.discard(full_code)
                print(f"[GiveawayTracker] Email dispatch FAILED: {res.get('error')}", flush=True)
            else:
                print(
                    f"\a[GiveawayTracker] >>> EMAIL SENT to {self.target_email} "
                    f"(from {res.get('from')}) at {res.get('sent_at')}!",
                    flush=True,
                )
            self._persist(force=True)

    def on_transcript(self, text: str, timestamp: str | None = None):
        """Process a 10-second ASR transcript chunk from the live clipper."""
        if not text or not text.strip():
            return
        clean = text.strip()
        if not CODE_CONTEXT_RE.search(clean):
            return

        now = time.time()
        ts_str = timestamp or datetime.datetime.now().strftime("%H:%M:%S")
        with self._lock:
            self.last_asr_code_ts = now
            self.asr_mentions.append({"time": ts_str, "text": clean[:240]})
            print(f"[GiveawayTracker][ASR @ {ts_str}] {clean[:180]}", flush=True)

            # Parse explicit positional announcements like "5th digit is 8" or "paanchva number aath hai"
            low = re.sub(r"[^a-z0-9\s]", " ", clean.lower())
            tokens = low.split()

            # Check ordinal + digit proximity
            for idx, tok in enumerate(tokens):
                if tok in ORDINAL_WORDS and tok not in ("1", "2", "3", "4", "5", "6"):
                    slot = ORDINAL_WORDS[tok]
                    if slot > self.code_length or slot in self.digits:
                        continue
                    window_toks = tokens[idx + 1 : idx + 8]
                    if any(w in ("code", "kod", "digit", "number", "num", "hai", "is") for w in window_toks):
                        for w in window_toks:
                            if w in DIGIT_WORDS and w != tok:
                                digit = DIGIT_WORDS[w]
                                self.asr_digit_hints[slot] = (digit, now, clean[:140])
                                print(
                                    f"[GiveawayTracker][ASR-HINT] Candidate slot #{slot} = {digit} from: {clean[:120]!r}",
                                    flush=True,
                                )
                                if self.trust_asr_direct:
                                    self._lock_digit(slot, digit, "asr_direct", "asr_only", clean[:140])
                                break

            # Also check "next digit is X" / "agla digit X" / "code is X"
            next_slot = self.next_missing_slot()
            if next_slot is not None and next_slot not in self.asr_digit_hints:
                m = re.search(
                    r"\b(?:next|agla|agle|new|code|digit|number)\s+(?:digit|code|number|is|hai|ho\s+gaya)?\s*(?:is|hai)?\s*"
                    r"(0|1|2|3|4|5|6|7|8|9|zero|one|ek|two|do|three|teen|four|chaar|char|five|paanch|panch|six|chhe|che|seven|saat|sat|eight|aath|ath|nine|nau)\b",
                    low,
                )
                if m:
                    digit = DIGIT_WORDS.get(m.group(1), "")
                    if digit:
                        self.asr_digit_hints[next_slot] = (digit, now, clean[:140])
                        print(
                            f"[GiveawayTracker][ASR-HINT] Candidate next slot #{next_slot} = {digit} from: {clean[:120]!r}",
                            flush=True,
                        )
                        if self.trust_asr_direct:
                            self._lock_digit(next_slot, digit, "asr_direct", "asr_only", clean[:140])

            self._persist(force=True)

    def on_chat_message(self, author: str, msg: str):
        """Process a live YouTube chat message and check for consensus on new digits."""
        if not msg:
            return
        now = time.time()
        author_key = (author or "anon").strip().lower()
        raw = msg.strip()

        with self._lock:
            self._chat_msg_count += 1
            if self._chat_msg_count % 40 == 0:
                self._prune_votes(now)

            if self.is_complete():
                self._persist(force=False)
                return

            if QUESTION_OR_SPECULATION_RE.search(raw):
                return

            prefix = self.current_prefix()
            next_slot = self.next_missing_slot()
            if next_slot is None:
                return

            # 1) Prefix extension: e.g. prefix="7523", message contains "75238" or "752389"
            if len(prefix) >= 2:
                # Allow slight separators like spaces/dashes between digits: "7 5 2 3 8"
                compact_digits = re.findall(r"\b\d(?:\s*[- ]?\s*\d){" + str(len(prefix)) + r"," + str(self.code_length - 1) + r"}\b", raw)
                for match in compact_digits:
                    seq = re.sub(r"\D", "", match)
                    if seq.startswith(prefix) and len(prefix) < len(seq) <= self.code_length:
                        self._prefix_votes[seq][author_key] = now

            # 2) Explicit positional chat report: "5th digit is 8", "5th code 8", "5th = 8", "last digit 9"
            low = raw.lower()
            pos_match = re.search(
                r"\b(1st|first|2nd|second|3rd|third|4th|fourth|5th|fifth|6th|sixth|last|final)\s*"
                r"(?:digit|code|number|num|no)?\s*(?:is|hai|=|:|-)?\s*(\d)\b",
                low,
            )
            if pos_match:
                slot = ORDINAL_WORDS.get(pos_match.group(1), 0)
                dig = pos_match.group(2)
                if slot == next_slot or (1 <= slot <= self.code_length and slot not in self.digits):
                    self._pos_votes[(slot, dig)][author_key] = now

            # 3) Single-digit burst: message is just "8" or "code 8" or "digit 8"
            single_match = re.fullmatch(
                r"(?:(?:code|digit|no|number|hai|is)\s*(?:is|hai|=|:|-)?\s*)?(\d)(?:\s*(?:hai|is|bro|bhai|confirm|confirmed))?!*",
                low,
            )
            if single_match:
                self._single_votes[single_match.group(1)][author_key] = now

            self._evaluate_consensus_locked(now)
            self._persist(force=False)

    def _evaluate_consensus_locked(self, now: float):
        self._prune_votes(now)
        prefix = self.current_prefix()
        next_slot = self.next_missing_slot()
        if next_slot is None:
            return

        asr_hint = self.asr_digit_hints.get(next_slot)
        has_recent_asr_hint = bool(asr_hint and (now - asr_hint[1]) <= 90.0)
        recent_asr_code = (now - self.last_asr_code_ts) <= 35.0

        # A) Evaluate prefix-extension votes for next digit (and full code)
        if len(prefix) >= 2 and self._prefix_votes:
            # Count unique authors per next-digit extension (merging 5-digit and 6-digit prefixes on next_slot)
            next_digit_authors: dict[str, set[str]] = collections.defaultdict(set)
            for seq, authors in self._prefix_votes.items():
                if seq.startswith(prefix) and len(seq) > len(prefix):
                    d_next = seq[len(prefix)]
                    next_digit_authors[d_next].update(authors.keys())

            ranked = sorted(
                ((d, len(a)) for d, a in next_digit_authors.items()),
                key=lambda x: x[1],
                reverse=True,
            )
            if ranked:
                top_d, top_n = ranked[0]
                second_n = ranked[1][1] if len(ranked) > 1 else 0
                needed = self.asr_boosted_consensus if (has_recent_asr_hint and asr_hint[0] == top_d) else self.min_chat_consensus
                share = top_n / max(1, top_n + second_n)
                if top_n >= needed and share >= 0.68:
                    src = "asr+chat_prefix" if (has_recent_asr_hint and asr_hint[0] == top_d) else "chat_prefix_consensus"
                    self._lock_digit(
                        next_slot,
                        top_d,
                        source=src,
                        confidence=f"{top_n} unique chatters ({share:.0%} dominance)",
                        evidence=f"Prefix {prefix}{top_d} confirmed by {top_n} unique authors (runner-up: {second_n})",
                    )
                    # Check if a 6th digit ALSO already has full-code consensus
                    if not self.is_complete():
                        self._evaluate_consensus_locked(now)
                    return

        # B) Evaluate explicit positional votes for any missing slot
        slot_tallies: dict[int, list[tuple[str, int]]] = collections.defaultdict(list)
        for (slot, dig), authors in self._pos_votes.items():
            if slot not in self.digits:
                slot_tallies[slot].append((dig, len(authors)))

        for slot, items in slot_tallies.items():
            items.sort(key=lambda x: x[1], reverse=True)
            top_d, top_n = items[0]
            second_n = items[1][1] if len(items) > 1 else 0
            slot_asr = self.asr_digit_hints.get(slot)
            slot_asr_ok = bool(slot_asr and (now - slot_asr[1]) <= 90.0 and slot_asr[0] == top_d)
            needed = self.asr_boosted_consensus if slot_asr_ok else self.min_chat_consensus
            share = top_n / max(1, top_n + second_n)
            if top_n >= needed and share >= 0.68:
                src = "asr+chat_positional" if slot_asr_ok else "chat_positional_consensus"
                self._lock_digit(
                    slot,
                    top_d,
                    source=src,
                    confidence=f"{top_n} unique chatters ({share:.0%} dominance)",
                    evidence=f"Positional #{slot}={top_d} reported by {top_n} unique authors (runner-up: {second_n})",
                )
                return

        # C) Evaluate sudden single-digit chat burst for next_slot
        if self._single_votes:
            ranked_s = sorted(
                ((d, len(a)) for d, a in self._single_votes.items()),
                key=lambda x: x[1],
                reverse=True,
            )
            top_d, top_n = ranked_s[0]
            second_n = ranked_s[1][1] if len(ranked_s) > 1 else 0
            share = top_n / max(1, top_n + second_n)
            needed = self.asr_boosted_consensus + 2 if (has_recent_asr_hint and asr_hint[0] == top_d) else (
                max(10, self.min_chat_consensus) if recent_asr_code else self.burst_consensus
            )
            if top_n >= needed and share >= 0.72:
                src = "asr+chat_burst" if recent_asr_code else "chat_burst_consensus"
                self._lock_digit(
                    next_slot,
                    top_d,
                    source=src,
                    confidence=f"{top_n} unique chatters in 18s ({share:.0%} dominance)",
                    evidence=f"Single-digit burst '{top_d}' by {top_n} unique authors (runner-up: {second_n})",
                )

    def get_snapshot(self) -> dict:
        now = time.time()
        self._prune_votes(now)
        top_prefix = sorted(
            ((seq, len(a)) for seq, a in self._prefix_votes.items()),
            key=lambda x: x[1],
            reverse=True,
        )[:6]
        top_pos = sorted(
            ((f"#{slot}={d}", len(a)) for (slot, d), a in self._pos_votes.items()),
            key=lambda x: x[1],
            reverse=True,
        )[:6]
        top_single = sorted(
            ((d, len(a)) for d, a in self._single_votes.items()),
            key=lambda x: x[1],
            reverse=True,
        )[:5]
        creds = load_smtp_credentials(self.smtp_config)
        return {
            "updated_at": datetime.datetime.now().isoformat(),
            "target_email": self.target_email,
            "code_length": self.code_length,
            "current_code": self.current_masked(),
            "confirmed_prefix": self.current_prefix(),
            "is_complete": self.is_complete(),
            "auto_send_enabled": self.auto_send,
            "smtp_configured": bool(creds["gmail_user"] and creds["gmail_app_password"]),
            "chat_messages_seen": self._chat_msg_count,
            "digits": {str(k): v for k, v in sorted(self.digits.items())},
            "completed_codes": self.completed_codes,
            "live_candidates": {
                "prefix_votes": [{"seq": s, "unique_authors": n} for s, n in top_prefix],
                "positional_votes": [{"slot_digit": s, "unique_authors": n} for s, n in top_pos],
                "single_digit_burst": [{"digit": d, "unique_authors": n} for d, n in top_single],
            },
            "asr_mentions": list(self.asr_mentions)[-15:],
        }

    def _persist(self, force: bool = False):
        now = time.time()
        if not force and (now - self._last_persist_ts) < 3.0:
            return
        self._last_persist_ts = now
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_file.with_suffix(".tmp.json")
            tmp.write_text(json.dumps(self.get_snapshot(), indent=2), encoding="utf-8")
            tmp.replace(self.state_file)
        except Exception:
            pass


def run_standalone_chat_tracker(args: argparse.Namespace):
    import pytchat

    vid = extract_youtube_video_id(args.url)
    tracker = GiveawayCodeTracker(
        target_email=args.email,
        code_length=args.length,
        seed_prefix=args.seed,
        auto_send=args.auto_send,
        subject_template=args.subject,
        body_template=args.body,
        state_file=Path(args.state_file),
        min_chat_consensus=args.min_consensus,
        burst_consensus=args.burst_consensus,
    )

    creds = load_smtp_credentials()
    smtp_status = f"READY ({creds['gmail_user']})" if (creds["gmail_user"] and creds["gmail_app_password"]) else "NOT CONFIGURED (dry-run)"
    print(
        f"[GiveawayTracker] Watching YouTube Live Chat for video={vid}\n"
        f"  Current code : {tracker.current_masked()} (length={args.length})\n"
        f"  Target email : {args.email} | Auto-send: {'ON' if args.auto_send else 'OFF'} | SMTP: {smtp_status}\n"
        f"  State file   : {args.state_file}\n",
        flush=True,
    )

    last_status_ts = 0.0
    try:
        while True:
            chat = None
            try:
                chat = pytchat.create(video_id=vid, interruptable=False)
                while chat.is_alive():
                    for item in chat.get().sync_items():
                        author = getattr(item.author, "name", "yt_user") or "yt_user"
                        msg = getattr(item, "message", "") or ""
                        tracker.on_chat_message(author, msg)

                    now = time.time()
                    if now - last_status_ts >= 10.0:
                        last_status_ts = now
                        snap = tracker.get_snapshot()
                        p_top = snap["live_candidates"]["prefix_votes"][:3]
                        pos_top = snap["live_candidates"]["positional_votes"][:3]
                        s_top = snap["live_candidates"]["single_digit_burst"][:3]
                        print(
                            f"[{datetime.datetime.now().strftime('%H:%M:%S')}] "
                            f"code={snap['current_code']} | msgs={snap['chat_messages_seen']} | "
                            f"prefix={p_top} | pos={pos_top} | single={s_top}",
                            flush=True,
                        )

                    if args.stop_when_complete and tracker.is_complete():
                        time.sleep(2.0)  # let dispatch thread finish
                        return
                    time.sleep(0.4)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                print(f"[GiveawayTracker] Chat reconnect after error: {exc}", flush=True)
                time.sleep(3.0)
            finally:
                if chat:
                    try:
                        chat.terminate()
                    except Exception:
                        pass
    except KeyboardInterrupt:
        print("\n[GiveawayTracker] Stopped by user.", flush=True)


def main():
    parser = argparse.ArgumentParser(
        description="Live YouTube Giveaway Code Tracker & Auto-Email Dispatcher"
    )
    parser.add_argument("--url", help="YouTube live stream URL or 11-char video ID")
    parser.add_argument("--seed", default="", help="Already known leading digits (e.g. '7523')")
    parser.add_argument("--length", type=int, default=6, help="Total digits in code (default: 6)")
    parser.add_argument("--email", default="code.mythpat@gmail.com", help="Recipient giveaway email")
    parser.add_argument("--auto-send", action="store_true", help="Automatically dispatch Gmail SMTP email once all digits lock")
    parser.add_argument("--subject", default="{code}", help="Email subject template (supports {code})")
    parser.add_argument("--body", default="{code}", help="Email body template (supports {code})")
    parser.add_argument("--min-consensus", type=int, default=12, help="Min unique chatters to lock a digit (default: 12)")
    parser.add_argument("--burst-consensus", type=int, default=22, help="Min unique chatters for unprompted single-digit burst (default: 22)")
    parser.add_argument("--state-file", default=str(DEFAULT_STATE_FILE), help="JSON state output path")
    parser.add_argument("--stop-when-complete", action="store_true", help="Exit after full code is confirmed & dispatched")
    parser.add_argument("--test-smtp", action="store_true", help="Send a self-test email to your own GMAIL_USER to verify SMTP setup")
    args = parser.parse_args()

    if args.test_smtp:
        creds = load_smtp_credentials()
        if not creds["gmail_user"]:
            print("ERROR: GMAIL_USER / GMAIL_APP_PASSWORD not configured.", file=sys.stderr)
            sys.exit(1)
        res = send_gmail_smtp(
            creds["gmail_user"],
            "CreatorRadar Giveaway Tracker — SMTP Test OK",
            "Your Gmail SMTP auto-dispatch is working and ready for instant code delivery.",
        )
        print(json.dumps(res, indent=2))
        sys.exit(0 if res.get("ok") else 1)

    if not args.url:
        parser.error("--url is required unless using --test-smtp")

    run_standalone_chat_tracker(args)


if __name__ == "__main__":
    main()
