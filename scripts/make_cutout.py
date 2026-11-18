#!/usr/bin/env python3
"""
CreatorRadar Vox Paper Cutout Engine
Converts AI-generated illustrations (on clean light/solid backgrounds) into authentic
Vox-style transparent RGBA die-cut paper stickers with:
- Flood-fill background removal from borders (preserves interior white highlights!)
- Organic scissor/hand-torn jagged white paper margin around the silhouette
- Subtle scanned-paper texture grain
- Realistic soft offset drop shadow
"""

import argparse
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage


def make_paper_cutout(
    input_path: Path,
    output_path: Path,
    border_px: int = 18,
    jaggedness: float = 4.2,
    tolerance: int = 34,
    max_dim: int = 900,
    seed: int = 42,
) -> Path:
    img = Image.open(input_path).convert("RGBA")

    # Resize down to crisp working resolution before masking
    w, h = img.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
        w, h = img.size

    arr = np.array(img, dtype=np.float32)
    rgb = arr[:, :, :3]

    # Sample border pixels to find exact background color (usually near-white)
    border_pixels = np.concatenate([
        rgb[0, :, :], rgb[-1, :, :], rgb[:, 0, :], rgb[:, -1, :]
    ], axis=0)
    bg_color = np.median(border_pixels, axis=0)

    # Color distance from background
    dist = np.linalg.norm(rgb - bg_color, axis=2)
    bg_candidate = dist < tolerance

    # Flood-fill ONLY regions connected to the outer edges (keeps white inside subject!)
    edge_seed = np.zeros_like(bg_candidate, dtype=bool)
    edge_seed[0, :] = bg_candidate[0, :]
    edge_seed[-1, :] = bg_candidate[-1, :]
    edge_seed[:, 0] = bg_candidate[:, 0]
    edge_seed[:, -1] = bg_candidate[:, -1]

    bg_mask = ndimage.binary_propagation(edge_seed, mask=bg_candidate)
    fg_mask = ~bg_mask

    # Clean tiny stray speckles and fill tiny pinholes inside foreground
    fg_mask = ndimage.binary_closing(fg_mask, iterations=2)
    fg_mask = ndimage.binary_opening(fg_mask, iterations=1)

    # Keep only significant connected components (>0.3% of image area)
    labeled, num = ndimage.label(fg_mask)
    if num > 1:
        sizes = ndimage.sum(fg_mask, labeled, range(1, num + 1))
        min_area = (w * h) * 0.003
        keep = np.zeros_like(fg_mask)
        for idx, sz in enumerate(sizes, start=1):
            if sz >= min_area:
                keep |= (labeled == idx)
        if keep.any():
            fg_mask = keep

    # Crop tightly to foreground bounding box with generous padding for paper border + shadow
    ys, xs = np.where(fg_mask)
    if len(ys) == 0:
        raise RuntimeError(f"Could not detect foreground subject in {input_path}")

    pad = border_px + 34
    y0, y1 = max(0, ys.min()), min(h, ys.max() + 1)
    x0, x1 = max(0, xs.min()), min(w, xs.max() + 1)

    fg_crop = fg_mask[y0:y1, x0:x1]
    rgb_crop = arr[y0:y1, x0:x1, :3].astype(np.uint8)

    ch, cw = fg_crop.shape
    out_w, out_h = cw + pad * 2, ch + pad * 2

    padded_fg = np.zeros((out_h, out_w), dtype=bool)
    padded_fg[pad:pad + ch, pad:pad + cw] = fg_crop

    padded_rgb = np.full((out_h, out_w, 3), 248, dtype=np.uint8)
    padded_rgb[pad:pad + ch, pad:pad + cw] = rgb_crop

    # Build organic hand-cut paper border using distance transform + low-frequency jagged noise
    dist_out = ndimage.distance_transform_edt(~padded_fg)

    rng = np.random.default_rng(seed)
    # Low-frequency smooth noise field so edges look scissor-cut / hand-torn, not pixelated
    noise_small = rng.normal(0.0, 1.0, size=(max(8, out_h // 14), max(8, out_w // 14)))
    noise_img = Image.fromarray(((noise_small - noise_small.min()) / max(1e-5, noise_small.max() - noise_small.min()) * 255).astype(np.uint8))
    noise_up = np.array(noise_img.resize((out_w, out_h), Image.Resampling.BICUBIC), dtype=np.float32) / 255.0 - 0.5
    wobble = noise_up * (jaggedness * 2.4)

    paper_mask = (dist_out + wobble) <= border_px
    # Slight smooth anti-aliasing on paper mask edge
    paper_alpha = Image.fromarray((paper_mask.astype(np.uint8) * 255)).filter(ImageFilter.GaussianBlur(radius=0.8))

    # Warm archival paper color (#F8F4EA) with subtle tactile fiber noise
    paper_grain = rng.integers(-6, 7, size=(out_h, out_w, 1), dtype=np.int16)
    paper_base = np.clip(np.array([248, 244, 234], dtype=np.int16) + paper_grain, 0, 255).astype(np.uint8)
    paper_layer = Image.fromarray(paper_base, mode="RGB").convert("RGBA")
    paper_layer.putalpha(paper_alpha)

    # Soft inner subject mask so subject sits cleanly on top of the white paper margin
    subj_alpha = Image.fromarray((padded_fg.astype(np.uint8) * 255)).filter(ImageFilter.GaussianBlur(radius=0.6))
    subj_layer = Image.fromarray(padded_rgb, mode="RGB").convert("RGBA")
    subj_layer.putalpha(subj_alpha)

    sticker = Image.alpha_composite(paper_layer, subj_layer)

    # Realistic directional paper drop shadow (offset right+down)
    shadow_alpha = paper_alpha.filter(ImageFilter.GaussianBlur(radius=10))
    shadow_arr = np.array(shadow_alpha, dtype=np.float32) * 0.42
    shadow_layer = Image.new("RGBA", (out_w, out_h), (12, 10, 8, 0))
    shadow_layer.putalpha(Image.fromarray(shadow_arr.astype(np.uint8)))

    final = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
    final.alpha_composite(shadow_layer, dest=(10, 14))
    final.alpha_composite(sticker, dest=(0, 0))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    final.save(output_path, "PNG")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Convert editorial illustrations to Vox die-cut paper stickers")
    parser.add_argument("input", help="Input image path")
    parser.add_argument("output", help="Output transparent PNG path")
    parser.add_argument("--border", type=int, default=18, help="White paper border thickness in px")
    parser.add_argument("--tolerance", type=int, default=34, help="Background color tolerance")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    out = make_paper_cutout(
        Path(args.input),
        Path(args.output),
        border_px=args.border,
        tolerance=args.tolerance,
        seed=args.seed,
    )
    print(f"[CutoutEngine] Saved transparent paper sticker: {out}")


if __name__ == "__main__":
    main()
