#!/usr/bin/env python3
"""
CreatorRadar / ClipSurge — Viral Style Blueprint & Self-Improving Taste Memory

Learns continuously from the channel owner's Approve, Upload, and Delete actions
in the Live Clipper dashboard:
  - Approved clip  -> +1.0 reinforcement
  - Uploaded clip  -> +1.5 strong reinforcement
  - Deleted clip   -> -1.0 negative feedback

Computes bounded, Laplace-smoothed multipliers per normalized archetype family
and keyword bucket, blended with config/viral-style-bible.json, so the clipper
steadily locks onto the owner's exact taste without drifting wildly.
"""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Any

STUDIO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = STUDIO_ROOT / "config"
BLUEPRINT_PATH = CONFIG_DIR / "viral-style-bible.json"
MEMORY_PATH = CONFIG_DIR / "clipper-taste-memory.json"

_MEM_LOCK = threading.Lock()

DEFAULT_MEMORY: dict[str, Any] = {
    "version": "1.0",
    "updated_at": 0.0,
    "totals": {"approved": 0, "uploaded": 0, "deleted": 0},
    "archetypes": {},
    "keywords": {},
    "channels": {},
    "recent_events": [],
}


def load_viral_blueprint() -> dict[str, Any]:
    if BLUEPRINT_PATH.exists():
        try:
            return json.loads(BLUEPRINT_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "version": "1.0",
        "pacing": {"target_clip_sec": 22, "min_clip_sec": 11, "max_clip_sec": 30, "max_trailing_silence_sec": 1.8, "dono_reaction_watch_sec": 15.0},
        "archetype_weights": {},
    }


def normalize_archetype_family(
    archetype: str,
    has_weird_dono: bool = False,
    has_weird_glitch: bool = False,
    has_facecam_antics: bool = False,
) -> str:
    if has_weird_dono:
        return "weird_dono"
    if has_weird_glitch:
        return "wonky_glitch"
    if has_facecam_antics:
        return "facecam_antics"

    a = (archetype or "").lower()
    if any(k in a for k in ("dono", "superchat", "bits", "donation")):
        return "weird_dono"
    if any(k in a for k in ("glitch", "wonky", "weird", "ayo", "sus", "bug")):
        return "wonky_glitch"
    if any(k in a for k in ("facecam", "antics", "freakout")):
        return "facecam_antics"
    if any(k in a for k in ("emotional", "heartfelt", "thank")):
        return "emotional"
    if "clip call" in a:
        return "clip_call"
    if any(k in a for k in ("comedy", "fail", "rage")):
        return "comedy_fail"
    if any(k in a for k in ("shock", "disbelief")):
        return "shock"
    if "chat" in a:
        return "chat_explosion"
    if "cool play" in a or "clutch" in a or "hype" in a:
        return "cool_play"
    if "story" in a:
        return "story_comedy"
    if "silent" in a:
        return "silent_visual"
    return "audio_peak"


def load_taste_memory() -> dict[str, Any]:
    if MEMORY_PATH.exists():
        try:
            data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for k, v in DEFAULT_MEMORY.items():
                    data.setdefault(k, v if not isinstance(v, (dict, list)) else (dict(v) if isinstance(v, dict) else list(v)))
                return data
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_MEMORY))


def _save_taste_memory(mem: dict[str, Any]):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    mem["updated_at"] = time.time()
    tmp = MEMORY_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(mem, indent=2), encoding="utf-8")
    tmp.replace(MEMORY_PATH)


