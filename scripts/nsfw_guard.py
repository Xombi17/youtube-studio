#!/usr/bin/env python3
"""
CreatorRadar — content-safety gate for uploads.

Screens a rendered clip for explicit nudity with NudeNet, blurs every flagged
time range, and reports whether the clip is safe to send to YouTube.

    .venv/bin/python scripts/nsfw_guard.py <file-or-clip-dir> [--censor]

Design rules:
- Fail closed. If the detector cannot run, uploads are blocked instead of
  silently passing unscanned content.
- The censored copy (`*_censored.mp4`) is written next to the original; the
  original is never mutated.
- Results are cached in `<clip_dir>/content_safety.json`, keyed on the source
  file size and mtime, so repeated uploads do not re-scan.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

DETECT_CLASSES = {
    "FEMALE_BREAST_EXPOSED",
    "FEMALE_GENITALIA_EXPOSED",
    "MALE_GENITALIA_EXPOSED",
    "BUTTOCKS_EXPOSED",
    "ANUS_EXPOSED",
}

DEFAULT_SAMPLE_FPS = 2.0
DEFAULT_THRESHOLD = 0.30
DEFAULT_BLUR = 28
SAFETY_FILE = "content_safety.json"

_DETECTOR = None
_DETECTOR_ERROR = ""


def _get_detector():
    global _DETECTOR, _DETECTOR_ERROR
    if _DETECTOR is not None:
        return _DETECTOR
    try:
        from nudenet import NudeDetector
    except Exception as exc:  # pragma: no cover - environment dependent
        _DETECTOR_ERROR = f"NudeNet is not installed ({exc.__class__.__name__}). Run: uv pip install nudenet"
        return None
    try:
        _DETECTOR = NudeDetector()
        return _DETECTOR
    except Exception as exc:  # pragma: no cover - model download / runtime
        _DETECTOR_ERROR = f"NudeNet failed to initialise: {exc}"
        return None


def _probe(path: Path) -> dict[str, Any]:
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height:format=duration",
        "-of", "json", str(path),
    ]
    pr = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if pr.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path.name}: {pr.stderr.strip()[:200]}")
    data = json.loads(pr.stdout or "{}")
    stream = (data.get("streams") or [{}])[0]
    duration = float((data.get("format") or {}).get("duration") or 0.0)
    return {"width": int(stream.get("width") or 0), "height": int(stream.get("height") or 0), "duration": duration}


def _extract_frames(path: Path, out_dir: Path, sample_fps: float, width: int = 640) -> int:
    cmd = [
        "ffmpeg", "-v", "error", "-y", "-i", str(path),
        "-vf", f"fps={sample_fps},scale={width}:-2",
        "-q:v", "3", str(out_dir / "f%05d.jpg"),
    ]
    pr = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if pr.returncode != 0:
        raise RuntimeError(f"frame extraction failed: {pr.stderr.strip()[:200]}")
    return len(list(out_dir.glob("f*.jpg")))


def screen_video(
    path: str | Path,
    sample_fps: float = DEFAULT_SAMPLE_FPS,
    threshold: float = DEFAULT_THRESHOLD,
) -> dict[str, Any]:
    """Detect explicit frames in a video. Never raises for detector problems."""
    path = Path(path)
    started = time.time()
    info = {"available": False, "safe": True, "source": str(path), "frames_scanned": 0,
            "max_score": 0.0, "ranges": [], "hits": [], "model": "nudenet", "error": ""}

    detector = _get_detector()
    if detector is None:
        info["error"] = _DETECTOR_ERROR
        return info

    try:
        meta = _probe(path)
    except Exception as exc:
        info["error"] = str(exc)
        return info

    if meta["width"] <= 0 or meta["height"] <= 0:
        info["error"] = "no video stream"
        return info

    with tempfile.TemporaryDirectory(prefix="nsfw-") as tmp:
        tmp_dir = Path(tmp)
        try:
            count = _extract_frames(path, tmp_dir, sample_fps)
        except Exception as exc:
            info["error"] = str(exc)
            return info

        frames = sorted(tmp_dir.glob("f*.jpg"))
        sx = meta["width"] / 640.0
        hits: list[dict[str, Any]] = []
        for frame in frames:
            idx = int(frame.stem[1:])
            t = (idx - 1) / sample_fps
            try:
                detections = detector.detect(str(frame))
            except Exception as exc:  # model error mid-run: fail closed
                info["error"] = f"detection failed at frame {idx}: {exc}"
                info["available"] = True
                info["safe"] = False
                return info
            for det in detections or []:
                label = str(det.get("class") or "")
                score = float(det.get("score") or 0.0)
                if label not in DETECT_CLASSES or score < threshold:
                    continue
                box = det.get("box") or [0, 0, 0, 0]
                # nudenet returns [x, y, w, h] in the sampled frame space
                fx, fy, fw, fh = [float(v) for v in box[:4]]
                x, y = fx * sx, fy * sx
                w, h = fw * sx, fh * sx
                x = max(0.0, min(x, meta["width"] - 1))
                y = max(0.0, min(y, meta["height"] - 1))
                w = max(1.0, min(w, meta["width"] - x))
                h = max(1.0, min(h, meta["height"] - y))
                hits.append({"t": round(t, 2), "label": label, "score": round(score, 3),
                             "box": [round(x, 1), round(y, 1), round(w, 1), round(h, 1)]})

        info["available"] = True
        info["frames_scanned"] = count
        info["hits"] = hits
        if not hits:
            info["elapsed_sec"] = round(time.time() - started, 2)
            return info

        info["safe"] = False
        info["max_score"] = max(h["score"] for h in hits)
        info["ranges"] = _merge_ranges(hits, sample_fps, meta["width"], meta["height"])
        info["elapsed_sec"] = round(time.time() - started, 2)
        return info


def _merge_ranges(hits: list[dict[str, Any]], sample_fps: float, width: int, height: int) -> list[dict[str, Any]]:
    step = 1.0 / sample_fps
    gap = step * 1.6
    ranges: list[dict[str, Any]] = []
    for hit in sorted(hits, key=lambda h: h["t"]):
        if ranges and hit["t"] - ranges[-1]["_last"] <= gap:
            cur = ranges[-1]
            cur["end"] = round(hit["t"] + step + 0.3, 2)
            cur["_last"] = hit["t"]
            cur["labels"].add(hit["label"])
            cur["max_score"] = max(cur["max_score"], hit["score"])
            cur["box"] = _union(cur["box"], hit["box"])
        else:
            ranges.append({
                "start": round(max(0.0, hit["t"] - 0.3), 2),
                "end": round(hit["t"] + step + 0.3, 2),
                "_last": hit["t"],
                "labels": {hit["label"]},
                "max_score": hit["score"],
                "box": list(hit["box"]),
            })

    out: list[dict[str, Any]] = []
    for r in ranges:
        box = _pad(r["box"], width, height, 0.10)
        area_ratio = (box[2] * box[3]) / float(width * height)
        out.append({
            "start": r["start"],
            "end": r["end"],
            "labels": sorted(r["labels"]),
            "max_score": round(r["max_score"], 3),
            "box": [round(v, 1) for v in box],
            "full_frame": area_ratio > 0.55,
        })
    return out


def _union(a: list[float], b: list[float]) -> list[float]:
    x1 = min(a[0], b[0]); y1 = min(a[1], b[1])
    x2 = max(a[0] + a[2], b[0] + b[2]); y2 = max(a[1] + a[3], b[1] + b[3])
    return [x1, y1, x2 - x1, y2 - y1]


def _pad(box: list[float], width: int, height: int, pad: float) -> list[float]:
    x, y, w, h = box
    px, py = w * pad, h * pad
    x1 = max(0.0, x - px); y1 = max(0.0, y - py)
    x2 = min(float(width), x + w + px); y2 = min(float(height), y + h + py)
    return [x1, y1, max(2.0, x2 - x1), max(2.0, y2 - y1)]


def censor_video(src: str | Path, dst: str | Path, ranges: list[dict[str, Any]],
                 blur: int = DEFAULT_BLUR) -> dict[str, Any]:
    """Blur each flagged range in `src` and write the result to `dst`."""
    src, dst = Path(src), Path(dst)
    if not ranges:
        shutil.copy2(src, dst)
        return {"ok": True, "path": str(dst), "regions": 0}

    meta = _probe(src)
    width, height = meta["width"], meta["height"]
    chains: list[str] = []
    prev = "0:v"
    for i, r in enumerate(ranges):
        start, end = float(r["start"]), float(r["end"])
        if end <= start:
            continue
        if r.get("full_frame"):
            chains.append(f"[{prev}]split[base{i}][tmp{i}]")
            chains.append(f"[tmp{i}]boxblur={blur}:2[bf{i}]")
            chains.append(f"[base{i}][bf{i}]overlay=0:0:enable='between(t,{start:.2f},{end:.2f})'[v{i}]")
            prev = f"v{i}"
            continue

        x, y, w, h = r["box"]
        x, y = int(x) // 2 * 2, int(y) // 2 * 2
        w, h = int(w) // 2 * 2, int(h) // 2 * 2
        w = max(2, min(w, width - x))
        h = max(2, min(h, height - y))
        chains.append(f"[{prev}]crop={w}:{h}:{x}:{y},boxblur={blur}:2[b{i}]")
        chains.append(f"[{prev}][b{i}]overlay={x}:{y}:enable='between(t,{start:.2f},{end:.2f})'[v{i}]")
        prev = f"v{i}"

    if not chains:
        shutil.copy2(src, dst)
        return {"ok": True, "path": str(dst), "regions": 0}

    cmd = [
        "ffmpeg", "-v", "error", "-y", "-i", str(src),
        "-filter_complex", ";".join(chains),
        "-map", f"[{prev}]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "copy", "-movflags", "+faststart", str(dst),
    ]
    pr = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if pr.returncode != 0:
        return {"ok": False, "path": str(dst), "regions": len(ranges),
                "error": pr.stderr.strip()[-300:]}
    try:
        out_meta = _probe(dst)
        if meta["duration"] and abs(out_meta["duration"] - meta["duration"]) > 1.5:
            return {"ok": False, "path": str(dst), "regions": len(ranges),
                    "error": f"duration drift {meta['duration']:.1f}s -> {out_meta['duration']:.1f}s"}
    except Exception as exc:
        return {"ok": False, "path": str(dst), "regions": len(ranges), "error": str(exc)}
    return {"ok": True, "path": str(dst), "regions": len(ranges), "bytes": dst.stat().st_size}


def ensure_upload_safe(folder: str | Path, video_path: str | Path) -> dict[str, Any]:
    """
    Upload gate. Returns:
      upload_ok        bool  — may this file go to YouTube?
      video_path       str   — file to upload (censored copy when needed)
      censored_path    str|None
      reason           str   — human-readable blocker when upload_ok is False
    Caches the verdict in `<folder>/content_safety.json`.
    """
    folder, video_path = Path(folder), Path(video_path)
    try:
        st = video_path.stat()
    except OSError as exc:
        return {"upload_ok": False, "video_path": str(video_path), "reason": f"missing video: {exc}"}

    signature = {"file": video_path.name, "size": st.st_size, "mtime": round(st.st_mtime, 1)}
    cache_path = folder / SAFETY_FILE
    cached: dict[str, Any] | None = None
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            cached = None

    if cached and cached.get("signature") == signature:
        censored = cached.get("censored_path")
        video_ok = (not cached.get("censored")) or (censored and Path(censored).exists())
        return {
            "upload_ok": bool(cached.get("upload_ok")) and bool(video_ok),
            "video_path": censored if cached.get("censored") and video_ok else str(video_path),
            "censored_path": censored,
            "reason": cached.get("reason", ""),
            "safe": cached.get("safe"),
            "cached": True,
        }

    scan = screen_video(video_path)
    result: dict[str, Any] = {
        "signature": signature,
        "source": str(video_path),
        "safe": scan["safe"],
        "available": scan["available"],
        "ranges": scan["ranges"],
        "max_score": scan["max_score"],
        "frames_scanned": scan["frames_scanned"],
        "model": scan["model"],
        "scanned_at": round(time.time(), 1),
        "censored": False,
        "censored_path": None,
        "upload_ok": False,
        "reason": "",
    }

    if not scan["available"]:
        result["reason"] = f"content safety scan unavailable: {scan['error']}"
    elif scan.get("error"):
        result["reason"] = f"content safety scan failed: {scan['error']}"
    elif scan["safe"]:
        result["upload_ok"] = True
    else:
        out = video_path.with_name(f"{video_path.stem}_censored.mp4")
        censor = censor_video(video_path, out, scan["ranges"])
        result["censor_result"] = censor
        if censor.get("ok"):
            result["censored"] = True
            result["censored_path"] = str(out)
            result["upload_ok"] = True
            result["reason"] = (
                f"explicit content detected ({len(scan['ranges'])} range(s), max score "
                f"{scan['max_score']:.2f}); upload uses the blurred copy"
            )
        else:
            result["reason"] = f"explicit content detected and blur failed: {censor.get('error')}"

    try:
        cache_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    except Exception:
        pass

    return {
        "upload_ok": result["upload_ok"],
        "video_path": result["censored_path"] or str(video_path),
        "censored_path": result["censored_path"],
        "reason": result["reason"],
        "safe": result["safe"],
        "cached": False,
    }


def _iter_videos(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    return sorted(p for p in target.rglob("*.mp4") if "_censored" not in p.stem)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Screen clips for explicit content and blur it.")
    parser.add_argument("target", help="video file, clip directory, or exports directory")
    parser.add_argument("--censor", action="store_true", help="write *_censored.mp4 for flagged videos")
    parser.add_argument("--fps", type=float, default=DEFAULT_SAMPLE_FPS)
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    args = parser.parse_args(argv)

    target = Path(args.target)
    if not target.exists():
        print(f"not found: {target}", file=sys.stderr)
        return 2

    videos = _iter_videos(target)
    report: list[dict[str, Any]] = []
    flagged = 0
    for video in videos:
        scan = screen_video(video, sample_fps=args.fps, threshold=args.threshold)
        row: dict[str, Any] = {
            "video": str(video),
            "safe": scan["safe"],
            "available": scan["available"],
            "frames": scan["frames_scanned"],
            "max_score": scan["max_score"],
            "ranges": len(scan["ranges"]),
        }
        if scan.get("error"):
            row["error"] = scan["error"]
        if not scan["safe"] and args.censor and scan["available"]:
            out = video.with_name(f"{video.stem}_censored.mp4")
            row["censor"] = censor_video(video, out, scan["ranges"])
        if not scan["safe"]:
            flagged += 1
        report.append(row)

    print(json.dumps({"scanned": len(videos), "flagged": flagged, "results": report}, indent=2))
    return 0 if not flagged else 1


if __name__ == "__main__":
    raise SystemExit(main())
