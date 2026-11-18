#!/usr/bin/env python3
"""
CreatorRadar Deterministic HTML5/GSAP Scene Renderer
Renders any studio.js / HyperFrames HTML composition frame-by-frame via headless Chrome
(Playwright) and pipes frames directly into FFmpeg with NVIDIA NVENC acceleration
(automatic fallback to libx264 on CPU-only machines).
"""

import argparse
import functools
import http.server
import os
import shutil
import socketserver
import subprocess
import sys
import threading
import time
from pathlib import Path


def detect_nvenc() -> bool:
    try:
        res = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if "h264_nvenc" not in res.stdout:
            return False
        # Verify NVENC actually initializes on the GPU
        probe = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.1",
                "-c:v", "h264_nvenc", "-f", "null", "-",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return probe.returncode == 0
    except Exception:
        return False


def find_browser_executable() -> str | None:
    env_path = os.environ.get("CHROME_PATH") or os.environ.get("CHROMIUM_PATH")
    if env_path and Path(env_path).exists():
        return env_path
    for candidate in (
        "google-chrome-stable",
        "google-chrome",
        "chromium",
        "chromium-browser",
    ):
        found = shutil.which(candidate)
        if found:
            return found
    return None


class _QuietHTTPHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def start_local_server(directory: Path):
    handler = functools.partial(_QuietHTTPHandler, directory=str(directory))
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, port


def build_ffmpeg_cmd(
    output_path: Path,
    fps: int,
    quality: str,
    codec: str,
    image_format: str = "jpeg",
) -> tuple[list[str], str]:
    use_nvenc = False
    if codec == "nvenc":
        use_nvenc = True
    elif codec == "auto":
        use_nvenc = detect_nvenc()

    vcodec_label = "h264_nvenc (GPU)" if use_nvenc else "libx264 (CPU)"

    cmd = [
        "ffmpeg", "-y",
        "-hide_banner", "-loglevel", "error",
        "-f", "image2pipe",
        "-vcodec", "mjpeg" if image_format == "jpeg" else "png",
        "-framerate", str(fps),
        "-i", "-",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
    ]

    if use_nvenc:
        cq_map = {"draft": "26", "standard": "21", "high": "18"}
        preset_map = {"draft": "p1", "standard": "p4", "high": "p5"}
        cmd += [
            "-c:v", "h264_nvenc",
            "-preset", preset_map.get(quality, "p4"),
            "-rc", "vbr",
            "-cq", cq_map.get(quality, "18"),
            "-b:v", "0",
        ]
    else:
        crf_map = {"draft": "26", "standard": "20", "high": "17"}
        preset_map = {"draft": "veryfast", "standard": "medium", "high": "slow"}
        cmd += [
            "-c:v", "libx264",
            "-preset", preset_map.get(quality, "medium"),
            "-crf", crf_map.get(quality, "18"),
        ]

    cmd.append(str(output_path))
    return cmd, vcodec_label


