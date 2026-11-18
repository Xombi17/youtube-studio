#!/usr/bin/env python3
"""
CreatorRadar Caption Spelling Polisher & Acoustic Aligner
Runs AFTER ASR (Whisper Hinglish-Apex / Whisper / Whistle) and BEFORE ASS subtitle
generation & NVENC video encoding.

Pipeline:
  1. Spelling & Hinglish Normalization (config/caption-glossary.json):
     - Multi-word phrase corrections ("harbar bridge" -> "Harbor Bridge", "tere lie" -> "tere liye")
     - Single-word Hinglish & gaming glossary corrections ("nahin" -> "nahi", "pachche" -> "peeche")
     - Drops isolated ASR filler hallucinations ("Yah. Yah.", "uh", "hmm")
     - Collapses accidental ASR stutters while preserving natural double emphasis ("ruk ruk", "nahi nahi")
     - Optional Gemini Flash context polish when GEMINI_API_KEY is set & use_llm=True
  2. Acoustic Vocal-Band Forced Alignment (numpy + scipy + soundfile):
     - Bandpass-filters clip audio to the human vocal band (280 Hz - 3400 Hz)
     - Computes a 10ms vocal-energy envelope to snap phrase boundaries onto real speech onsets/offsets
     - Distributes word start/end times inside each spoken phrase using
       (syllable/character duration weight + punctuation pause weight) mapped over
       cumulative vocal energy (eliminates linear-spread caption drift!)
     - Enforces readable Shorts timing guardrails (min word duration, zero overlaps, clean card breaks)
"""

import argparse
import json
import math
import os
import re
import urllib.request
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, filtfilt

ROOT = Path(__file__).resolve().parent.parent
GLOSSARY_PATH = ROOT / "config" / "caption-glossary.json"


def load_glossary() -> dict:
    if GLOSSARY_PATH.exists():
        return json.loads(GLOSSARY_PATH.read_text(encoding="utf-8"))
    return {
        "phrase_replacements": {},
        "word_replacements": {},
        "drop_isolated_fillers": ["yah", "uh", "um", "hmm"],
        "keep_double_emphasis": ["ruk", "nahi", "haan", "wait", "bhai", "no", "stop"],
    }


def _split_punct(token: str) -> tuple[str, str, str]:
    m = re.match(r"^([^A-Za-z0-9']*)([A-Za-z0-9']+)([^A-Za-z0-9']*)$", token)
    if not m:
        return "", token, ""
    return m.group(1), m.group(2), m.group(3)


def _estimate_syllable_weight(word: str) -> float:
    _, core, trail = _split_punct(word)
    if not core:
        return 1.0
    low = core.lower()
    vowel_groups = len(re.findall(r"[aeiouy]+", low))
    syl = max(1, vowel_groups)
    base = 0.65 * syl + 0.14 * len(core)
    # Add natural breathing pause weight for punctuation
    if any(p in trail for p in (".", "!", "?")):
        base += 1.4
    elif any(p in trail for p in (",", ";", ":")):
        base += 0.7
    return max(0.8, base)