def record_clip_feedback(clip_dir: Path, decision: str, channel: str = "") -> dict[str, Any]:
    """
    Record owner feedback ('approved', 'uploaded', 'deleted') for a live clip folder.
    Safe to call right before deleting clip_dir (reads moment.json before deletion).
    """
    decision = (decision or "").strip().lower()
    if decision not in ("approved", "uploaded", "deleted"):
        return {"recorded": False, "reason": f"invalid decision '{decision}'"}

    moment_path = clip_dir / "moment.json"
    moment: dict[str, Any] = {}
    if moment_path.exists():
        try:
            moment = json.loads(moment_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    fusion = moment.get("fusion") or {}
    chat = moment.get("chat") or {}
    visual = moment.get("visual") or {}
    txt_sig = moment.get("transcript_score") or {}

    archetype_raw = str(fusion.get("archetype") or "LIVE MOMENT")
    family = normalize_archetype_family(
        archetype_raw,
        has_weird_dono=bool(chat.get("top_weird_dono") or chat.get("dono_watch_active")),
        has_weird_glitch=bool(chat.get("is_weird_spike")),
        has_facecam_antics=bool(visual.get("facecam_antics")),
    )
    ch_key = (channel or clip_dir.parent.name or "unknown").strip().lower()

    matched_kw = [str(k).lower() for k in (txt_sig.get("matched_keywords") or []) if str(k).strip()]
    matched_cats = [str(k).lower() for k in (txt_sig.get("matched_categories") or {}).keys()]
    weird_toks = [str(k).lower() for k in (chat.get("weird_tokens_hit") or []) if str(k).strip()]
    feature_keys = list(dict.fromkeys(matched_kw + matched_cats + weird_toks))[:8]

    with _MEM_LOCK:
        mem = load_taste_memory()
        mem["totals"][decision] = int(mem["totals"].get(decision, 0)) + 1

        def _bump(bucket: dict[str, Any], key: str):
            rec = bucket.setdefault(key, {"approved": 0, "uploaded": 0, "deleted": 0})
            rec[decision] = int(rec.get(decision, 0)) + 1

        _bump(mem["archetypes"], family)
        _bump(mem["channels"], ch_key)
        for fk in feature_keys:
            _bump(mem["keywords"], fk)

        event = {
            "ts": round(time.time(), 1),
            "clip_id": clip_dir.name,
            "channel": ch_key,
            "decision": decision,
            "family": family,
            "archetype": archetype_raw,
            "score": fusion.get("total_score"),
            "features": feature_keys,
        }
        recent = mem.get("recent_events") or []
        recent.append(event)
        mem["recent_events"] = recent[-120:]
        _save_taste_memory(mem)

    return {"recorded": True, "family": family, "decision": decision, "features": feature_keys}


def _stat_to_multiplier(stat: dict[str, Any] | None, prior: float = 3.0, strength: float = 0.28) -> float:
    """Laplace-smoothed positive/negative preference ratio mapped smoothly around 1.0."""
    if not stat:
        return 1.0
    pos = float(stat.get("approved", 0)) * 1.0 + float(stat.get("uploaded", 0)) * 1.5
    neg = float(stat.get("deleted", 0)) * 1.0
    if pos + neg < 1.0:
        return 1.0
    # Neutral = 0.5 -> mult = 1.0; all positive -> approaches 1 + strength; all negative -> approaches 1 - strength
    rate = (pos + prior * 0.5) / (pos + neg + prior)
    delta = (rate - 0.5) * 2.0 * strength
    return round(max(0.74, min(1.30, 1.0 + delta)), 3)


def get_taste_multiplier(
    archetype: str,
    channel: str = "",
    matched_keywords: list[str] | None = None,
    matched_categories: list[str] | None = None,
    weird_tokens: list[str] | None = None,
    has_weird_dono: bool = False,
    has_weird_glitch: bool = False,
    has_facecam_antics: bool = False,
) -> dict[str, Any]:
    """
    Combine Viral Style Blueprint prior weight with learned owner Taste Memory.
    Returns a bounded multiplier in [0.72, 1.38] and a concise human-readable reason.
    """
    bp = load_viral_blueprint()
    mem = load_taste_memory()

    family = normalize_archetype_family(
        archetype,
        has_weird_dono=has_weird_dono,
        has_weird_glitch=has_weird_glitch,
        has_facecam_antics=has_facecam_antics,
    )
    bp_weights = bp.get("archetype_weights") or {}
    bp_w = float(bp_weights.get(family, 1.0))

    arch_mult = _stat_to_multiplier((mem.get("archetypes") or {}).get(family), prior=3.0, strength=0.25)

    kw_keys = [
        str(k).lower()
        for k in list(matched_keywords or []) + list(matched_categories or []) + list(weird_tokens or [])
        if str(k).strip()
    ]
    kw_mults = [
        _stat_to_multiplier((mem.get("keywords") or {}).get(k), prior=4.0, strength=0.16)
        for k in kw_keys
        if k in (mem.get("keywords") or {})
    ]
    kw_mult = float(sum(kw_mults) / len(kw_mults)) if kw_mults else 1.0

    combined = round(max(0.72, min(1.38, bp_w * arch_mult * kw_mult)), 3)
    reasons = []
    if abs(bp_w - 1.0) >= 0.04:
        reasons.append(f"blueprint:{family}={bp_w:.2f}x")
    if abs(arch_mult - 1.0) >= 0.03:
        reasons.append(f"taste:{family}={arch_mult:.2f}x")
    if abs(kw_mult - 1.0) >= 0.03:
        reasons.append(f"taste:kw={kw_mult:.2f}x")

    return {
        "family": family,
        "multiplier": combined,
        "blueprint_weight": round(bp_w, 3),
        "taste_weight": round(arch_mult * kw_mult, 3),
        "reason": ", ".join(reasons) or "neutral",
    }


def get_taste_memory_summary() -> dict[str, Any]:
    bp = load_viral_blueprint()
    mem = load_taste_memory()
    totals = mem.get("totals") or {}
    arch_scores = []
    for fam, st in (mem.get("archetypes") or {}).items():
        m = _stat_to_multiplier(st, prior=3.0, strength=0.25)
        arch_scores.append({
            "family": fam,
            "multiplier": m,
            "approved": int(st.get("approved", 0)),
            "uploaded": int(st.get("uploaded", 0)),
            "deleted": int(st.get("deleted", 0)),
        })
    arch_scores.sort(key=lambda x: -x["multiplier"])
    return {
        "blueprint_version": bp.get("version", "1.0"),
        "target_clip_sec": (bp.get("pacing") or {}).get("target_clip_sec", 22),
        "totals": {
            "approved": int(totals.get("approved", 0)),
            "uploaded": int(totals.get("uploaded", 0)),
            "deleted": int(totals.get("deleted", 0)),
            "total_decisions": int(totals.get("approved", 0)) + int(totals.get("uploaded", 0)) + int(totals.get("deleted", 0)),
        },
        "boosted": [a for a in arch_scores if a["multiplier"] > 1.02][:4],
        "dampened": [a for a in reversed(arch_scores) if a["multiplier"] < 0.98][:4],
        "recent_count": len(mem.get("recent_events") or []),
    }


if __name__ == "__main__":
    print(json.dumps(get_taste_memory_summary(), indent=2))
