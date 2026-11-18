#!/usr/bin/env python3
"""
CreatorRadar / ClipSurge — Free-Tier Optimized Groq Cloud AI Brain (Zero Local VRAM)

Uses `qwen/qwen3.8-27b` + `whisper-large-v3-turbo` with strict Free-Tier protection:
  1. Soft Rate-Limit Guard (`config/groq-usage-budget.json`): caps RPM (18/min) & RPD (850/day)
     so we NEVER exhaust Groq free-tier limits or trigger 429 storms.
  2. Multi-Clip Batching (`groq_batch_review_clips`): packs 2-3 clips into ONE single Groq call
     (judge virality against Viral Style Blueprint v2 + S-Tier >=90 + 3 viral titles + description + tags),
     cutting LLM API requests by ~80%!
  3. Persistent Per-Clip Disk Cache (`<clip_dir>/groq_review.json`): reopening the Upload Modal
     uses cached Groq metadata with ZERO extra API calls.
  4. Wispr Flow-style contextual caption review + Groq Whisper Large v3 Turbo word-level ASR.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

STUDIO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = STUDIO_ROOT / "config"
BUDGET_PATH = CONFIG_DIR / "groq-usage-budget.json"
BLUEPRINT_PATH = CONFIG_DIR / "viral-style-bible.json"
DEFAULT_GROQ_MODEL = os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b")
FALLBACK_GROQ_MODELS = ("qwen/qwen3-32b", "llama-3.3-70b-versatile")

# Naga AI fallback (imported lazily to avoid circular deps at module load)
def _try_import_naga():
    try:
        from scripts.naga_fallback import polish_caption_with_naga, call_naga_chat, _acquire_naga_budget, _load_naga_key
        return polish_caption_with_naga, call_naga_chat, _acquire_naga_budget, _load_naga_key
    except ImportError:
        try:
            import sys as _sys
            _sys.path.insert(0, str(Path(__file__).resolve().parent))
            from naga_fallback import polish_caption_with_naga, call_naga_chat, _acquire_naga_budget, _load_naga_key
            return polish_caption_with_naga, call_naga_chat, _acquire_naga_budget, _load_naga_key
        except ImportError:
            return None, None, None, None

_BUDGET_LOCK = threading.Lock()

_PROFANITY_RE = re.compile(
    r"\b(?:f+u+c+k\w*|s+h+i+t\w*|b+i+t+c+h\w*|a+s+s+h+o+l+e\w*|m+o+t+h+e+r+f\w*|c+u+n+t\w*|d+i+c+k\w*|p+u+s+s+y\w*|n+i+g+g\w*|f+a+g+\w*)\b",
    flags=re.I,
)


def _load_blueprint_limits() -> dict[str, Any]:
    try:
        if BLUEPRINT_PATH.exists():
            bp = json.loads(BLUEPRINT_PATH.read_text(encoding="utf-8"))
            return bp.get("groq_free_tier") or {}
    except Exception:
        pass
    return {"max_rpm_soft": 18, "max_rpd_soft": 850, "batch_size": 3, "whisper_min_score": 65.0}


def _load_tier_thresholds() -> tuple[float, float]:
    try:
        if BLUEPRINT_PATH.exists():
            t = (json.loads(BLUEPRINT_PATH.read_text(encoding="utf-8")).get("tiers") or {})
            return float(t.get("s_tier_min", 90.0)), float(t.get("a_tier_min", 72.0))
    except Exception:
        pass
    return 90.0, 72.0


def _load_dotenv_key(key_name: str = "GROQ_API_KEY") -> str:
    val = (os.environ.get(key_name) or "").strip()
    if val:
        return val
    for env_file in (STUDIO_ROOT / ".env", STUDIO_ROOT / ".env.local"):
        if not env_file.exists():
            continue
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == key_name:
                    cleaned = v.strip().strip('"').strip("'")
                    if cleaned:
                        return cleaned
        except Exception:
            continue
    return ""


def is_groq_configured() -> bool:
    return bool(_load_dotenv_key("GROQ_API_KEY"))


def _today_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def _load_budget_unlocked() -> dict[str, Any]:
    today = _today_utc()
    if BUDGET_PATH.exists():
        try:
            d = json.loads(BUDGET_PATH.read_text(encoding="utf-8"))
            if isinstance(d, dict) and d.get("day") == today:
                d.setdefault("recent_ts", [])
                d.setdefault("llm_calls_today", 0)
                d.setdefault("whisper_calls_today", 0)
                d.setdefault("whisper_sec_today", 0.0)
                d.setdefault("calls_saved", 0)
                return d
        except Exception:
            pass
    return {
        "day": today,
        "recent_ts": [],
        "llm_calls_today": 0,
        "whisper_calls_today": 0,
        "whisper_sec_today": 0.0,
        "calls_saved": 0,
    }


def _save_budget_unlocked(d: dict[str, Any]):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = BUDGET_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=2), encoding="utf-8")
    tmp.replace(BUDGET_PATH)


def _acquire_groq_budget(kind: str = "llm", audio_sec: float = 0.0) -> bool:
    """Enforce soft free-tier RPM/RPD guard before firing any Groq HTTP request."""
    lim = _load_blueprint_limits()
    max_rpm = int(lim.get("max_rpm_soft", 18))
    max_rpd = int(lim.get("max_rpd_soft", 850))
    now = time.time()
    with _BUDGET_LOCK:
        d = _load_budget_unlocked()
        recent = [ts for ts in d.get("recent_ts", []) if now - float(ts) < 60.0]
        total_today = int(d.get("llm_calls_today", 0)) + int(d.get("whisper_calls_today", 0))
        if len(recent) >= max_rpm or total_today >= max_rpd:
            return False
        recent.append(round(now, 2))
        d["recent_ts"] = recent
        if kind == "whisper":
            d["whisper_calls_today"] = int(d.get("whisper_calls_today", 0)) + 1
            d["whisper_sec_today"] = round(float(d.get("whisper_sec_today", 0.0)) + max(0.0, audio_sec), 1)
        else:
            d["llm_calls_today"] = int(d.get("llm_calls_today", 0)) + 1
        _save_budget_unlocked(d)
        return True


def record_groq_calls_saved(count: int = 1):
    if count <= 0:
        return
    with _BUDGET_LOCK:
        d = _load_budget_unlocked()
        d["calls_saved"] = int(d.get("calls_saved", 0)) + int(count)
        _save_budget_unlocked(d)


def get_groq_usage_summary() -> dict[str, Any]:
    lim = _load_blueprint_limits()
    now = time.time()
    with _BUDGET_LOCK:
        d = _load_budget_unlocked()
        rpm = len([ts for ts in d.get("recent_ts", []) if now - float(ts) < 60.0])
        return {
            "configured": is_groq_configured(),
            "model": DEFAULT_GROQ_MODEL,
            "day": d["day"],
            "rpm_used": rpm,
            "rpm_soft_cap": int(lim.get("max_rpm_soft", 18)),
            "llm_calls_today": int(d.get("llm_calls_today", 0)),
            "whisper_calls_today": int(d.get("whisper_calls_today", 0)),
            "whisper_min_today": round(float(d.get("whisper_sec_today", 0.0)) / 60.0, 1),
            "rpd_soft_cap": int(lim.get("max_rpd_soft", 850)),
            "calls_saved": int(d.get("calls_saved", 0)),
            "batch_size": int(lim.get("batch_size", 3)),
        }


def _get_groq_client():
    api_key = _load_dotenv_key("GROQ_API_KEY")
    if not api_key:
        return None
    try:
        from groq import Groq
        return Groq(api_key=api_key, timeout=14.0)
    except Exception:
        return None


def is_naga_configured() -> bool:
    """Check whether a Naga API key is available."""
    _, _, _, _load_naga_key = _try_import_naga()
    if _load_naga_key is None:
        return False
    return bool(_load_naga_key())


def fallback_polish_caption(raw_caption: str, tone: str = "engaging") -> str | None:
    """
    Naga AI fallback for caption polishing.
    Called automatically when Groq quota is exhausted.
    Strictly uses Naga free-tier models only.
    Returns polished caption string, or None if Naga is unavailable / rate-limited.
    """
    _polish_fn, _, _acquire_fn, _ = _try_import_naga()
    if _polish_fn is None or _acquire_fn is None:
        return None
    try:
        return _polish_fn(raw_caption, tone=tone)
    except RuntimeError as e:
        # Naga RPM limit or key missing
        print(f"[Naga fallback] skipped: {e}")
        return None
    except Exception as e:
        print(f"[Naga fallback] error: {e}")
        return None


def get_naga_usage_summary() -> dict:
    """Return Naga free-tier usage stats for the dashboard."""
    try:
        from pathlib import Path as _Path
        import json as _json
        budget_path = Path(__file__).resolve().parent.parent / "config" / "naga-usage-budget.json"
        if budget_path.exists():
            d = _json.loads(budget_path.read_text(encoding="utf-8"))
            return {
                "configured": is_naga_configured(),
                "day": d.get("day", ""),
                "calls_today": d.get("calls_today", 0),
                "rpm_limit": 10,
                "rpd_limit": 100,
            }
    except Exception:
        pass
    return {"configured": is_naga_configured(), "calls_today": 0, "rpm_limit": 10, "rpd_limit": 100}


def _strip_think_and_extract_json(raw_text: str) -> Any:
    cleaned = re.sub(r"<think>.*?</think>", "", raw_text or "", flags=re.S | re.I).strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except Exception:
        for open_c, close_c in (("{", "}"), ("[", "]")):
            s = cleaned.find(open_c)
            e = cleaned.rfind(close_c)
            if s != -1 and e > s:
                try:
                    return json.loads(cleaned[s:e + 1])
                except Exception:
                    continue
    return None


def _groq_chat_json(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.45,
    max_tokens: int = 900,
    reasoning_effort: str = "none",
) -> Any:
    if not is_groq_configured():
        return None
    if not _acquire_groq_budget("llm"):
        # --- Naga AI fallback: fires only when Groq free-tier quota is exhausted ---
        # Only attempt for caption/polish tasks (short user_prompt content).
        # Batch review payloads are too large for a simple free-tier fallback.
        if len(user_prompt) < 800:
            naga_result = fallback_polish_caption(user_prompt)
            if naga_result:
                # Wrap plain-text Naga response into a minimal JSON envelope so
                # callers that expect dict get something usable.
                print("[groq_clip_brain] Groq quota exhausted → Naga fallback used.")
                return {"naga_fallback": True, "caption": naga_result}
        return None
    client = _get_groq_client()
    if client is None:
        return None

    models_to_try = [DEFAULT_GROQ_MODEL] + [m for m in FALLBACK_GROQ_MODELS if m != DEFAULT_GROQ_MODEL]
    for model_id in models_to_try:
        try:
            kwargs: dict[str, Any] = {
                "model": model_id,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
                "max_completion_tokens": max_tokens,
                "top_p": 0.95,
                "stream": False,
            }
            if "qwen" in model_id.lower():
                kwargs["reasoning_effort"] = reasoning_effort
            try:
                comp = client.chat.completions.create(**kwargs)
            except TypeError:
                kwargs.pop("reasoning_effort", None)
                comp = client.chat.completions.create(**kwargs)
            except Exception as e:
                if "reasoning_effort" in str(e).lower():
                    kwargs.pop("reasoning_effort", None)
                    comp = client.chat.completions.create(**kwargs)
                else:
                    raise

            content = (comp.choices[0].message.content or "").strip() if comp.choices else ""
            parsed = _strip_think_and_extract_json(content)
            if parsed is not None:
                return parsed
        except Exception as exc:
            err_s = str(exc).lower()
            if "model" in err_s and ("not found" in err_s or "does not exist" in err_s or "decommissioned" in err_s):
                continue
            return None
    return None


def read_cached_groq_review(clip_dir: Path) -> dict[str, Any] | None:
    cache_path = clip_dir / "groq_review.json"
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("titles"):
            return data
    except Exception:
        pass
    return None


def _sanitize_review_item(item: dict[str, Any]) -> dict[str, Any] | None:
    titles = [
        _PROFANITY_RE.sub("***", re.sub(r"\s+", " ", str(t)).strip())
        .replace("#Shorts", "")
        .replace("#shorts", "")
        .strip()
        for t in (item.get("titles") or [])
        if str(t).strip()
    ]
    hook_line = _PROFANITY_RE.sub("***", re.sub(r"\s+", " ", str(item.get("hook_line") or "")).strip())
    extra_tags = [re.sub(r"\s+", " ", str(x)).strip().lower() for x in (item.get("extra_tags") or []) if str(x).strip()]
    if not titles or not hook_line:
        return None
    return {
        "keep": bool(item.get("keep", True)),
        "viral_score": max(0, min(100, int(item.get("viral_score") or 70))),
        "score_adj": max(-15, min(18, int(item.get("score_adj") or 0))),
        "clip_label": str(item.get("clip_label") or "LIVE HIGHLIGHT").strip().upper()[:36],
        "reason": str(item.get("reason") or "").strip()[:140],
        "titles": titles[:3],
        "hook_line": hook_line,
        "extra_tags": extra_tags[:5],
        "engine": DEFAULT_GROQ_MODEL,
        "cached_at": round(time.time(), 1),
    }


def groq_batch_review_clips(clip_dirs: list[Path], max_batch: int = 3) -> list[dict[str, Any]]:
    """
    FREE-TIER OPTIMIZER: Packs 2-3 clips into ONE single Groq `qwen/qwen3.8-27b` request!
    Evaluates each clip against the 2026 Viral Shorts Blueprint (0-2s hook, emotional contrast,
    comment-war/shareability, S-Tier >= 90 bar) AND writes `<clip_dir>/groq_review.json` +
    updates `moment.json` (`tier`, `total_score`, `archetype`) so Upload Modal needs 0 extra calls!
    """
    if not is_groq_configured() or not clip_dirs:
        return []

    s_min, a_min = _load_tier_thresholds()
    items_for_prompt: list[dict[str, Any]] = []
    dir_by_id: dict[str, Path] = {}

    for cdir in clip_dirs[:max(1, min(4, max_batch))]:
        if not cdir.is_dir():
            continue
        mj_path = cdir / "moment.json"
        tj_path = cdir / "transcript.json"
        mj = json.loads(mj_path.read_text(encoding="utf-8")) if mj_path.exists() else {}
        tj = json.loads(tj_path.read_text(encoding="utf-8")) if tj_path.exists() else {}
        tx = re.sub(r"\s+", " ", str(tj.get("text") or mj.get("transcript") or "")).strip()
        if len(tx) < 10:
            continue
        cid = cdir.name
        ch = cdir.parent.name
        fus = mj.get("fusion") or {}
        chat = mj.get("chat") or {}
        dono = chat.get("matched_dono") if chat.get("dono_read_verified") else None
        dir_by_id[cid] = cdir
        items_for_prompt.append({
            "clip_id": cid,
            "channel": ch,
            "base_score": float(fus.get("total_score") or 55.0),
            "initial_label": str(fus.get("archetype") or "LIVE MOMENT"),
            "chat_explosion": bool(chat.get("is_explosion")),
            "weird_glitch_chat": bool(chat.get("is_weird_spike")),
            "verified_dono": f"{dono.get('author')} ({dono.get('amount_str')}): {dono.get('msg')}" if dono else None,
            "transcript": tx[:520],
        })

    if not items_for_prompt:
        return []

    sys_p = (
        "You are an elite viral YouTube Shorts producer for ClipSurge, judging clips against 2026 Shorts retention benchmarks:\n"
        "- Target >=70% Viewed vs Swiped Away (needs instant 0-2s hook: shock, funny fail, glitch, debate, or verified dono read).\n"
        "- Target >=95% APV & >=20% Loop Rate (tight setup -> punchline with zero dead air).\n"
        "- S-TIER (>=90/100) is RESERVED strictly for true viral bangers: insane GTA 6 glitches/carjacks/cops, hilarious streamer freakouts, "
        "iconic quotes/debates, wholesome milestones, or verified unhinged dono reads. Give mundane/boring clips negative score_adj (-10 to -15).\n"
        "NEVER fabricate events, NEVER include profanity or #Shorts in titles, NEVER leak internal metrics.\n"
        "Return STRICT JSON ONLY: an object with key \"clips\" mapping to an array (one entry per clip_id in the input)."
    )
    user_p = (
        f"Review this batch of {len(items_for_prompt)} clip(s) in ONE response.\n"
        "For EACH clip, return:\n"
        '{"clip_id": "...", "keep": true/false, "viral_score": 0-100, "score_adj": -15..18, '
        '"clip_label": "2-4 WORD UPPERCASE LABEL", "reason": "1 short sentence", '
        '"titles": [3 distinct 38-76 char clickable titles, max 1 emoji, NO #Shorts], '
        '"hook_line": "1-2 specific viewer-facing sentences", "extra_tags": [5 lowercase SEO tags]}\n\n'
        + json.dumps(items_for_prompt, ensure_ascii=False)
    )

    parsed = _groq_chat_json(sys_p, user_p, temperature=0.45, max_tokens=min(2000, 480 * len(items_for_prompt)), reasoning_effort="none")
    if not isinstance(parsed, dict) or not isinstance(parsed.get("clips"), list):
        return []

    if len(items_for_prompt) > 1:
        # Each batched clip saves ~2 separate calls (judge + metadata)
        record_groq_calls_saved(len(items_for_prompt) * 2 - 1)

    results: list[dict[str, Any]] = []
    for raw_item in parsed["clips"]:
        if not isinstance(raw_item, dict):
            continue
        cid = str(raw_item.get("clip_id") or "")
        cdir = dir_by_id.get(cid)
        if not cdir:
            continue
        clean = _sanitize_review_item(raw_item)
        if not clean:
            continue
        clean["clip_id"] = cid
        (cdir / "groq_review.json").write_text(json.dumps(clean, indent=2), encoding="utf-8")

        # Update moment.json with Groq's refined score, S-Tier (>=90) classification & crisp label
        mj_path = cdir / "moment.json"
        if mj_path.exists():
            try:
                mj = json.loads(mj_path.read_text(encoding="utf-8"))
                fus = mj.setdefault("fusion", {})
                old_score = float(fus.get("base_score") or fus.get("total_score") or 55.0)
                blended = round(max(10.0, min(100.0, (old_score * 0.55 + clean["viral_score"] * 0.45) + clean["score_adj"] * 0.35)), 1)
                fus["total_score"] = blended
                fus["tier"] = "S-TIER" if blended >= s_min else ("A-TIER" if blended >= a_min else "B-TIER")
                fus["archetype"] = clean["clip_label"]
                mj["groq_judge"] = {
                    "keep": clean["keep"],
                    "viral_score": clean["viral_score"],
                    "score_adj": clean["score_adj"],
                    "clip_label": clean["clip_label"],
                    "reason": clean["reason"],
                    "engine": clean["engine"],
                }
                mj_path.write_text(json.dumps(mj, indent=2), encoding="utf-8")
                clean["final_score"] = blended
                clean["final_tier"] = fus["tier"]
            except Exception:
                pass
        results.append(clean)
    return results


def groq_generate_clip_metadata(
    streamer: str,
    game: str,
    platform: str,
    transcript: str,
    archetype: str = "",
    matched_dono: dict | None = None,
    clip_dir: Path | None = None,
) -> dict[str, Any] | None:
    """
    Cache-first viral Shorts metadata generator:
      - Checks `<clip_dir>/groq_review.json` FIRST (0 API calls!)
      - Only hits Groq if uncached, and immediately caches the result on disk.
    """
    if clip_dir is not None:
        cached = read_cached_groq_review(clip_dir)
        if cached:
            record_groq_calls_saved(1)
            return cached

    if not is_groq_configured():
        return None
    tx = re.sub(r"\s+", " ", (transcript or "")).strip()
    if len(tx) < 12 and not matched_dono:
        return None

    dono_ctx = ""
    if matched_dono:
        dono_ctx = (
            f"\nVerified SuperChat/Donation read by streamer: "
            f"{matched_dono.get('author')} ({matched_dono.get('amount_str')}): \"{matched_dono.get('msg')}\""
        )

    sys_p = (
        "You are an elite viral YouTube Shorts editor for ClipSurge. "
        "Write punchy, human-sounding, curiosity-gap titles strictly grounded in what ACTUALLY happened in the transcript. "
        "NEVER fabricate events, NEVER use generic boilerplate like 'Loses His Mind' when a specific funny event happened, "
        "NEVER include profanity or #Shorts in titles, and NEVER include internal scores. Return STRICT JSON ONLY."
    )
    user_p = (
        f"Streamer: {streamer}\n"
        f"Game: {game or 'Gaming'}\n"
        f"Platform: {platform}\n"
        f"Detected moment vibe: {archetype}\n"
        f"Spoken transcript: {tx[:850]}"
        f"{dono_ctx}\n\n"
        'Return JSON: {"titles": [3 distinct 38-76 char clickable titles, max 1 emoji, NO #Shorts], '
        '"hook_line": "1-2 specific viewer-facing sentences", "extra_tags": [5 lowercase SEO tags]}'
    )
    parsed = _groq_chat_json(sys_p, user_p, temperature=0.5, max_tokens=480, reasoning_effort="none")
    if not isinstance(parsed, dict):
        return None
    clean = _sanitize_review_item(parsed)
    if clean and clip_dir is not None and clip_dir.is_dir():
        try:
            (clip_dir / "groq_review.json").write_text(json.dumps(clean, indent=2), encoding="utf-8")
        except Exception:
            pass
    return clean


def groq_transcribe_wav(
    wav_path: Path,
    language: str = "auto",
    prompt_hint: str = "",
    clip_score: float = 70.0,
) -> dict[str, Any] | None:
    """
    Free-tier-guarded word-timestamped transcription via Groq `whisper-large-v3-turbo` (~0.35s, 0 VRAM).
    Skips low B-tier clips (< whisper_min_score) so audio quota is saved for strong A/S-tier clips!
    """
    if not is_groq_configured() or not wav_path or not Path(wav_path).exists():
        return None
    lim = _load_blueprint_limits()
    min_sc = float(lim.get("whisper_min_score", 65.0))
    if clip_score < min_sc:
        record_groq_calls_saved(1)
        return None
    if not _acquire_groq_budget("whisper", audio_sec=28.0):
        return None
    client = _get_groq_client()
    if client is None:
        return None

    import subprocess
    import tempfile

    try:
        with tempfile.TemporaryDirectory(prefix="groq_asr_") as td:
            mp3_path = Path(td) / "clip.mp3"
            subprocess.run(
                [
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-i", str(wav_path),
                    "-vn", "-ar", "16000", "-ac", "1", "-b:a", "48k",
                    str(mp3_path),
                ],
                check=True,
                timeout=10,
            )
            kwargs: dict[str, Any] = {
                "file": (mp3_path.name, mp3_path.read_bytes()),
                "model": "whisper-large-v3-turbo",
                "response_format": "verbose_json",
                "timestamp_granularities": ["word"],
                "temperature": 0.0,
            }
            if language and language.lower() in ("en", "hi"):
                kwargs["language"] = language.lower()
            if prompt_hint:
                kwargs["prompt"] = prompt_hint[:220]

            tr = client.audio.transcriptions.create(**kwargs)
            text = str(getattr(tr, "text", "") or "").strip()
            raw_words = getattr(tr, "words", None) or []
            words: list[dict[str, Any]] = []
            for w in raw_words:
                tok = str((w.get("word") if isinstance(w, dict) else getattr(w, "word", "")) or "").strip()
                if not tok:
                    continue
                st = float((w.get("start") if isinstance(w, dict) else getattr(w, "start", 0.0)) or 0.0)
                en = float((w.get("end") if isinstance(w, dict) else getattr(w, "end", st + 0.15)) or (st + 0.15))
                words.append({
                    "word": tok,
                    "start": round(max(0.0, st), 3),
                    "end": round(max(st + 0.06, en), 3),
                    "probability": 0.96,
                })
            if words or text:
                return {"engine": "groq-whisper-large-v3-turbo", "text": text, "words": words}
    except Exception:
        return None
    return None


def groq_polish_caption_phrases(
    phrases: list[list[dict]],
    streamer: str = "",
    game: str = "",
) -> list[list[dict]] | None:
    """
    Wispr Flow-style whole-clip caption reviewer using Groq (`qwen/qwen3.8-27b`).
    Respects soft free-tier RPM/RPD caps automatically.
    """
    if not is_groq_configured() or not phrases:
        return None

    numbered = [f"{i + 1}. {' '.join(w['word'] for w in ph)}" for i, ph in enumerate(phrases)]
    ctx_line = f"Streamer: {streamer or 'Gaming Streamer'} | Game: {game or 'GTA 6 / Live Gaming'}"
    sys_p = (
        "You are a Wispr Flow-grade real-time caption editor for viral YouTube Shorts gaming clips.\n"
        "Review the full numbered list of ASR caption phrases together using whole-clip context and follow these rules strictly:\n"
        "1. Preserve the streamer's authentic voice, hype energy, and casual slang ('bro', 'chat', 'no way', 'bhai', 'arey'). Never make it sound corporate or robotic.\n"
        "2. Clean speech-to-text artifacts: remove 'uh', 'um', 'erm', accidental stutters/false restarts, and broken half-words.\n"
        "3. Fix context-obvious ASR mishearings & proper nouns (e.g., 'GTA 6', 'Vice City', 'Leonida', 'Lucia', 'Jason', 'IShowSpeed', 'Kai Cenat', 'xQc', 'Mythpat', 'Ronaldo', 'Ferrari', 'Lamborghini', 'cops everywhere', 'out of the car').\n"
        "4. If a phrase is pure unintelligible ASR gibberish, background noise hallucination, or 'nan'/'Thank you for watching', replace it with an empty string \"\".\n"
        "5. Keep every phrase concise and readable for vertical Shorts captions, with natural punctuation ('!', '?', apostrophes) and Latin script only (Romanized Hinglish for Hindi, never Devanagari).\n"
        "6. Output STRICT JSON ONLY: a JSON array of strings with the EXACT same length as the input list."
    )
    user_p = (
        f"{ctx_line}\n"
        f"Return a JSON array of exactly {len(phrases)} polished caption strings (use \"\" to drop pure noise):\n\n"
        + "\n".join(numbered)
    )
    fixed = _groq_chat_json(sys_p, user_p, temperature=0.15, max_tokens=900, reasoning_effort="none")

    # Groq quota exhausted → _groq_chat_json returns a Naga fallback dict.
    # We can't reconstruct word-level timestamps from a plain string, so return None
    # gracefully; the caller will fall back to raw ASR phrases.
    if isinstance(fixed, dict) and fixed.get("naga_fallback"):
        print("[groq_clip_brain] Caption phrase polish skipped (Naga fallback not phrase-aware).")
        return None

    if not isinstance(fixed, list) or len(fixed) != len(phrases):
        return None

    updated: list[list[dict]] = []
    for ph, new_line in zip(phrases, fixed):
        cleaned_line = str(new_line or "").strip()
        if not cleaned_line:
            continue
        toks = [t for t in cleaned_line.split() if t]
        if not toks:
            continue
        s0, e0 = float(ph[0]["start"]), float(ph[-1]["end"])
        dt = max(0.14, e0 - s0) / len(toks)
        updated.append([
            {
                "word": tok,
                "start": round(s0 + idx * dt, 3),
                "end": round(min(s0 + (idx + 1) * dt, s0 + idx * dt + 1.15), 3),
                "probability": 0.97,
            }
            for idx, tok in enumerate(toks)
        ])
    return updated


def groq_judge_live_clip(
    channel: str,
    transcript: str,
    archetype: str,
    score: float,
    chat_summary: dict | None = None,
) -> dict[str, Any] | None:
    """Single-clip fallback judge (prefer groq_batch_review_clips for 2-3 clips at once!)."""
    if not is_groq_configured():
        return None
    tx = re.sub(r"\s+", " ", (transcript or "")).strip()
    if len(tx) < 15:
        return None
    sys_p = (
        "You are a viral gaming Shorts producer judging whether a clip meets the 2026 S-Tier (>=90/100) bar. "
        "Return STRICT JSON ONLY."
    )
    user_p = (
        f"Channel: {channel} | Base score: {score}/100 | Initial tag: {archetype}\n"
        f"Transcript: {tx[:650]}\n\n"
        'Return JSON: {"keep": true/false, "score_adj": -15..15, "clip_label": "2-4 WORD UPPERCASE LABEL", "reason": "1 short sentence"}'
    )
    parsed = _groq_chat_json(sys_p, user_p, temperature=0.2, max_tokens=200, reasoning_effort="none")
    if not isinstance(parsed, dict) or "keep" not in parsed:
        return None
    return {
        "keep": bool(parsed.get("keep", True)),
        "score_adj": max(-15, min(15, int(parsed.get("score_adj") or 0))),
        "clip_label": str(parsed.get("clip_label") or archetype).strip().upper()[:36],
        "reason": str(parsed.get("reason") or "").strip()[:140],
        "engine": DEFAULT_GROQ_MODEL,
    }


if __name__ == "__main__":
    print(json.dumps(get_groq_usage_summary(), indent=2))
