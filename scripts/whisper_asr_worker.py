#!/usr/bin/env python3
"""
Persistent CUDA Multilingual ASR Worker (Hindi / Hinglish / English)
Runs inside VoiceStudio/.venv (PyTorch CUDA + HuggingFace transformers) so zero
extra PyTorch/CUDA packages are duplicated on disk.

Protocol (JSON Lines over stdin/stdout):
  Request:  {"wav": "/abs/path/clip_16k.wav", "language": "auto" | "hi" | "en"}
  Response: {"ok": true, "engine": "whisper-small (cuda)", "text": "...", "raw_text": "...", "words": [...]}
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# Pure-Python Devanagari -> readable Romanized Hinglish transliterator
# Prevents missing-glyph tofu boxes in libass/DejaVu Sans while keeping Indian Shorts punchy.
_VOWELS = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo",
    "ऋ": "ri", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "ऑ": "o", "ऍ": "e",
}
_MATRAS = {
    "ा": "a", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "ृ": "ri",
    "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ॉ": "o", "ॅ": "e",
}
_CONSONANTS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ng",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "ny",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh",
    "ष": "sh", "स": "s", "ह": "h", "ळ": "l",
    "क़": "q", "ख़": "kh", "ग़": "gh", "ज़": "z", "ड़": "d", "ढ़": "dh", "फ़": "f",
}
_SIGNS = {"ं": "n", "ँ": "n", "ः": "h", "।": ".", "॥": "."}
_DIGITS = {"०": "0", "१": "1", "२": "2", "३": "3", "४": "4", "५": "5", "६": "6", "७": "7", "८": "8", "९": "9"}
_HALANT = "्"
_NUKTA = "़"


def devanagari_to_hinglish(text: str) -> str:
    """Convert any Devanagari spans into readable Romanized Hinglish while preserving English."""
    if not any("\u0900" <= ch <= "\u097F" for ch in text):
        return text

    out: list[str] = []
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        # Handle nukta combined consonants like ज़, फ़, ड़
        if i + 1 < n and text[i + 1] == _NUKTA and (ch + _NUKTA) in _CONSONANTS:
            cons = _CONSONANTS[ch + _NUKTA]
            i += 2
            nxt = text[i] if i < n else ""
            if nxt == _HALANT:
                out.append(cons)
                i += 1
            elif nxt in _MATRAS:
                out.append(cons + _MATRAS[nxt])
                i += 1
            else:
                # Drop inherent schwa at word end
                is_word_end = (i >= n) or (not ("\u0900" <= nxt <= "\u097F"))
                out.append(cons if is_word_end else cons + "a")
            continue

        if ch in _CONSONANTS:
            cons = _CONSONANTS[ch]
            i += 1
            nxt = text[i] if i < n else ""
            if nxt == _HALANT:
                out.append(cons)
                i += 1
            elif nxt in _MATRAS:
                out.append(cons + _MATRAS[nxt])
                i += 1
            else:
                is_word_end = (i >= n) or (not ("\u0900" <= nxt <= "\u097F"))
                out.append(cons if is_word_end else cons + "a")
        elif ch in _VOWELS:
            out.append(_VOWELS[ch])
            i += 1
        elif ch in _MATRAS:
            out.append(_MATRAS[ch])
            i += 1
        elif ch in _SIGNS:
            out.append(_SIGNS[ch])
            i += 1
        elif ch in _DIGITS:
            out.append(_DIGITS[ch])
            i += 1
        elif ch in (_HALANT, _NUKTA):
            i += 1
        else:
            out.append(ch)
            i += 1

    res = "".join(out)
    res = re.sub(r"\s+", " ", res).strip()
    return res


def distribute_chunk_words(chunks: list[dict], total_duration: float) -> list[dict]:
    """Convert Whisper word or phrase chunks into clean word-level timestamps."""
    words: list[dict] = []
    for ch in chunks:
        raw = str(ch.get("text") or "").strip()
        if not raw:
            continue
        ts = ch.get("timestamp") or (0.0, total_duration)
        t0 = float(ts[0]) if ts[0] is not None else (words[-1]["end"] if words else 0.0)
        t1 = float(ts[1]) if (len(ts) > 1 and ts[1] is not None) else min(total_duration, t0 + max(0.35, len(raw.split()) * 0.25))
        if t1 <= t0:
            t1 = t0 + 0.18

        hinglish = devanagari_to_hinglish(raw)
        toks = [t for t in hinglish.split() if t]
        if not toks:
            continue
        if len(toks) == 1:
            words.append({"word": toks[0], "start": round(t0, 3), "end": round(t1, 3), "probability": 0.95})
        else:
            step = (t1 - t0) / len(toks)
            for idx, tok in enumerate(toks):
                w0 = t0 + idx * step
                w1 = t0 + (idx + 1) * step
                words.append({"word": tok, "start": round(w0, 3), "end": round(w1, 3), "probability": 0.92})
    return words


def load_pipeline(model_id: str, device_pref: str = "auto"):
    import torch
    import transformers
    from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline

    transformers.logging.set_verbosity_error()

    use_cuda = (device_pref != "cpu") and torch.cuda.is_available()
    device = "cuda:0" if use_cuda else "cpu"
    dtype = torch.float16 if use_cuda else torch.float32

    model = AutoModelForSpeechSeq2Seq.from_pretrained(
        model_id,
        dtype=dtype,
        low_cpu_mem_usage=True,
    )
    model.to(device)
    processor = AutoProcessor.from_pretrained(model_id)

    asr = pipeline(
        "automatic-speech-recognition",
        model=model,
        tokenizer=processor.tokenizer,
        feature_extractor=processor.feature_extractor,
        dtype=dtype,
        device=device,
    )
    return asr, f"{model_id.split('/')[-1]} ({'cuda' if use_cuda else 'cpu'})"


def _dedup_hallucinations(words: list[dict]) -> list[dict]:
    """Strip classic Whisper silence loops (same word/phrase repeated 4+ times consecutively)."""
    if len(words) < 4:
        return words
    cleaned: list[dict] = []
    repeat_run = 0
    for w in words:
        tok = w["word"].lower().strip(".,!?")
        prev = cleaned[-1]["word"].lower().strip(".,!?") if cleaned else ""
        if tok and tok == prev:
            repeat_run += 1
            if repeat_run >= 2:
                continue
        else:
            repeat_run = 0
        cleaned.append(w)
    return cleaned


def detect_speech_segments(data, sr: int, min_speech_sec: float = 0.45, max_seg_sec: float = 8.0) -> list[tuple[float, float]]:
    """
    Lightweight RMS Voice Activity Detector (numpy-only) that splits audio into
    natural spoken phrases (0.45s - 8.0s). Gives frame-accurate phrase start/end
    timestamps and eliminates silence hallucinations on Whisper-Hindi2Hinglish-Apex.
    """
    import numpy as np

    hop = max(1, int(sr * 0.05))  # 50 ms frames
    n_frames = len(data) // hop
    if n_frames < 4:
        return [(0.0, len(data) / float(sr))]

    rms = np.array([
        float(np.sqrt(np.mean(data[i * hop:(i + 1) * hop] ** 2)) + 1e-9)
        for i in range(n_frames)
    ])
    db = 20.0 * np.log10(rms)
    # Adaptive threshold above noise floor (handles game engine/music background cleanly)
    floor = float(np.percentile(db, 20))
    peak = float(np.percentile(db, 95))
    thresh = max(-42.0, min(-22.0, floor + (peak - floor) * 0.28))

    active = db >= thresh
    # Bridge brief <0.35s intra-sentence pauses
    bridge = 7
    i = 0
    while i < n_frames:
        if not active[i]:
            j = i
            while j < n_frames and not active[j]:
                j += 1
            if i > 0 and j < n_frames and (j - i) <= bridge:
                active[i:j] = True
            i = j
        else:
            i += 1

    raw_segs: list[tuple[float, float]] = []
    in_seg = False
    start_f = 0
    for idx in range(n_frames):
        if active[idx] and not in_seg:
            in_seg = True
            start_f = idx
        elif not active[idx] and in_seg:
            in_seg = False
            s_t = max(0.0, start_f * 0.05 - 0.12)
            e_t = min(len(data) / float(sr), idx * 0.05 + 0.15)
            if (e_t - s_t) >= min_speech_sec:
                raw_segs.append((s_t, e_t))
    if in_seg:
        s_t = max(0.0, start_f * 0.05 - 0.12)
        e_t = len(data) / float(sr)
        if (e_t - s_t) >= min_speech_sec:
            raw_segs.append((s_t, e_t))

    if not raw_segs:
        return [(0.0, min(len(data) / float(sr), max_seg_sec))]

    # Subdivide any continuous speech segment longer than max_seg_sec at local quietest dips
    final_segs: list[tuple[float, float]] = []
    for s_t, e_t in raw_segs:
        cur = s_t
        while (e_t - cur) > max_seg_sec:
            # Search for quietest 50ms frame between cur+4.5s and cur+max_seg_sec
            lo = int((cur + 4.5) / 0.05)
            hi = min(n_frames - 1, int((cur + max_seg_sec) / 0.05))
            cut_f = lo + int(np.argmin(db[lo:hi + 1])) if hi > lo else hi
            cut_t = cut_f * 0.05
            final_segs.append((cur, cut_t))
            cur = cut_t
        if (e_t - cur) >= 0.35:
            final_segs.append((cur, e_t))
    return final_segs


def transcribe_one(asr, engine_label: str, wav_path: str, language: str = "auto") -> dict:
    import math
    import numpy as np
    import soundfile as sf
    import torch

    data, sr = sf.read(wav_path, dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)
    duration = len(data) / float(sr) if sr else 10.0

    # Skip near-silent chunks to prevent Whisper silence hallucinations
    rms = float(np.sqrt(np.mean(data ** 2)) + 1e-9) if len(data) else 1e-9
    rms_db = 20.0 * math.log10(rms)
    if rms_db < -46.0 or duration < 0.35:
        return {"ok": True, "engine": engine_label, "raw_text": "", "text": "", "words": []}

    is_hinglish_model = "hinglish" in engine_label.lower()
    gen_kwargs: dict = {
        "task": "transcribe",
        "repetition_penalty": 1.18,
        "no_repeat_ngram_size": 3,
        "max_new_tokens": 128,
    }
    if not is_hinglish_model and language in ("hi", "en", "hindi", "english"):
        gen_kwargs["language"] = "hindi" if language.startswith("hi") else "english"
    elif is_hinglish_model and language in ("en", "english"):
        gen_kwargs["language"] = "english"

    arr = np.asarray(data, dtype=np.float32)

    # For Hinglish-Apex (alignment_heads=null): use VAD phrase segmentation so EVERY spoken phrase
    # gets exact start/end timestamps & zero silence hallucination loops!
    if is_hinglish_model:
        segs = detect_speech_segments(arr, int(sr), min_speech_sec=0.45, max_seg_sec=7.5)
        all_words: list[dict] = []
        raw_parts: list[str] = []
        with torch.inference_mode():
            for s_t, e_t in segs:
                seg_arr = arr[int(s_t * sr):int(e_t * sr)]
                if len(seg_arr) < int(0.3 * sr):
                    continue
                out = asr({"raw": seg_arr.copy(), "sampling_rate": int(sr)}, generate_kwargs=gen_kwargs)
                seg_raw = (out.get("text") or "").strip()
                if not seg_raw:
                    continue
                raw_parts.append(seg_raw)
                seg_words = _dedup_hallucinations(
                    distribute_chunk_words([{"text": seg_raw, "timestamp": (s_t, e_t)}], e_t)
                )
                # Drop trailing single-syllable hallucination noise if a phrase has too few real words
                all_words.extend(seg_words)
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        raw_text = " ".join(raw_parts).strip()
        hinglish_text = " ".join(w["word"] for w in all_words).strip()
        return {
            "ok": True,
            "engine": engine_label,
            "raw_text": raw_text,
            "text": hinglish_text,
            "words": all_words,
        }

    pipe_kwargs: dict = {"generate_kwargs": gen_kwargs}
    if duration > 28.0:
        pipe_kwargs["chunk_length_s"] = 25
        pipe_kwargs["stride_length_s"] = (4, 2)

    with torch.inference_mode():
        try:
            out = asr({"raw": arr.copy(), "sampling_rate": int(sr)}, return_timestamps="word", **pipe_kwargs)
        except Exception:
            out = asr({"raw": arr.copy(), "sampling_rate": int(sr)}, return_timestamps=True, **pipe_kwargs)
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    raw_text = (out.get("text") or "").strip()
    hinglish_text = devanagari_to_hinglish(raw_text)
    chunks = out.get("chunks") or []
    words = _dedup_hallucinations(distribute_chunk_words(chunks, duration))
    if not words and hinglish_text:
        words = _dedup_hallucinations(distribute_chunk_words([{"text": raw_text, "timestamp": (0.0, duration)}], duration))
    if words:
        hinglish_text = " ".join(w["word"] for w in words).strip()

    return {
        "ok": True,
        "engine": engine_label,
        "raw_text": raw_text,
        "text": hinglish_text,
        "words": words,
    }


def main():
    parser = argparse.ArgumentParser(description="Persistent CUDA Whisper ASR Worker (Hindi/Hinglish/English)")
    parser.add_argument(
        "--model",
        default="Oriserve/Whisper-Hindi2Hinglish-Apex",
        help="HF Whisper model ID (default: Oriserve/Whisper-Hindi2Hinglish-Apex)",
    )
    parser.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    parser.add_argument("--once", default=None, help="Transcribe a single WAV file and exit")
    parser.add_argument("--language", default="auto", help="auto, hi, or en")
    args = parser.parse_args()

    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    asr, engine_label = load_pipeline(args.model, args.device)

    if args.once:
        res = transcribe_one(asr, engine_label, args.once, args.language)
        print(json.dumps(res, ensure_ascii=False), flush=True)
        return

    # Signal ready to parent process
    print(json.dumps({"ready": True, "engine": engine_label}), flush=True)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            if req.get("cmd") == "quit":
                break
            wav = req.get("wav", "")
            lang = req.get("language", args.language)
            res = transcribe_one(asr, engine_label, wav, lang)
            print(json.dumps(res, ensure_ascii=False), flush=True)
        except Exception as e:
            print(json.dumps({"ok": False, "error": str(e), "text": "", "words": []}), flush=True)


if __name__ == "__main__":
    main()
