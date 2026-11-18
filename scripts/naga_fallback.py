#!/usr/bin/env python3
"""
Naga AI fallback utilities for caption polishing and metadata generation.
This module provides a thin wrapper around Naga's OpenAI‑compatible API and
tracks free‑tier usage in `config/naga-usage-budget.json`.
It is intended to be used as a fallback when Groq quota is exhausted.
"""

import os
import json
import time
import threading
from pathlib import Path
from typing import Any, List, Dict

# Base configuration paths
STUDIO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = STUDIO_ROOT / "config"
NAGA_BUDGET_PATH = CONFIG_DIR / "naga-usage-budget.json"

# Simple lock for budget file access
_BUDGET_LOCK = threading.Lock()


def _load_naga_key() -> str:
    """Load NAGA_API_KEY from environment or .env files."""
    key = os.environ.get("NAGA_API_KEY", "").strip()
    if key:
        return key
    # Fallback to .env files similar to Groq helper
    for env_file in (STUDIO_ROOT / ".env", STUDIO_ROOT / ".env.local"):
        if not env_file.exists():
            continue
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == "NAGA_API_KEY":
                    return v.strip().strip('"').strip("'")
        except Exception:
            continue
    return ""


def _load_budget() -> dict:
    today = time.strftime("%Y-%m-%d", time.gmtime())
    if NAGA_BUDGET_PATH.exists():
        try:
            d = json.loads(NAGA_BUDGET_PATH.read_text(encoding="utf-8"))
            if isinstance(d, dict) and d.get("day") == today:
                d.setdefault("recent_ts", [])
                d.setdefault("calls_today", 0)
                return d
        except Exception:
            pass
    # Initialise fresh budget for today
    return {"day": today, "recent_ts": [], "calls_today": 0}


def _save_budget(d: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = NAGA_BUDGET_PATH.with_suffix('.tmp')
    tmp.write_text(json.dumps(d, indent=2), encoding='utf-8')
    tmp.replace(NAGA_BUDGET_PATH)


def _acquire_naga_budget(limit_rpm: int = 10) -> bool:
    """Enforce a soft RPM limit for the free tier (default 10 RPM)."""
    now = time.time()
    with _BUDGET_LOCK:
        d = _load_budget()
        recent = [ts for ts in d.get("recent_ts", []) if now - ts < 60.0]
        if len(recent) >= limit_rpm:
            return False
        recent.append(now)
        d["recent_ts"] = recent
        d["calls_today"] = d.get("calls_today", 0) + 1
        _save_budget(d)
        return True


def _get_openai_client():
    """Return an OpenAI‑compatible client pointing at Naga's endpoint."""
    api_key = _load_naga_key()
    if not api_key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(base_url="https://api.naga.ac/v1", api_key=api_key, timeout=14.0)
    except Exception:
        return None


def call_naga_chat(model: str, messages: List[Dict[str, str]], temperature: float = 0.7) -> str:
    """Send a chat completion request to Naga AI.
    Returns the raw content string or raises an exception on failure.
    """
    if not _acquire_naga_budget():
        raise RuntimeError("Naga free‑tier RPM limit reached")
    client = _get_openai_client()
    if client is None:
        raise RuntimeError("NAGA_API_KEY not configured")
    response = client.chat.completions.create(model=model, messages=messages, temperature=temperature)
    return response.choices[0].message.content.strip()

# Convenience helper used by the fallback path in Groq pipeline
def _detect_naga_free_model() -> str | None:
    """Query GET /v1/models and return the first model ID ending in ':free'.
    Returns None if the API key is missing, the request fails, or no free model is found.
    Result is cached in-process for 1 hour to avoid extra API calls.
    """
    global _free_model_cache, _free_model_cache_ts
    if _free_model_cache and (time.time() - _free_model_cache_ts) < 3600:
        return _free_model_cache
    client = _get_openai_client()
    if client is None:
        return None
    try:
        models = client.models.list()
        for m in (models.data or []):
            mid = getattr(m, "id", "") or ""
            if mid.endswith(":free"):
                _free_model_cache = mid
                _free_model_cache_ts = time.time()
                return mid
    except Exception:
        pass
    return None

_free_model_cache: str | None = None
_free_model_cache_ts: float = 0.0


def polish_caption_with_naga(raw_caption: str, tone: str = "engaging") -> str:
    """Polish a caption using Naga's free‑tier model.
    The free model identifier is documented in Naga's catalog – we use a
    placeholder ``gpt-4o-2024-05-13:free`` which should be replaced with the
    actual free model name if it changes.
    """
    system_prompt = f"You are a professional social media manager. Refine the caption to be concise, add appropriate emojis and hashtags, and keep the tone {tone}."
    user_prompt = f"Raw caption: {raw_caption}"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    # Model selection priority:
    # 1. NAGA_FREE_MODEL env var (user override)
    # 2. Auto-detect from /v1/models filtered by ":free" suffix (best available)
    # 3. Hardcoded fallback: "gpt-4o-2024-05-13:free"
    free_model = os.environ.get("NAGA_FREE_MODEL", "").strip()
    if not free_model:
        free_model = _detect_naga_free_model() or "gpt-4o-2024-05-13:free"
    return call_naga_chat(free_model, messages)

if __name__ == "__main__":
    # Simple sanity test – prints a polished caption if env is set
    test = "went to the beach today sunset was cool #sunset #beach"
    try:
        print(polish_caption_with_naga(test, tone="inspiring"))
    except Exception as e:
        print(f"Naga fallback test failed: {e}")
