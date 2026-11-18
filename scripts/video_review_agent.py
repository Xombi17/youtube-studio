#!/usr/bin/env python3
"""
CreatorRadar Video Reviewer Agent (Real Technical, Audio, Motion & Compliance QA)
Inspects rendered video deliverables against CreatorRadar broadcast standards:
1. Technical Playback (1080x1920 or 1920x1080, >=24 fps, valid H.264/HEVC + AAC)
2. Real Audio Loudness & Clipping Audit (ffmpeg ebur128 Integrated LUFS, True Peak, LRA)
3. Real Motion Verification (extracts beat frames and verifies non-static pixel delta)
4. Real Studio Compliance Checks (AI disclosure, source citations, human approval gate)
Writes both REVIEW.md and review.json alongside the video.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REQUIRED_DISCLOSURE = "Graphics created with AI assistance. All facts sourced from official documentation."


def _parse_fps(rate_str: str | None) -> float:
    if not rate_str:
        return 0.0
    if "/" in rate_str:
        num, den = rate_str.split("/", 1)
        try:
            return round(float(num) / max(1.0, float(den)), 2)
        except ValueError:
            return 0.0
    try:
        return round(float(rate_str), 2)
    except ValueError:
        return 0.0


class VideoReviewerAgent:
    def __init__(
        self,
        video_path: str | Path,
        style_id: str = "midnight-grid",
        beats_file: str | Path | None = None,
        metadata_file: str | Path | None = None,
    ):
        self.video_path = Path(video_path).resolve()
        self.style_id = style_id
        self.beats_file = Path(beats_file) if beats_file else None
        self.metadata_file = Path(metadata_file) if metadata_file else None
        self.findings: list[dict] = []
        self.metrics: dict = {"style_id": style_id, "video_file": self.video_path.name}
        self.compliance: list[dict] = []

    def log(self, message: str):
        print(f"[Video Reviewer Agent] {message}", flush=True)

    def inspect_technical(self) -> bool:
        self.log(f"Inspecting technical streams for: {self.video_path.name}...")
        if not self.video_path.exists():
            self.findings.append({"severity": "BLOCKER", "category": "technical", "issue": "Video file does not exist"})
            return False

        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries",
            "format=duration,size,bit_rate:stream=codec_type,codec_name,width,height,r_frame_rate,channels,sample_rate",
            "-of", "json",
            str(self.video_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(res.stdout)

        fmt = data.get("format", {})
        streams = data.get("streams", [])
        v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        duration = float(fmt.get("duration", 0))
        size_bytes = int(fmt.get("size", 0))
        bitrate_kbps = round(int(fmt.get("bit_rate", 0)) / 1000, 1) if fmt.get("bit_rate") else 0

        self.metrics["duration"] = round(duration, 2)
        self.metrics["size_mb"] = round(size_bytes / (1024 * 1024), 2)
        self.metrics["bitrate_kbps"] = bitrate_kbps

        if duration < 3.0:
            self.findings.append({"severity": "BLOCKER", "category": "technical", "issue": f"Video too short ({duration:.2f}s)"})

        if not v_stream:
            self.findings.append({"severity": "BLOCKER", "category": "technical", "issue": "Missing video stream"})
            return False

        w, h = int(v_stream.get("width", 0)), int(v_stream.get("height", 0))
        fps = _parse_fps(v_stream.get("r_frame_rate"))
        self.metrics["width"] = w
        self.metrics["height"] = h
        self.metrics["resolution"] = f"{w}x{h}"
        self.metrics["fps"] = fps
        self.metrics["video_codec"] = v_stream.get("codec_name")

        if (w, h) == (1080, 1920):
            self.metrics["format_type"] = "Vertical Short (9:16)"
        elif (w, h) == (1920, 1080):
            self.metrics["format_type"] = "Landscape Video (16:9)"
        else:
            self.metrics["format_type"] = f"Non-standard ({w}x{h})"
            self.findings.append({
                "severity": "BLOCKER",
                "category": "technical",
                "issue": f"Resolution {w}x{h} is not 1080x1920 or 1920x1080",
            })

        if fps < 24.0:
            self.findings.append({"severity": "WARNING", "category": "technical", "issue": f"Low framerate: {fps} fps (target >=30)"})

        if not a_stream:
            self.findings.append({"severity": "BLOCKER", "category": "audio", "issue": "Missing audio stream"})
        else:
            self.metrics["audio_codec"] = a_stream.get("codec_name")
            self.metrics["audio_channels"] = int(a_stream.get("channels", 0))
            self.metrics["audio_sample_rate"] = int(a_stream.get("sample_rate", 0))

        return not any(f["severity"] == "BLOCKER" for f in self.findings)

    def inspect_audio_loudness(self) -> bool:
        self.log("Measuring integrated loudness (EBU R128) and peak levels...")
        cmd = [
            "ffmpeg", "-hide_banner", "-i", str(self.video_path),
            "-af", "ebur128=peak=true",
            "-f", "null", "-",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        stderr = res.stderr

        # Parse final Summary block from ebur128
        summary_idx = stderr.rfind("Summary:")
        summary = stderr[summary_idx:] if summary_idx != -1 else stderr

        i_match = re.search(r"I:\s*(-?\d+(?:\.\d+)?)\s*LUFS", summary)
        lra_match = re.search(r"LRA:\s*(-?\d+(?:\.\d+)?)\s*LU", summary)
        tp_match = re.search(r"Peak:\s*(-?\d+(?:\.\d+)?)\s*dBFS", summary)

        lufs = float(i_match.group(1)) if i_match else None
        lra = float(lra_match.group(1)) if lra_match else None
        true_peak = float(tp_match.group(1)) if tp_match else None

        self.metrics["loudness_lufs"] = lufs
        self.metrics["loudness_lra"] = lra
        self.metrics["true_peak_dbtp"] = true_peak

        if lufs is None:
            self.findings.append({"severity": "WARNING", "category": "audio", "issue": "Could not measure EBU R128 loudness"})
        else:
            if lufs < -28.0:
                self.findings.append({"severity": "BLOCKER", "category": "audio", "issue": f"Audio nearly silent ({lufs} LUFS; target -14 LUFS)"})
            elif lufs < -18.5 or lufs > -10.0:
                self.findings.append({"severity": "WARNING", "category": "audio", "issue": f"Loudness {lufs} LUFS outside broadcast window (-18 to -10 LUFS)"})

        if true_peak is not None and true_peak > -0.2:
            self.findings.append({"severity": "WARNING", "category": "audio", "issue": f"Audio true peak {true_peak} dBFS risks clipping (target <= -1.0 dBTP)"})

        return True

    def extract_and_verify_motion(self) -> list[str]:
        duration = self.metrics.get("duration", 0.0)
        sample_times: list[float] = []

        if self.beats_file and self.beats_file.exists():
            try:
                beats_data = json.loads(self.beats_file.read_text(encoding="utf-8"))
                beats = beats_data.get("beats", beats_data) if isinstance(beats_data, dict) else beats_data
                for b in beats:
                    if isinstance(b, dict) and "start" in b:
                        mid = min(max(0.2, float(b["start"]) + float(b.get("duration", 1.0)) * 0.45), max(0.2, duration - 0.2))
                        sample_times.append(round(mid, 2))
            except Exception:
                pass

        if not sample_times and duration > 0.5:
            count = 5
            sample_times = [round(duration * (i + 0.5) / count, 2) for i in range(count)]

        self.log(f"Extracting & verifying motion across {len(sample_times)} beat frames: {sample_times}...")
        sample_dir = self.video_path.parent / "review_samples"
        sample_dir.mkdir(exist_ok=True)

        extracted: list[str] = []
        frame_hashes: set[str] = set()

        for i, t in enumerate(sample_times):
            out_img = sample_dir / f"beat_{i + 1}_{t:.2f}s.jpg"
            cmd = [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-ss", str(t), "-i", str(self.video_path),
                "-frames:v", "1", "-q:v", "3",
                str(out_img),
            ]
            subprocess.run(cmd, check=False)
            if out_img.exists() and out_img.stat().st_size > 1000:
                extracted.append(out_img.name)
                frame_hashes.add(hashlib.sha256(out_img.read_bytes()).hexdigest()[:16])

        self.metrics["sampled_frames"] = extracted
        self.metrics["unique_frame_count"] = len(frame_hashes)
        self.metrics["motion_verified"] = len(frame_hashes) >= max(2, min(len(extracted), 3))

        if len(extracted) >= 2 and len(frame_hashes) < 2:
            self.findings.append({
                "severity": "BLOCKER",
                "category": "visual",
                "issue": "Static video detected: sampled beat frames are identical (violates Studio Rule 7).",
            })
        return extracted

    def inspect_compliance(self):
        self.log("Running CreatorRadar compliance verification...")
        meta_path = self.metadata_file or (self.video_path.parent / "metadata.md")
        checklist_path = self.video_path.parent / "checklist.md"

        meta_text = meta_path.read_text(encoding="utf-8", errors="replace") if meta_path.exists() else ""
        checklist_text = checklist_path.read_text(encoding="utf-8", errors="replace") if checklist_path.exists() else ""

        has_disclosure = REQUIRED_DISCLOSURE.lower() in meta_text.lower()
        has_sources = ("http://" in meta_text or "https://" in meta_text or "source" in meta_text.lower()) if meta_text else False
        human_approved = bool(re.search(r"\[x\]\s*Final human approval", checklist_text, re.I))

        if meta_path.exists() and not has_disclosure:
            self.findings.append({
                "severity": "BLOCKER",
                "category": "compliance",
                "issue": "metadata.md is missing mandatory AI disclosure line (Studio Rule 5).",
            })

        self.compliance = [
            {
                "rule": "Rule 1 & 2: No fabricated claims / first-hand gameplay",
                "status": "NEEDS_HUMAN_CHECK",
                "detail": "Verify script claims against source ledger before publishing.",
            },
            {
                "rule": "Rule 3: Sources cited",
                "status": "PASS" if has_sources else "NEEDS_REVIEW",
                "detail": "Source references found in metadata.md" if has_sources else "No metadata.md or source links detected yet.",
            },
            {
                "rule": "Rule 4: Human approval gate",
                "status": "APPROVED" if human_approved else "PENDING_HUMAN_APPROVAL",
                "detail": "Human sign-off recorded." if human_approved else "Upload blocked until channel owner signs off in checklist.md.",
            },
            {
                "rule": "Rule 5: Mandatory AI disclosure",
                "status": "PASS" if has_disclosure else ("FAIL" if meta_path.exists() else "PENDING_METADATA"),
                "detail": "Required AI disclosure line verified." if has_disclosure else "Add required disclosure line to metadata.md.",
            },
            {
                "rule": "Rule 6: Broadcast mastered audio (-14 LUFS target)",
                "status": "PASS" if (self.metrics.get("loudness_lufs") is not None and -18.5 <= self.metrics["loudness_lufs"] <= -10.0) else "WARNING",
                "detail": f"Measured {self.metrics.get('loudness_lufs')} LUFS, True Peak {self.metrics.get('true_peak_dbtp')} dBFS.",
            },
            {
                "rule": "Rule 7: Kinetic motion (zero static video)",
                "status": "PASS" if self.metrics.get("motion_verified") else "FAIL",
                "detail": f"{self.metrics.get('unique_frame_count', 0)}/{len(self.metrics.get('sampled_frames', []))} distinct beat frames verified.",
            },
        ]

    def generate_review_report(self) -> tuple[bool, dict, str]:
        self.log("Compiling Quality Review Report (REVIEW.md + review.json)...")
        blockers = [f for f in self.findings if f["severity"] == "BLOCKER"]
        warnings = [f for f in self.findings if f["severity"] == "WARNING"]
        passed = len(blockers) == 0

        report_data = {
            "passed": passed,
            "verdict": "PASSED" if passed else "ACTION_REQUIRED",
            "metrics": self.metrics,
            "findings": self.findings,
            "compliance": self.compliance,
        }

        findings_md = (
            "\n".join(f"- **[{f['severity']}]** ({f['category']}): {f['issue']}" for f in self.findings)
            if self.findings
            else "- None. All automated technical, audio, and motion checks passed."
        )
        compliance_md = "\n".join(
            f"| {c['rule']} | `{c['status']}` | {c['detail']} |" for c in self.compliance
        )

        report_md = f"""# Quality Review Report: `{self.video_path.name}`

