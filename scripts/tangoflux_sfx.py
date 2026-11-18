#!/usr/bin/env python3
"""
TangoFlux Local SFX Generator (RTX 4060 CUDA)
Generates 44.1 kHz stereo sound effects & foley (1-30s) from text prompts
using declare-lab/TangoFlux inside external/TangoFlux/.venv.
"""

import argparse
import os
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
TANGO_PY = WORKSPACE_ROOT / "external" / "TangoFlux" / ".venv" / "bin" / "python"


def _run_in_tango_env(args: argparse.Namespace):
    import torch
    import torchaudio
    from tangoflux import TangoFluxInference

    device = "cuda" if torch.cuda.is_available() and args.device != "cpu" else "cpu"
    out_path = Path(args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    duration = max(1, min(30, int(round(args.duration))))
    print(f"[TangoFlux] Prompt='{args.prompt}' | {duration}s | steps={args.steps} | device={device}", flush=True)
    model = TangoFluxInference(name="declare-lab/TangoFlux", device=device)
    # Keep 8 GB VRAM GPUs safe by decoding VAE latents on CPU inside inference_mode
    if device == "cuda":
        model.vae = model.vae.to("cpu")
        with torch.inference_mode():
            latents = model.model.inference_flow(args.prompt, duration=duration, num_inference_steps=args.steps)
            wave = model.vae.decode(latents.transpose(2, 1).to("cpu")).sample.cpu()[0]
        waveform_end = int(duration * model.vae.config.sampling_rate)
        audio = wave[:, :waveform_end]
    else:
        with torch.inference_mode():
            audio = model.generate(args.prompt, steps=args.steps, duration=duration).cpu()
    torchaudio.save(str(out_path), audio, 44100)
    print(f"[TangoFlux] Saved 44.1kHz stereo SFX: {out_path}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Generate custom 44.1kHz stereo SFX via TangoFlux")
    parser.add_argument("prompt", help="Sound effect description (e.g. 'Deep cinematic bass boom and metallic whoosh')")
    parser.add_argument("output", help="Output WAV path (e.g. assets/sfx/custom_whoosh.wav)")
    parser.add_argument("--duration", type=float, default=3.0, help="Duration in seconds (1-30, default: 3)")
    parser.add_argument("--steps", type=int, default=40, help="Diffusion steps (25=fast, 50=best quality)")
    parser.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    args = parser.parse_args()

    if TANGO_PY.exists() and Path(sys.executable).resolve() != TANGO_PY.resolve():
        os.execv(str(TANGO_PY), [str(TANGO_PY), __file__, *sys.argv[1:]])

    _run_in_tango_env(args)


if __name__ == "__main__":
    main()