def clean_word_spellings(words: list[dict], glossary: dict) -> list[dict]:
    """Apply phrase replacements, word glossary fixes, filler removal, and stutter dedup while keeping timing anchors."""
    if not words:
        return []

    word_map = {k.lower(): v for k, v in glossary.get("word_replacements", {}).items()}
    phrase_map = {k.lower(): v for k, v in glossary.get("phrase_replacements", {}).items()}
    drop_fillers = set(f.lower() for f in glossary.get("drop_isolated_fillers", []))
    keep_double = set(k.lower() for k in glossary.get("keep_double_emphasis", []))

    # 1. Single-word spelling normalization + isolated filler removal
    step1: list[dict] = []
    for w in words:
        raw_tok = str(w.get("word") or "").strip()
        if not raw_tok:
            continue
        lead, core, trail = _split_punct(raw_tok)
        low = core.lower()

        # Drop standalone ASR noise fillers & NaN/blank hallucinations unconditionally
        if low in drop_fillers or low in ("nan", "null", "none", "blank_audio", "inaudible", "music"):
            continue

        fixed_core = word_map.get(low, core)
        # Keep trailing punctuation clean (strip double dots/commas)
        trail = re.sub(r"([.,!?])\1+", r"\1", trail)
        fixed_tok = f"{lead}{fixed_core}{trail}".strip()
        if not fixed_tok:
            continue

        # Handle multi-word expansion from single-word glossary (e.g. "gta6" -> "GTA 6")
        parts = fixed_tok.split()
        if len(parts) == 1:
            step1.append({
                "word": parts[0],
                "start": float(w.get("start", 0.0)),
                "end": float(w.get("end", float(w.get("start", 0.0)) + 0.2)),
                "probability": float(w.get("probability", 0.92)),
            })
        else:
            s0, e0 = float(w.get("start", 0.0)), float(w.get("end", 0.2))
            dt = max(0.12, e0 - s0) / len(parts)
            for idx, p in enumerate(parts):
                step1.append({
                    "word": p,
                    "start": round(s0 + idx * dt, 3),
                    "end": round(s0 + (idx + 1) * dt, 3),
                    "probability": float(w.get("probability", 0.92)),
                })

    # 2. Multi-word phrase replacements (longest phrase first: 3-grams then 2-grams)
    sorted_phrases = sorted(phrase_map.items(), key=lambda kv: -len(kv[0].split()))
    step2: list[dict] = []
    i = 0
    n = len(step1)
    while i < n:
        matched = False
        for src_phrase, dst_phrase in sorted_phrases:
            src_toks = src_phrase.split()
            k = len(src_toks)
            if i + k > n:
                continue
            win_cores = [_split_punct(step1[i + j]["word"])[1].lower() for j in range(k)]
            if win_cores == src_toks:
                lead_first = _split_punct(step1[i]["word"])[0]
                trail_last = _split_punct(step1[i + k - 1]["word"])[2]
                dst_toks = dst_phrase.split()
                s0 = step1[i]["start"]
                e0 = step1[i + k - 1]["end"]
                dt = max(0.14, e0 - s0) / len(dst_toks)
                for j, dt_word in enumerate(dst_toks):
                    tok_str = (lead_first if j == 0 else "") + dt_word + (trail_last if j == len(dst_toks) - 1 else "")
                    step2.append({
                        "word": tok_str,
                        "start": round(s0 + j * dt, 3),
                        "end": round(s0 + (j + 1) * dt, 3),
                        "probability": step1[i]["probability"],
                    })
                i += k
                matched = True
                break
        if not matched:
            step2.append(step1[i])
            i += 1

    # 3. Collapse ASR stutters (allow intentional double emphasis like "ruk ruk", drop 3+ or accidental duplicates)
    step3: list[dict] = []
    run_count = 0
    for w in step2:
        cur_low = _split_punct(w["word"])[1].lower()
        prev_low = _split_punct(step3[-1]["word"])[1].lower() if step3 else ""
        if cur_low and cur_low == prev_low:
            run_count += 1
            if cur_low in keep_double and run_count == 1:
                step3.append(w)
            else:
                # Merge end timestamp into previous word so timing stays continuous
                step3[-1]["end"] = max(step3[-1]["end"], w["end"])
        else:
            run_count = 0
            step3.append(w)

    # 4. Capitalize sentence starts cleanly
    for idx, w in enumerate(step3):
        prev_ends_sent = idx == 0 or step3[idx - 1]["word"].endswith((".", "!", "?"))
        if prev_ends_sent:
            lead, core, trail = _split_punct(w["word"])
            if core and core[0].islower():
                w["word"] = f"{lead}{core[0].upper()}{core[1:]}{trail}"

    return step3


