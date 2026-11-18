# Offloading CreatorRadar GPUs to Modal (Free $30/mo Credits)

Run **Whisper Hinglish-Apex (CUDA)** and **FFmpeg GPU rendering** remotely on **Modal's serverless NVIDIA T4 GPUs** so your laptop stays cool, quiet, and uses ~0% GPU VRAM.

---

## Why Hybrid (Thin Laptop Ingest + Modal Serverless GPU) Works Best

- **YouTube Live & Chat (`pytchat` / `streamlink`)**: YouTube frequently blocks cloud datacenter IPs (`"Sign in to confirm you're not a bot"`). Running `ffmpeg -c copy` + `pytchat` on your residential IP uses only **~1% CPU and 0% GPU**.
- **Heavy AI & Rendering (Modal NVIDIA T4 GPU)**: Every 10s audio chunk (~300 KB WAV) is sent to Modal's **scale-to-zero T4 GPU** running `Oriserve/Whisper-Hindi2Hinglish-Apex`. Modal bills per second (~$0.59/hr while actively transcribing, **$0.00 when idle**), so Modal's **$30/month free Starter tier** covers dozens of hours of live clipping!

---

## 3-Step One-Time Setup (Takes ~2 Minutes)

### Step 1: Connect Your Free Modal Account
```bash
.venv/bin/modal setup
```
This opens your browser, lets you sign in with GitHub/Google on [modal.com](https://modal.com) (free $30/mo credits), and saves your token to `~/.modal.toml`.

### Step 2: Deploy the CreatorRadar GPU Worker to Modal
```bash
.venv/bin/modal deploy modal_workers/studio_gpu.py
```
First deploy caches `Oriserve/Whisper-Hindi2Hinglish-Apex` inside a persistent Modal Volume (`creatorradar-models`) so future starts take only a few seconds.

### Step 3: Select "Modal Cloud GPU" in the Dashboard (or CLI)
- **Web Dashboard (`http://localhost:3000`):** Under **Speech AI Engine**, pick **`Modal Cloud GPU (Free T4 — Zero Laptop GPU)`** and click **Start Live Clipper**.
- **CLI:**
  ```bash
  .venv/bin/python orchestration/live_clipper_agent.py \
    --url "https://www.youtube.com/watch?v=<LIVE_ID>" \
    --asr modal \
    --layout facecam-split \
    --facecam-pos top-right
  ```

### Verify Modal Connection Anytime
```bash
.venv/bin/modal run modal_workers/studio_gpu.py
```
