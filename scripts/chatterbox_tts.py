#!/usr/bin/env python3
"""
Chatterbox TTS Local Studio Wrapper (RTX 4060 CUDA)
ElevenLabs-style zero-shot voice cloning & expressive speech synthesis using
Resemble AI's Chatterbox / Chatterbox-Turbo inside external/chatterbox/.venv.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
CHATTERBOX_PY = WORKSPACE_ROOT / "external" / "chatterbox" / ".venv" / "bin" / "python"
DEFAULT_REF = WORKSPACE_ROOT / "assets" / "voices" / "creator_sample.wav"

BROADCAST_FILTER_CHAIN = (
    "highpass=f=75,"
    "equalizer=f=120:width_type=o:width=1.0:g=2.5,"
    "equalizer=f=350:width_type=o:width=1.5:g=-2.0,"
    "equalizer=f=4500:width_type=o:width=1.2:g=3.0,"
    "acompressor=threshold=-18dB:ratio=3.5:attack=15:release=100,"
    "loudnorm=I=-14:LRA=7:TP=-1.5"
)


def _run_in_chatterbox_env(args: argparse.Namespace):
    import torch
    import torchaudio as ta

    device = args.device
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"

    out_path = Path(args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    raw_out = out_path.with_suffix(".cb_raw.wav") if args.master else out_path

    ref_path = str(Path(args.ref).resolve()) if args.ref and Path(args.ref).exists() else None
    print(f"[Chatterbox] Mode={args.mode} | Device={device} | Ref={ref_path or 'default'}", flush=True)

    if args.mode == "turbo":
        from chatterbox.tts_turbo import ChatterboxTurboTTS

        model = ChatterboxTurboTTS.from_pretrained(device=device)
        kwargs = {}
        if ref_path:
            kwargs["audio_prompt_path"] = ref_path
        wav = model.generate(args.text, **kwargs)
    elif args.mode == "multilingual":
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS

        model = ChatterboxMultilingualTTS.from_pretrained(device=device)
        kwargs = {"language_id": args.lang}
        if ref_path:
            kwargs["audio_prompt_path"] = ref_path
        wav = model.generate(args.text, **kwargs)
    else:
        from chatterbox.tts import ChatterboxTTS

        model = ChatterboxTTS.from_pretrained(device=device)
        kwargs = {"exaggeration": args.exaggeration, "cfg_weight": args.cfg_weight}
        if ref_path:
            kwargs["audio_prompt_path"] = ref_path
        wav = model.generate(args.text, **kwargs)

    ta.save(str(raw_out), wav.cpu(), model.sr)

    if args.master:
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(raw_out),
                "-af", BROADCAST_FILTER_CHAIN,
                "-ar", "48000", "-ac", "2",
                str(out_path),
            ],
            check=True,
        )
        raw_out.unlink(missing_ok=True)

    print(f"[Chatterbox] Saved: {out_path}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Chatterbox TTS ElevenLabs-style local voice cloning")
    parser.add_argument("text", help="Text to synthesize (Turbo supports [laugh], [chuckle], [cough])")
    parser.add_argument("output", help="Output WAV path")
    parser.add_argument("--ref", default=str(DEFAULT_REF), help="Reference voice WAV for zero-shot cloning")
    parser.add_argument("--mode", choices=["turbo", "standard", "multilingual"], default="turbo")
    parser.add_argument("--lang", default="en", help="Language code for multilingual mode (e.g. en, hi)")
    parser.add_argument("--exaggeration", type=float, default=0.55, help="Emotion intensity (standard mode)")
    parser.add_argument("--cfg-weight", type=float, default=0.5, help="Pacing/CFG weight (standard mode)")
    parser.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    parser.add_argument("--no-master", dest="master", action="store_false", help="Skip -14 LUFS broadcast mastering")
    parser.set_defaults(master=True)
    args = parser.parse_args()

    # Re-exec inside external/chatterbox/.venv automatically if invoked from system/studio python
    if CHATTERBOX_PY.exists() and Path(sys.executable).resolve() != CHATTERBOX_PY.resolve():
        os.execv(str(CHATTERBOX_PY), [str(CHATTERBOX_PY), __file__, *sys.argv[1:]])

    _run_in_chatterbox_env(args)


if __name__ == "__main__":
    main()