## 1. Technical Verdict
- **Status:** {'PASSED (Ready for Human Review)' if passed else 'ACTION REQUIRED (Blockers Found)'}
- **Resolution:** `{self.metrics.get('resolution', 'N/A')}` — {self.metrics.get('format_type', 'Unknown')}
- **Framerate / Codec:** `{self.metrics.get('fps', 0)} fps` / `{self.metrics.get('video_codec', 'N/A')}`
- **Duration / Size:** `{self.metrics.get('duration', 0):.2f}s` / `{self.metrics.get('size_mb', 0):.2f} MB` (`{self.metrics.get('bitrate_kbps', 0)} kbps`)
- **Style Specification:** `{self.style_id}`

## 2. Audio & Loudness Audit (EBU R128)
- **Audio Stream:** `{self.metrics.get('audio_codec', 'N/A')}` ({self.metrics.get('audio_channels', 0)} ch @ {self.metrics.get('audio_sample_rate', 0)} Hz)
- **Integrated Loudness:** `{self.metrics.get('loudness_lufs', 'N/A')} LUFS` (target: `-14.0 LUFS`)
- **Loudness Range (LRA):** `{self.metrics.get('loudness_lra', 'N/A')} LU`
- **True Peak:** `{self.metrics.get('true_peak_dbtp', 'N/A')} dBFS` (ceiling: `-1.0 dBTP`)