def optional_llm_polish_phrases(phrases: list[list[dict]]) -> list[list[dict]]:
    """
    Optional Gemini Flash-Lite contextual spelling refiner (only runs if GEMINI_API_KEY is set).
    Preserves exact phrase grouping and timestamps while fixing Hinglish/English context typos.
    """
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key or not phrases:
        return phrases

    numbered = [f"{i + 1}. {' '.join(w['word'] for w in ph)}" for i, ph in enumerate(phrases)]
    prompt = (
        "Fix obvious ASR spelling errors in these Indian Hinglish/English gaming stream captions. "
        "Keep them in natural Romanized Hinglish (Latin script, no Devanagari), keep the same meaning, "
        "short punchy words, and return ONLY a JSON array of strings with the exact same length "
        f"({len(phrases)} items).\n\n" + "\n".join(numbered)
    )
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
    }).encode("utf-8")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key={api_key}"
    try:
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=12) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        text_out = payload["candidates"][0]["content"]["parts"][0]["text"]
        fixed_lines = json.loads(text_out)
        if not isinstance(fixed_lines, list) or len(fixed_lines) != len(phrases):
            return phrases

        updated: list[list[dict]] = []
        for ph, new_line in zip(phrases, fixed_lines):
            toks = [t for t in str(new_line).strip().split() if t]
            if not toks:
                updated.append(ph)
                continue
            s0, e0 = ph[0]["start"], ph[-1]["end"]
            dt = max(0.15, e0 - s0) / len(toks)
            updated.append([
                {
                    "word": tok,
                    "start": round(s0 + idx * dt, 3),
                    "end": round(s0 + (idx + 1) * dt, 3),
                    "probability": 0.95,
                }
                for idx, tok in enumerate(toks)
            ])
        return updated
    except Exception:
        return phrases


def _vocal_energy_envelope(wav_path: Path, hop_sec: float = 0.01) -> tuple[np.ndarray, float, float]:
    """Compute 10ms bandpass-filtered (280-3400 Hz) vocal speech energy envelope."""
    data, sr = sf.read(str(wav_path), dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)
    duration = len(data) / float(sr) if sr else 0.0
    if len(data) < sr // 4:
        return np.ones(10, dtype=np.float32), hop_sec, duration

    # Bandpass isolate human speech frequencies (rejects car engine bass rumble & high hiss)
    nyq = 0.5 * sr
    lo = min(0.95, 280.0 / nyq)
    hi = min(0.98, 3400.0 / nyq)
    if lo < hi:
        b, a = butter(3, [lo, hi], btype="band")
        data = filtfilt(b, a, data).astype(np.float32)

    hop = max(1, int(round(sr * hop_sec)))
    n_frames = len(data) // hop
    if n_frames < 2:
        return np.ones(2, dtype=np.float32), hop_sec, duration

    reshaped = data[:n_frames * hop].reshape(n_frames, hop)
    env = np.sqrt(np.mean(reshaped ** 2, axis=1) + 1e-10)
    return env, hop_sec, duration