def render_scene(
    project_path: Path,
    output_path: Path,
    fps: int = 30,
    quality: str = "high",
    codec: str = "auto",
    width_override: int | None = None,
    height_override: int | None = None,
    duration_override: float | None = None,
    composition_id: str | None = None,
) -> dict:
    from playwright.sync_api import sync_playwright

    project_path = project_path.resolve()
    if project_path.is_file():
        serve_dir = project_path.parent
        html_name = project_path.name
    else:
        serve_dir = project_path
        html_name = "index.html"
        if not (serve_dir / html_name).exists():
            raise FileNotFoundError(f"index.html not found in {serve_dir}")

    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    httpd, port = start_local_server(serve_dir)
    url = f"http://127.0.0.1:{port}/{html_name}"
    browser_exe = find_browser_executable()

    # JPEG quality 95 is ~3x faster to pipe than PNG with virtually identical visual fidelity for H.264
    img_type = "png" if quality == "lossless" else "jpeg"
    jpeg_quality = 96 if quality == "high" else (90 if quality == "standard" else 82)

    t0 = time.time()
    try:
        with sync_playwright() as p:
            launch_kwargs = {
                "headless": True,
                "args": [
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--hide-scrollbars",
                    "--mute-audio",
                    "--autoplay-policy=no-user-gesture-required",
                    "--font-render-hinting=none",
                ],
            }
            if browser_exe:
                launch_kwargs["executable_path"] = browser_exe

            browser = p.chromium.launch(**launch_kwargs)
            context = browser.new_context(
                viewport={"width": width_override or 1080, "height": height_override or 1920},
                device_scale_factor=1,
            )
            page = context.new_page()

            page.goto(url, wait_until="networkidle", timeout=30000)

            # Wait for fonts and STUDIO timeline initialization
            page.evaluate("() => document.fonts ? document.fonts.ready : Promise.resolve()")
            meta = page.evaluate(
                """(compId) => {
                    const root = compId
                      ? document.querySelector(`[data-composition-id="${compId}"]`)
                      : document.querySelector('[data-composition-id]');
                    const id = root ? root.dataset.compositionId : 'main';
                    const width = root && root.dataset.width ? Number(root.dataset.width) : window.innerWidth;
                    const height = root && root.dataset.height ? Number(root.dataset.height) : window.innerHeight;
                    const duration = root && root.dataset.duration ? Number(root.dataset.duration) : 10;
                    const hasTimeline = Boolean(window.__timelines && window.__timelines[id]);
                    const hasRenderFn = typeof window.__studioRender === 'function';
                    return { id, width, height, duration, hasTimeline, hasRenderFn };
                }""",
                composition_id,
            )

            width = width_override or int(meta["width"])
            height = height_override or int(meta["height"])
            duration = duration_override or float(meta["duration"])
            comp_id = meta["id"]

            # Ensure even dimensions for yuv420p H.264
            width = width - (width % 2)
            height = height - (height % 2)
            page.set_viewport_size({"width": width, "height": height})

            total_frames = max(1, int(round(duration * fps)))
            ff_cmd, vcodec_label = build_ffmpeg_cmd(output_path, fps, quality, codec, image_format=img_type)

            print(
                f"[RenderEngine] {width}x{height} @ {fps}fps | {duration:.2f}s ({total_frames} frames) | "
                f"Encoder: {vcodec_label} | Browser: {browser_exe or 'playwright-chromium'}",
                flush=True,
            )

            ff_proc = subprocess.Popen(
                ff_cmd,
                stdin=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            # Force deterministic seeking without loop wrap on final frames
            page.evaluate("() => { window.STUDIO_NO_WRAP = true; }")

            shot_kwargs = {"type": img_type}
            if img_type == "jpeg":
                shot_kwargs["quality"] = jpeg_quality

            last_report = time.time()
            try:
                for frame_idx in range(total_frames):
                    t = frame_idx / fps
                    page.evaluate(
                        """([cid, tVal]) => {
                            const tl = window.__timelines && window.__timelines[cid];
                            if (tl) {
                                tl.time(tVal);
                            } else if (typeof window.__studioRender === 'function') {
                                window.__studioRender(tVal);
                            }
                        }""",
                        [comp_id, t],
                    )
                    frame_bytes = page.screenshot(**shot_kwargs)
                    ff_proc.stdin.write(frame_bytes)

                    now = time.time()
                    if now - last_report >= 2.0 or frame_idx == total_frames - 1:
                        pct = ((frame_idx + 1) / total_frames) * 100.0
                        rate = (frame_idx + 1) / max(0.01, now - t0)
                        print(
                            f"[RenderEngine] Frame {frame_idx + 1}/{total_frames} ({pct:.1f}%) — {rate:.1f} fps",
                            flush=True,
                        )
                        last_report = now
            finally:
                if ff_proc.stdin:
                    ff_proc.stdin.close()

            stderr_out = ff_proc.stderr.read().decode("utf-8", errors="replace") if ff_proc.stderr else ""
            ret = ff_proc.wait()
            browser.close()

            if ret != 0:
                raise RuntimeError(f"FFmpeg encoding failed (exit {ret}): {stderr_out}")

        elapsed = time.time() - t0
        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(
            f"[RenderEngine] Complete: {output_path.name} ({size_mb:.2f} MB) in {elapsed:.1f}s "
            f"({total_frames / max(0.01, elapsed):.1f} render fps)",
            flush=True,
        )
        return {
            "output": str(output_path),
            "width": width,
            "height": height,
            "fps": fps,
            "duration": duration,
            "frames": total_frames,
            "encoder": vcodec_label,
            "elapsed_sec": round(elapsed, 2),
            "size_bytes": output_path.stat().st_size,
        }
    finally:
        httpd.shutdown()
        httpd.server_close()


def main():
    parser = argparse.ArgumentParser(description="Render HTML5/GSAP studio.js scene to MP4 via Chrome + NVENC")
    parser.add_argument("project", help="Path to scene directory (containing index.html) or HTML file")
    parser.add_argument("output", help="Output MP4 file path")
    parser.add_argument("--fps", type=int, default=30, help="Frames per second (default: 30)")
    parser.add_argument("--quality", choices=["draft", "standard", "high", "lossless"], default="high")
    parser.add_argument("--codec", choices=["auto", "nvenc", "cpu"], default="auto")
    parser.add_argument("--width", type=int, default=None)
    parser.add_argument("--height", type=int, default=None)
    parser.add_argument("--duration", type=float, default=None)
    parser.add_argument("--composition-id", default=None)
    args = parser.parse_args()

    render_scene(
        project_path=Path(args.project),
        output_path=Path(args.output),
        fps=args.fps,
        quality=args.quality,
        codec=args.codec,
        width_override=args.width,
        height_override=args.height,
        duration_override=args.duration,
        composition_id=args.composition_id,
    )


if __name__ == "__main__":
    main()