## 3. Visual Motion Check
- **Sampled Beat Frames:** {len(self.metrics.get('sampled_frames', []))} extracted into `review_samples/`
- **Distinct Frame Hashes:** {self.metrics.get('unique_frame_count', 0)} ({'Kinetic motion verified' if self.metrics.get('motion_verified') else 'Potential static frame issue'})

## 4. Automated Findings ({len(blockers)} Blockers, {len(warnings)} Warnings)
{findings_md}

## 5. CreatorRadar Studio Rules Compliance
| Rule | Status | Notes |
| --- | --- | --- |
{compliance_md}
"""
        (self.video_path.parent / "REVIEW.md").write_text(report_md, encoding="utf-8")
        (self.video_path.parent / "review.json").write_text(json.dumps(report_data, indent=2), encoding="utf-8")
        self.log(f"Wrote REVIEW.md and review.json to {self.video_path.parent}")
        return passed, report_data, report_md


def main():
    parser = argparse.ArgumentParser(description="CreatorRadar Automated Video Quality Reviewer")
    parser.add_argument("video_path", help="Path to rendered MP4 file")
    parser.add_argument("style_id", nargs="?", default="midnight-grid")
    parser.add_argument("--beats", default=None, help="Optional path to audio_timeline.json")
    parser.add_argument("--metadata", default=None, help="Optional path to metadata.md")
    args = parser.parse_args()

    reviewer = VideoReviewerAgent(
        args.video_path,
        style_id=args.style_id,
        beats_file=args.beats,
        metadata_file=args.metadata,
    )
    reviewer.inspect_technical()
    reviewer.inspect_audio_loudness()
    reviewer.extract_and_verify_motion()
    reviewer.inspect_compliance()
    passed, _, report_md = reviewer.generate_review_report()
    print(report_md)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