def align_words_acoustically(words: list[dict], wav_path: Path | None) -> list[dict]:
    """
    Re-align word timestamps to real vocal speech energy:
      1. Groups consecutive words into spoken phrases (gap > 0.45s or punctuation boundary).
      2. Snaps each phrase's start/end tightly onto the actual vocal-band speech onset/offset.
      3. Distributes individual words within the phrase by combining syllable weight + vocal energy
         cumulative distribution so captions hit in sync with actual speech cadence.
      4. Enforces clean Shorts timing guardrails (min word duration >= 0.14s, zero overlaps).
    """
    if not words:
        return []

    env = None
    hop = 0.01
    total_dur = max(w["end"] for w in words)
    if wav_path and wav_path.exists():
        try:
            env, hop, total_dur = _vocal_energy_envelope(wav_path, hop_sec=0.01)
        except Exception:
            env = None

    # Group into spoken phrases
    phrases: list[list[dict]] = []
    cur: list[dict] = []
    for w in words:
        if cur and (
            (w["start"] - cur[-1]["end"]) > 0.45
            or cur[-1]["word"].endswith((".", "!", "?"))
            or len(cur) >= 12
        ):
            phrases.append(cur)
            cur = []
        cur.append(w)
    if cur:
        phrases.append(cur)

    aligned: list[dict] = []
    noise_floor = float(np.percentile(env, 25)) if env is not None else 0.0
    speech_peak = float(np.percentile(env, 95)) if env is not None else 1.0
    onset_thresh = noise_floor + (speech_peak - noise_floor) * 0.16

    for ph in phrases:
        p_start = max(0.0, float(ph[0]["start"]))
        p_end = min(total_dur, max(p_start + 0.25, float(ph[-1]["end"])))

        # Snap phrase start/end tightly to actual vocal energy onset & offset (trim leading/trailing dead air)
        if env is not None and len(env) > 10:
            i0 = max(0, int(p_start / hop))
            i1 = min(len(env) - 1, int(p_end / hop))
            if i1 > i0 + 6:
                seg_env = env[i0:i1 + 1]
                active_idx = np.where(seg_env >= onset_thresh)[0]
                if len(active_idx) >= 3:
                    snapped_start = (i0 + int(active_idx[0])) * hop
                    snapped_end = (i0 + int(active_idx[-1]) + 1) * hop
                    # Only snap inwards up to 1.2s so we never distort a whole phrase
                    if 0 <= (snapped_start - p_start) <= 1.2:
                        p_start = max(0.0, snapped_start - 0.04)
                    if 0 <= (p_end - snapped_end) <= 1.2 and (snapped_end - p_start) >= 0.25:
                        p_end = min(total_dur, snapped_end + 0.06)

        # Syllable + vocal energy weighted distribution within [p_start, p_end]
        weights = np.array([_estimate_syllable_weight(w["word"]) for w in ph], dtype=np.float64)
        cum_target = np.cumsum(weights) / np.sum(weights)

        if env is not None and len(env) > 10:
            i0 = max(0, int(p_start / hop))
            i1 = min(len(env) - 1, int(p_end / hop))
            if i1 > i0 + len(ph):
                # Blend 55% vocal energy + 45% uniform time so silent breaths compress naturally
                seg_e = env[i0:i1 + 1].astype(np.float64)
                seg_e = np.maximum(0.0, seg_e - noise_floor * 0.7)
                e_norm = seg_e / (np.sum(seg_e) + 1e-9)
                u_norm = np.ones_like(e_norm) / len(e_norm)
                blended_cdf = np.cumsum(0.55 * e_norm + 0.45 * u_norm)
                blended_cdf /= blended_cdf[-1]

                prev_t = p_start
                for idx, w in enumerate(ph):
                    frac = float(cum_target[idx])
                    pos = int(np.searchsorted(blended_cdf, frac))
                    end_t = min(p_end, (i0 + pos) * hop)
                    if idx == len(ph) - 1:
                        end_t = p_end
                    end_t = max(prev_t + 0.14, end_t)
                    aligned.append({
                        "word": w["word"],
                        "start": round(prev_t, 3),
                        "end": round(end_t, 3),
                        "probability": w.get("probability", 0.95),
                    })
                    prev_t = end_t
                continue

        # Fallback: pure syllable-weighted distribution
        span = max(0.25, p_end - p_start)
        prev_t = p_start
        for idx, w in enumerate(ph):
            end_t = p_start + span * float(cum_target[idx])
            end_t = max(prev_t + 0.14, end_t)
            aligned.append({
                "word": w["word"],
                "start": round(prev_t, 3),
                "end": round(end_t, 3),
                "probability": w.get("probability", 0.95),
            })
            prev_t = end_t

    # Final monotonic / zero-overlap guardrail
    for i in range(1, len(aligned)):
        if aligned[i]["start"] < aligned[i - 1]["end"]:
            mid = round((aligned[i - 1]["end"] + aligned[i]["start"]) / 2.0, 3)
            aligned[i - 1]["end"] = max(aligned[i - 1]["start"] + 0.10, mid)
            aligned[i]["start"] = aligned[i - 1]["end"]
        if aligned[i]["end"] <= aligned[i]["start"] + 0.10:
            aligned[i]["end"] = round(aligned[i]["start"] + 0.14, 3)
        # Never let a single word sit frozen on screen for >1.15s during silence/music gaps
        if aligned[i]["end"] - aligned[i]["start"] > 1.15:
            aligned[i]["end"] = round(aligned[i]["start"] + 1.15, 3)

    return aligned


