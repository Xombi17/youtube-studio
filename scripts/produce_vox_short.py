#!/usr/bin/env python3
"""
CreatorRadar Vox Paper-Collage Production Runner
Orchestrates:
1. Per-beat zero-shot voice cloning via Chatterbox-Turbo (RTX 4060 CUDA)
2. 3-stem broadcast audio mix (Cloned Narration + Custom TangoFlux SFX + Ducked Editorial Music Bed) -> -14 LUFS
3. Living Vox paper-collage HTML5/GSAP scene assembly synced to exact beat timestamps
4. Deterministic 1080x1920 @ 30fps NVENC GPU render + muxing + metadata/checklist + automated QA review
"""

import argparse
import datetime
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = WORKSPACE_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from build_vox_collage import build_vox_scene  # noqa: E402
from render_scene import render_scene  # noqa: E402
from video_review_agent import REQUIRED_DISCLOSURE, VideoReviewerAgent  # noqa: E402

CHATTERBOX_PY = WORKSPACE_ROOT / "external" / "chatterbox" / ".venv" / "bin" / "python"
CREATOR_SAMPLE = WORKSPACE_ROOT / "assets" / "voices" / "creator_sample.wav"

VOCAL_EQ = (
    "highpass=f=75,"
    "equalizer=f=120:width_type=o:width=1.0:g=2.5,"
    "equalizer=f=350:width_type=o:width=1.5:g=-2.0,"
    "equalizer=f=4500:width_type=o:width=1.2:g=3.0,"
    "acompressor=threshold=-18dB:ratio=3.5:attack=15:release=100,"
    "silenceremove=start_periods=1:start_silence=0.04:start_threshold=-42dB,"
    "areverse,silenceremove=start_periods=1:start_silence=0.05:start_threshold=-42dB,areverse,"
    "loudnorm=I=-15:LRA=6:TP=-1.5"
)


def probe_duration(path: Path) -> float:
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(res.stdout.strip())


def synthesize_beats_chatterbox(beats: list[dict], audio_dir: Path, ref_wav: Path, mode: str = "turbo") -> list[dict]:
    """Run one persistent Chatterbox CUDA process so the model loads once for all beats."""
    audio_dir.mkdir(parents=True, exist_ok=True)
    jobs = [
        {"id": b["id"], "text": b["text"], "raw_out": str(audio_dir / f"{b['id']}_raw.wav")}
        for b in beats
    ]
    jobs_file = audio_dir / "chatterbox_jobs.json"
    jobs_file.write_text(json.dumps(jobs, indent=2), encoding="utf-8")

    runner_code = f"""
import json, torch, torchaudio as ta
jobs = json.loads(open({str(jobs_file)!r}).read())
device = 'cuda' if torch.cuda.is_available() else 'cpu'
print(f'[Chatterbox] Loading {mode} model on {{device}}...', flush=True)
if {mode!r} == 'turbo':
    from chatterbox.tts_turbo import ChatterboxTurboTTS
    model = ChatterboxTurboTTS.from_pretrained(device=device)
else:
    from chatterbox.tts import ChatterboxTTS
    model = ChatterboxTTS.from_pretrained(device=device)
ref = {str(ref_wav)!r}
for j in jobs:
    print(f"[Chatterbox] Synthesizing {{j['id']}}: {{j['text'][:60]}}...", flush=True)
    wav = model.generate(j['text'], audio_prompt_path=ref)
    ta.save(j['raw_out'], wav.cpu(), model.sr)
    print(f"[Chatterbox] Saved {{j['raw_out']}}", flush=True)
"""
    subprocess.run([str(CHATTERBOX_PY), "-c", runner_code], check=True)

    # Master each beat vocal clip & measure exact tight duration
    timed: list[dict] = []
    cursor = 0.25
    gap = 0.24
    for b in beats:
        raw_p = audio_dir / f"{b['id']}_raw.wav"
        clean_p = audio_dir / f"{b['id']}_clean.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw_p), "-af", VOCAL_EQ, "-ar", "48000", "-ac", "2", str(clean_p)],
            check=True,
        )
        dur = probe_duration(clean_p)
        entry = dict(b)
        entry["clip_path"] = str(clean_p)
        entry["start"] = round(cursor, 3)
        entry["end"] = round(cursor + dur, 3)
        entry["duration"] = round(dur, 3)
        timed.append(entry)
        cursor = entry["end"] + gap

    return timed


