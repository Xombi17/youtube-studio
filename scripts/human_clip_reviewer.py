#!/usr/bin/env python3
"""
CreatorRadar / ClipSurge — Simulated Normal-Human Shorts Reviewer Agent

Runs on a free model served by APInex (OpenAI-compatible, `APINEX_API_KEY`) — default
`free/gemini-3.8-flash`, with `free/qwen-3.8-max` / `free/kimi-k3` fallbacks — to act like a
brutally honest, normal 21-year-old YouTube Shorts viewer scrolling at night. Set
`APINEX_MODEL` to pick a different free model. When no APInex key is configured it falls back
to the original Groq models (`openai/gpt-oss-120b`, `qwen/qwen3.8-27b`) under the shared
Groq free-tier budget guard.

Runs automatically on every A-TIER or S-TIER clip as soon as it is exported (or when manually
requested on a specific clip in the UI), caches permanently in `<clip_dir>/human_review.json`,
and acts as a strict quality gate before any A/S-tier clip is dispatched for YouTube upload.
This is a quality filter, not a substitute for the Rule 4 human sign-off.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

try:
    from scripts.groq_clip_brain import (
        _acquire_groq_budget,
        _get_groq_client,
        _load_dotenv_key,
        _strip_think_and_extract_json,
        is_groq_configured,
        record_groq_calls_saved,
    )
except ImportError:
    from groq_clip_brain import (
        _acquire_groq_budget,
        _get_groq_client,
        _load_dotenv_key,
        _strip_think_and_extract_json,
        is_groq_configured,
        record_groq_calls_saved,
    )

HUMAN_REVIEWER_MODELS = ("openai/gpt-oss-120b", "qwen/qwen3.8-27b")

# APInex — one OpenAI-compatible endpoint, free-tier models. Get a key at
# https://apinex.bond/developers and set APINEX_API_KEY (env or .env).
APINEX_BASE_URL = (
    os.environ.get("APINEX_BASE_URL") or _load_dotenv_key("APINEX_BASE_URL") or "https://api.apinex.bond/v1"
).rstrip("/")
APINEX_MODEL = (
    os.environ.get("APINEX_MODEL") or _load_dotenv_key("APINEX_MODEL") or "free/gemini-3.8-flash"
)
APINEX_FALLBACK_MODELS = ("free/qwen-3.8-max", "free/kimi-k3")


def is_apinex_configured() -> bool:
    return bool(_load_dotenv_key("APINEX_API_KEY"))


def _get_apinex_client():
    key = _load_dotenv_key("APINEX_API_KEY")
    if not key:
        return None
    try:
        from openai import OpenAI
    except ImportError:
        return None
    return OpenAI(base_url=APINEX_BASE_URL, api_key=key, timeout=45.0, max_retries=1)

# Every clip in these tiers is automatically sent to the human reviewer on export.
AUTO_REVIEW_TIERS = ("A-TIER", "S-TIER")


def read_cached_human_review(clip_dir: Path) -> dict[str, Any] | None:
    p = clip_dir / "human_review.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("verdict") in ("POST", "MAYBE", "SKIP"):
            return data
    except Exception:
        pass
    return None


def clip_tier_and_score(clip_dir: Path) -> tuple[str, float]:
    """Read the authoritative tier/score from moment.json (folder names can lie)."""
    p = Path(clip_dir) / "moment.json"
    if not p.exists():
        return "B-TIER", 0.0
    try:
        fus = json.loads(p.read_text(encoding="utf-8")).get("fusion") or {}
        return str(fus.get("tier") or "B-TIER").upper(), float(fus.get("total_score") or 0.0)
    except Exception:
        return "B-TIER", 0.0


def needs_human_review(clip_dir: Path) -> bool:
    """True when an A/S-tier clip has not been through the human reviewer yet."""
    clip_dir = Path(clip_dir)
    if read_cached_human_review(clip_dir) is not None:
        return False
    p = clip_dir / "moment.json"
    if not p.exists():
        return False
    try:
        mj = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return False
    if mj.get("human_review"):
        return False
    return str((mj.get("fusion") or {}).get("tier") or "B-TIER").upper() in AUTO_REVIEW_TIERS


def _probe_clip_tech(clip_dir: Path) -> dict[str, Any]:
    mp4s = sorted(clip_dir.glob("*.mp4"))
    if not mp4s:
        return {"ok": False, "duration": 0.0, "v_start": 0.0, "issues": ["missing_mp4"]}
    mp4 = mp4s[0]
    issues: list[str] = []
    dur = 0.0
    v_start = 0.0
    try:
        pr = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,start_time", "-of", "json", str(mp4)],
            capture_output=True, text=True, timeout=6,
        )
        if pr.returncode == 0 and pr.stdout.strip():
            d = json.loads(pr.stdout)
            dur = round(float((d.get("format") or {}).get("duration") or 0.0), 2)
            vs = next((s for s in (d.get("streams") or []) if s.get("codec_type") == "video"), {})
            v_start = round(float(vs.get("start_time") or 0.0), 3)
    except Exception:
        pass

    if dur < 8.0:
        issues.append(f"too_short ({dur}s)")
    elif dur > 34.0:
        issues.append(f"too_long_for_short ({dur}s)")
    if v_start > 0.15:
        issues.append(f"frozen_video_start ({v_start}s)")
    return {"ok": len(issues) == 0, "duration": dur, "v_start": v_start, "issues": issues}


def review_clip_as_human(clip_dir: Path, force: bool = False) -> dict[str, Any] | None:
    """
    Evaluate a single clip as a brutally honest normal YouTube Shorts viewer.
    Returns dict with verdict ('POST' | 'MAYBE' | 'SKIP'), human_score (0-100),
    sub-scores (swipe_stop, clarity, entertainment, share_loop), gut_reaction, and edit_tip.
    """
    if not clip_dir.is_dir():
        return None
    if not force:
        cached = read_cached_human_review(clip_dir)
        if cached:
            record_groq_calls_saved(1)
            return cached

    tech = _probe_clip_tech(clip_dir)
    mj_path = clip_dir / "moment.json"
    tj_path = clip_dir / "transcript.json"
    gr_path = clip_dir / "groq_review.json"
    mj = json.loads(mj_path.read_text(encoding="utf-8")) if mj_path.exists() else {}
    tj = json.loads(tj_path.read_text(encoding="utf-8")) if tj_path.exists() else {}
    gr = json.loads(gr_path.read_text(encoding="utf-8")) if gr_path.exists() else {}

    tx = re.sub(r"\s+", " ", str(tj.get("text") or mj.get("transcript") or "")).strip()
    words = tj.get("words") or []
    word_count = len(words) if words else len(tx.split())
    fus = mj.get("fusion") or {}
    chat = mj.get("chat") or {}
    dono = chat.get("matched_dono") if chat.get("dono_read_verified") else None
    channel = clip_dir.parent.name
    draft_title = (gr.get("titles") or [""])[0]

    # Fast local pre-reject (0 API calls!) if clip is broken or completely empty speech
    if not tech["ok"] and any("frozen" in x or "missing" in x for x in tech["issues"]):
        out = {
            "verdict": "SKIP",
            "human_score": 25,
            "swipe_stop": 20,
            "clarity": 30,
            "entertainment": 30,
            "share_loop": 20,
            "gut_reaction": f"Skipped automatically: technical issue detected ({', '.join(tech['issues'])}).",
            "edit_tip": "Fix video start alignment before posting.",
            "would_post": False,
            "tech": tech,
            "model": "local-tech-gate",
            "reviewed_at": round(time.time(), 1),
        }
        (clip_dir / "human_review.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
        return out

    if word_count < 4 and float((mj.get("audio") or {}).get("score") or 0.0) < 16.0:
        out = {
            "verdict": "SKIP",
            "human_score": 32,
            "swipe_stop": 28,
            "clarity": 25,
            "entertainment": 35,
            "share_loop": 20,
            "gut_reaction": "Almost no speech or clear hook — a normal viewer would swipe past immediately.",
            "edit_tip": "Drop silent clips without a clear punchline.",
            "would_post": False,
            "tech": tech,
            "model": "local-prefilter",
            "reviewed_at": round(time.time(), 1),
        }
        (clip_dir / "human_review.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
        return out

    # Preferred: APInex free model. Groq stays as a fallback so an unset key never
    # silently disables the reviewer.
    use_apinex = is_apinex_configured()
    if use_apinex:
        client = _get_apinex_client()
        candidate_models = (APINEX_MODEL,) + tuple(
            m for m in APINEX_FALLBACK_MODELS if m != APINEX_MODEL
        )
    else:
        if not is_groq_configured() or not _acquire_groq_budget("llm"):
            return None
        client = _get_groq_client()
        candidate_models = HUMAN_REVIEWER_MODELS
    if client is None:
        return None

    first_5_words = " ".join(tx.split()[:10])
    last_5_words = " ".join(tx.split()[-10:])
    sys_p = (
        "You are NOT an AI assistant. You are a brutally honest, normal 21-year-old YouTube Shorts viewer "
        "scrolling your phone at 11 PM with a short attention span.\n"
        "You swipe away from 80% of gaming clips in under 2 seconds unless they genuinely hook you.\n"
        "Be STRICT and REALISTIC:\n"
        "- Say 'POST' ONLY if you would genuinely stop scrolling, watch till the end, and feel entertained, amused, shocked, or moved (human_score >= 82).\n"
        "- Say 'MAYBE' if it's decent but slightly flat or needs a tighter trim (human_score 68-81).\n"
        "- Say 'SKIP' if it's confusing without stream context, boring filler, rambling, random screaming with no payoff, or weak captions (human_score < 68).\n"
        "Return STRICT JSON ONLY."
    )
    dono_line = f"{dono.get('author')}: {dono.get('msg')}" if dono else "None"
    user_p = (
        f"Clip from channel: {channel}\n"
        f"Duration: {tech['duration']}s | Draft title: {draft_title or '(none)'}\n"
        f"Clipper score: {fus.get('total_score')}/100 ({fus.get('tier')}) | Label: {fus.get('archetype')}\n"
        f"Chat exploded: {bool(chat.get('is_explosion'))} | Weird/Glitch chat: {bool(chat.get('is_weird_spike'))}\n"
        f"Verified donation read: {dono_line}\n"
        f"Opening words (0-3s): \"{first_5_words}\"\n"
        f"Ending words (punchline): \"{last_5_words}\"\n"
        f"Full spoken transcript ({word_count} words): \"{tx[:850]}\"\n\n"
        "Evaluate as a normal human scroller and return JSON with exact keys:\n"
        '{"verdict": "POST" | "MAYBE" | "SKIP", '
        '"human_score": 0-100, '
        '"swipe_stop": 0-100, '
        '"clarity": 0-100, '
        '"entertainment": 0-100, '
        '"share_loop": 0-100, '
        '"gut_reaction": "1 blunt, natural human sentence explaining why you would watch or swipe away", '
        '"edit_tip": "1 short concrete suggestion if trim/title could be stronger, or \'Ready to post as-is\'"}'
    )

    parsed = None
    used_model = candidate_models[0]
    for model_id in candidate_models:
        try:
            kwargs: dict[str, Any] = {
                "model": model_id,
                "messages": [
                    {"role": "system", "content": sys_p},
                    {"role": "user", "content": user_p},
                ],
                "temperature": 0.35,
                "top_p": 0.95,
                "stream": False,
            }
            # APInex documents the OpenAI `max_tokens` alias; Groq uses max_completion_tokens.
            if use_apinex:
                kwargs["max_tokens"] = 380
            else:
                kwargs["max_completion_tokens"] = 380
            if (not use_apinex) and "qwen" in model_id.lower():
                kwargs["reasoning_effort"] = "none"
            try:
                comp = client.chat.completions.create(**kwargs)
            except Exception as e:
                if "reasoning_effort" in str(e).lower():
                    kwargs.pop("reasoning_effort", None)
                    comp = client.chat.completions.create(**kwargs)
                else:
                    raise
            raw = (comp.choices[0].message.content or "").strip() if comp.choices else ""
            parsed = _strip_think_and_extract_json(raw)
            if isinstance(parsed, dict) and parsed.get("verdict"):
                used_model = model_id
                break
        except Exception:
            continue

    if not isinstance(parsed, dict):
        return None

    h_score = max(0, min(100, int(parsed.get("human_score") or 50)))
    verdict = str(parsed.get("verdict") or "").strip().upper()
    if verdict not in ("POST", "MAYBE", "SKIP"):
        verdict = "POST" if h_score >= 82 else ("MAYBE" if h_score >= 68 else "SKIP")
    # Enforce strict consistency: POST requires human_score >= 80
    if verdict == "POST" and h_score < 80:
        verdict = "MAYBE"

    out = {
        "verdict": verdict,
        "human_score": h_score,
        "swipe_stop": max(0, min(100, int(parsed.get("swipe_stop") or h_score))),
        "clarity": max(0, min(100, int(parsed.get("clarity") or h_score))),
        "entertainment": max(0, min(100, int(parsed.get("entertainment") or h_score))),
        "share_loop": max(0, min(100, int(parsed.get("share_loop") or h_score))),
        "gut_reaction": str(parsed.get("gut_reaction") or "").strip()[:220],
        "edit_tip": str(parsed.get("edit_tip") or "").strip()[:180],
        "would_post": verdict == "POST",
        "tech": tech,
        "model": used_model,
        "reviewed_at": round(time.time(), 1),
    }
    (clip_dir / "human_review.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    # Sync into moment.json so dashboard cards display it immediately
    if mj_path.exists():
        try:
            mj["human_review"] = out
            mj_path.write_text(json.dumps(mj, indent=2), encoding="utf-8")
        except Exception:
            pass
    return out


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        res = review_clip_as_human(Path(sys.argv[1]), force="--force" in sys.argv)
        print(json.dumps(res, indent=2))
    else:
        print("Usage: python scripts/human_clip_reviewer.py <clip_dir> [--force]")