def polish_and_align_captions(
    raw_words: list[dict],
    wav_path: Path | None = None,
    use_llm: bool = True,
    streamer: str = "",
    game: str = "",
) -> dict:
    """
    Full caption post-processing layer:
      1. Spelling, Hinglish & gaming glossary cleanup + filler/stutter removal
      2. Wispr Flow-style Groq (`qwen/qwen3.8-27b`) whole-clip contextual caption review
         (or optional Gemini Flash-Lite fallback)
      3. Vocal-band acoustic forced alignment & syllable-weighted timing
    Returns dict with 'words', 'text', 'raw_count', 'polished_count', 'llm_used'.
    """
    glossary = load_glossary()
    cleaned = clean_word_spellings(raw_words, glossary)

    llm_used = False
    if use_llm and cleaned:
        groq_ready = False
        try:
            try:
                from scripts.groq_clip_brain import groq_polish_caption_phrases, is_groq_configured
            except ImportError:
                from groq_clip_brain import groq_polish_caption_phrases, is_groq_configured
            groq_ready = is_groq_configured()
        except Exception:
            groq_ready = False

        gemini_ready = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
        if groq_ready or gemini_ready:
            phrases: list[list[dict]] = []
            cur: list[dict] = []
            for w in cleaned:
                if cur and ((w["start"] - cur[-1]["end"]) > 0.55 or len(cur) >= 12):
                    phrases.append(cur)
                    cur = []
                cur.append(w)
            if cur:
                phrases.append(cur)

            polished_phrases = None
            if groq_ready:
                try:
                    polished_phrases = groq_polish_caption_phrases(phrases, streamer=streamer, game=game)
                except Exception:
                    polished_phrases = None
            if polished_phrases is None and gemini_ready:
                polished_phrases = optional_llm_polish_phrases(phrases)
            if polished_phrases is not None:
                cleaned = [w for ph in polished_phrases for w in ph]
                llm_used = True

    aligned = align_words_acoustically(cleaned, wav_path)
    for w in aligned:
        if w["end"] - w["start"] > 1.15:
            w["end"] = round(w["start"] + 1.15, 3)
    text = " ".join(w["word"] for w in aligned).strip()
    return {
        "words": aligned,
        "text": text,
        "raw_count": len(raw_words),
        "polished_count": len(aligned),
        "llm_used": llm_used,
    }


def main():
    parser = argparse.ArgumentParser(description="Polish caption spellings & acoustically align timestamps")
    parser.add_argument("transcript_json", help="Path to transcript.json containing 'words'")
    parser.add_argument("--wav", default=None, help="Optional 16kHz WAV file for vocal-band acoustic alignment")
    parser.add_argument("--no-llm", action="store_true", help="Disable optional Gemini Flash polish")
    parser.add_argument("--out", default=None, help="Output JSON path (defaults to stdout)")
    args = parser.parse_args()

    src = json.loads(Path(args.transcript_json).read_text(encoding="utf-8"))
    raw_words = src.get("words") or []
    res = polish_and_align_captions(
        raw_words,
        wav_path=Path(args.wav) if args.wav else None,
        use_llm=not args.no_llm,
    )
    if args.out:
        Path(args.out).write_text(json.dumps(res, indent=2), encoding="utf-8")
        print(f"Polished {res['raw_count']} -> {res['polished_count']} words -> {args.out}")
    else:
        print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