def mix_three_stem_master(
    timed_beats: list[dict],
    audio_dir: Path,
    music_bed: Path | None,
    master_wav: Path,
) -> float:
    total_duration = round(timed_beats[-1]["end"] + 0.75, 3)
    inputs: list[str] = []
    filters: list[str] = []
    voice_labels: list[str] = []
    sfx_labels: list[str] = []
    idx = 0

    for i, b in enumerate(timed_beats):
        inputs.extend(["-i", b["clip_path"]])
        delay_ms = int(round(b["start"] * 1000))
        filters.append(f"[{idx}:a]adelay={delay_ms}|{delay_ms}[v{i}];")
        voice_labels.append(f"[v{i}]")
        idx += 1

        sfx_name = b.get("sfx")
        if sfx_name:
            sfx_path = audio_dir / sfx_name
            if not sfx_path.exists():
                sfx_path = WORKSPACE_ROOT / "assets" / "sfx" / sfx_name
            if sfx_path.exists():
                sfx_ms = int(round(max(0.0, b["start"] - 0.05) * 1000))
                inputs.extend(["-i", str(sfx_path)])
                # Trim leading silence on generated SFX and mix cleanly at -11 dB
                filters.append(
                    f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,"
                    f"silenceremove=start_periods=1:start_silence=0.02:start_threshold=-38dB,"
                    f"atrim=0:1.1,afade=t=out:st=0.75:d=0.35,volume=-11dB,adelay={sfx_ms}|{sfx_ms}[s{i}];"
                )
                sfx_labels.append(f"[s{i}]")
                idx += 1

    # Base silence + Narration bus + SFX bus
    filters.append(f"aevalsrc=0:d={total_duration}:s=48000:c=stereo[base];")
    all_fg = "[base]" + "".join(voice_labels) + "".join(sfx_labels)
    fg_n = 1 + len(voice_labels) + len(sfx_labels)
    filters.append(f"{all_fg}amix=inputs={fg_n}:duration=first:dropout_transition=0:normalize=0[fg];")

    if music_bed and music_bed.exists():
        inputs.extend(["-stream_loop", "-1", "-i", str(music_bed)])
        fade_out_st = max(0.5, total_duration - 1.2)
        filters.append(
            f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,"
            f"atrim=0:{total_duration},highpass=f=70,lowpass=f=6000,"
            f"afade=t=in:st=0:d=0.6,afade=t=out:st={fade_out_st:.2f}:d=1.1,volume=-18dB[bgm];"
        )
        filters.append("[fg][bgm]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.92,loudnorm=I=-14:LRA=7:TP=-1.5[out]")
    else:
        filters.append("[fg]alimiter=limit=0.92,loudnorm=I=-14:LRA=7:TP=-1.5[out]")

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        *inputs,
        "-filter_complex", "".join(filters),
        "-map", "[out]",
        "-ar", "48000", "-ac", "2",
        str(master_wav),
    ]
    subprocess.run(cmd, check=True)
    return probe_duration(master_wav)


def main():
    parser = argparse.ArgumentParser(description="Produce a complete Vox Paper-Collage Short")
    parser.add_argument("--slug", default="gta-flu-economics")
    parser.add_argument("--title", default='The Economics of the "GTA Flu"')
    parser.add_argument("--mode", choices=["turbo", "standard"], default="turbo")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--quality", choices=["draft", "standard", "high"], default="high")
    args = parser.parse_args()

    render_dir = WORKSPACE_ROOT / "renders" / args.slug
    export_dir = WORKSPACE_ROOT / "exports" / args.slug
    audio_dir = render_dir / "audio"
    export_dir.mkdir(parents=True, exist_ok=True)

    beats = json.loads((render_dir / "beats.json").read_text(encoding="utf-8"))
    print(f"=== Producing Vox Paper-Collage Short: {args.title} ({len(beats)} beats) ===", flush=True)

    # 1. Voice Cloning (Chatterbox-Turbo on CUDA)
    timed_beats = synthesize_beats_chatterbox(beats, audio_dir, CREATOR_SAMPLE, mode=args.mode)

    # 2. 3-Stem Broadcast Mix (Cloned Voice + TangoFlux SFX + Ducked Editorial Music Bed)
    music_bed = WORKSPACE_ROOT / "assets" / "music" / "vox_editorial_bed.wav"
    master_wav = render_dir / "narration_master.wav"
    total_duration = mix_three_stem_master(timed_beats, audio_dir, music_bed, master_wav)
    print(f"[Audio] 3-stem master rendered ({total_duration:.2f}s) -> {master_wav}", flush=True)

    timeline_json = render_dir / "audio_timeline.json"
    timeline_json.write_text(json.dumps({
        "audio_path": str(master_wav),
        "duration": round(total_duration, 3),
        "engines": [f"chatterbox-{args.mode} (cloned: creator_sample.wav)", "tangoflux-sfx", "vox-editorial-bed"],
        "beats": timed_beats,
    }, indent=2), encoding="utf-8")

    # Save script.md for dashboard inspection
    script_md = f"# {args.title} — Vox Paper-Collage Script\n\n" + "\n\n".join(
        f"## {b['kicker']} — {b['headline']}\n{b['text']}" for b in timed_beats
    ) + "\n\n## Sources\n- Rockstar Games Official — https://www.rockstargames.com/VI\n- BambooHR / The Guardian / Forbes (Nov 2026 GTA Flu coverage)\n"
    (render_dir / "script.md").write_text(script_md, encoding="utf-8")

    # 3. Build Living Vox Paper-Collage Scene
    scene_dir = build_vox_scene(
        project_dir=render_dir,
        timed_beats=timed_beats,
        total_duration=total_duration,
        title=args.title,
        width=1080,
        height=1920,
    )
    print(f"[Scene] Authored Vox paper-collage HTML5/GSAP scene at {scene_dir / 'index.html'}", flush=True)

    # 4. Deterministic Render via Chrome + NVENC
    raw_mp4 = render_dir / "visual_raw.mp4"
    render_stats = render_scene(
        project_path=scene_dir,
        output_path=raw_mp4,
        fps=args.fps,
        quality=args.quality,
        codec="auto",
        width_override=1080,
        height_override=1920,
        duration_override=total_duration,
    )

    # 5. Final Mux & Export
    date_tag = datetime.date.today().strftime("%Y%m%d")
    export_mp4 = export_dir / f"{date_tag}-{args.slug}-vox-collage.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(raw_mp4),
            "-i", str(master_wav),
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            "-shortest",
            str(export_mp4),
        ],
        check=True,
    )
    print(f"[Export] Master video saved -> {export_mp4}", flush=True)

    # 6. Metadata + Human-Approval Checklist (Rules 4 & 5)
    chapters = "\n".join(
        f"{int(b['start'] // 60):02d}:{int(b['start'] % 60):02d} — {b['headline']}"
        for b in timed_beats
    )
    metadata_md = f"""# YouTube Metadata — {args.title}

## Title Options
1. `The $1 Billion "GTA Flu" Explained`
2. `Why Companies Are Giving Workers a Paid Day Off for GTA VI`

## Description
Tomorrow is November 19, 2026—and economists and HR platforms are tracking a massive "GTA Flu" wave of PTO requests and sick-day projections ahead of the GTA VI console launch. Here is the real economics behind the $1B productivity estimate vs. $4.5B week-one sales forecast.

#Shorts #GTAVI #Economics #VoxStyle #CreatorRadar

### Chapters
{chapters}

### Sources
- Rockstar Games Official (Launch Date & Platforms): https://www.rockstargames.com/VI
- BambooHR PTO Data & Guardian / Forbes Coverage (Nov 2026): https://www.bamboohr.com
- Pompeu Fabra University Productivity Estimate & Logitech "Logi Game Day" Reporting (Nov 2026)

---
{REQUIRED_DISCLOSURE}
"""
    metadata_file = export_dir / "metadata.md"
    metadata_file.write_text(metadata_md, encoding="utf-8")

    checklist_md = f"""# Pre-Upload Human Approval Checklist — {args.title}

- **Export File:** `{export_mp4.name}`
- **Style:** `vox-paper-collage` (AI-generated risograph cutouts + 12fps stop-motion GSAP)
- **Audio:** Chatterbox-Turbo (creator voice clone) + TangoFlux SFX + Editorial Music Bed (-14 LUFS)

## Required Gates (Rule 4 — Human Sign-off Required)
- [ ] Fact-check sign-off: All claims verified against `research/{args.slug}/claims.md`
- [ ] No first-hand gameplay claims / no fabricated mechanics
- [ ] Visual & audio playback reviewed by human
- [ ] AI disclosure line verified in YouTube description
- [ ] Copyright clearance confirmed in `assets/clearance-log.md`
- [ ] **Final human approval** to upload manually to YouTube Studio
"""
    (export_dir / "checklist.md").write_text(checklist_md, encoding="utf-8")

    # 7. Real Automated QA Audit
    reviewer = VideoReviewerAgent(
        video_path=export_mp4,
        style_id="vox-paper-collage",
        beats_file=timeline_json,
        metadata_file=metadata_file,
    )
    reviewer.inspect_technical()
    reviewer.inspect_audio_loudness()
    reviewer.extract_and_verify_motion()
    reviewer.inspect_compliance()
    passed, review_data, _ = reviewer.generate_review_report()

    manifest = {
        "slug": args.slug,
        "topic": args.title,
        "format": "short",
        "resolution": "1080x1920",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "style": {
            "id": "vox-paper-collage",
            "name": "Vox Paper Collage (Custom Cutouts)",
            "tokens": {"bg": "#F3EBD8", "surface": "#FAF6EC", "border": "#141413", "text": "#141413", "muted": "#4B5563", "accent": "#E6392E", "accent2": "#F7D046"},
        },
        "hook": timed_beats[0]["text"],
        "audio": {
            "duration": round(total_duration, 3),
            "engines": [f"chatterbox-{args.mode}", "tangoflux-sfx", "vox-editorial-bed"],
            "sfx_enabled": True,
            "beats_count": len(timed_beats),
        },
        "render": render_stats,
        "export_video": export_mp4.name,
        "qa_passed": passed,
        "qa_verdict": review_data["verdict"],
        "human_approved": False,
    }
    (export_dir / "project.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"=== COMPLETE: {export_mp4} | QA: {review_data['verdict']} | LUFS: {review_data['metrics'].get('loudness_lufs')} ===", flush=True)


if __name__ == "__main__":
    main()
