# 🌐 Deploying ClipSurge 24/7 in the Cloud

This guide explains how to deploy the entire clipping studio on a cloud server so it watches streams, cuts viral moments, auto-stages them as private drafts ($\ge 80$), and publishes the best ones via GitHub Actions **24 hours a day, 7 days a week — 100% autonomously**.

---

## 🏗️ Architecture Overview

```
                               ┌────────────────────────────────────────────────────────┐
                               │                    CLOUD VPS ($4-$6/mo)                │
                               │                                                        │
Twitch / YouTube Live Streams ─┼─► [Autonomous 24/7 Scout Daemon]                       │
                               │       │ Discovers creators live from watchlist         │
                               │       ▼                                                │
                               │   [Live Clipper Agent]                                 │
                               │       │ Ingests HLS & cuts vertical 9:16 Shorts        │
                               │       │                                                │
                               │       ├── (Heavy Whisper ASR) ──► Modal Free T4 GPU    │
                               │       │                           ($30/mo free credit) │
                               │       ▼                                                │
                               │   Score ≥ 80 + Human Review Gate                       │
                               │       │                                                │
                               │       ▼                                                │
                               │   Upload as PRIVATE YouTube Draft                      │
                               │   + Record in config/youtube_upload_history.json       │
                               │                                                        │
                               │   [Web Dashboard (Port 3000 / 8080)]                   │
                               │   Control & monitor live streams from anywhere         │
                               └─────────────────────────┬──────────────────────────────┘
                                                         │
                                                         ▼
                               ┌────────────────────────────────────────────────────────┐
                               │            GITHUB ACTIONS SCHEDULER                    │
                               │                                                        │
                               │   Twice Daily: 19:00 IST (Peak) & 10:00 IST (Morning)  │
                               │   • Checks staged private clips                        │
                               │   • POST verdict  ──► Flip to PUBLIC in peak window   │
                               │   • SKIP / MAYBE  ──► DELETE from YouTube & clean disk │
                               │   • Persists state back via ADMIN_TOKEN                │
                               └────────────────────────────────────────────────────────┘
```

---

## 💰 Recommended Hosting Options (Ultra Cost-Effective)

Since speech AI transcription is offloaded to **Modal's Free Tier NVIDIA T4 GPU ($30/mo free credits)**, the cloud server only handles HLS streaming and FFmpeg video slicing. You **do not** need an expensive $100/mo cloud GPU instance!

| Provider | Plan | Monthly Cost | Notes |
|----------|------|--------------|-------|
| **Oracle Cloud Always Free** | Ampere A1 (4 OCPU, 24 GB RAM) | **$0.00 / month** | 100% free forever, generous specs |
| **Hetzner Cloud** | CX22 (2 vCPU, 4 GB RAM) | **~€4.00 / month** | Fast European datacenters, very reliable |
| **DigitalOcean** | Basic Droplet (2 vCPU, 4 GB RAM) | **~$6-$12 / month** | 1-click Docker droplet available |

---

## 🚀 3-Step 24/7 Cloud Setup

### Step 1: Provision a Cloud Server & Clone the Repository
On your cloud server (Ubuntu 22.04 or 24.04 LTS):

```bash
# Clone the repository
git clone https://github.com/Xombi17/youtube-studio.git
cd youtube-studio
```

### Step 2: Copy Config & Environment Files
Copy your local `.env` and `config/` files to the cloud server (or run `./sync-secrets.sh` to sync credentials):

```bash
# Ensure your .env has your API keys:
cat << 'EOF' > .env
GROQ_API_KEY=your_groq_key
APINEX_API_KEY=your_apinex_key
EOF

# Ensure your YouTube token & client secret exist in config/:
# config/youtube_token_clipper.json
# config/youtube_client_secret_clipper.json
```

Connect your free Modal account on the server for GPU offloading:
```bash
python3 -m pip install modal
modal setup
modal deploy modal_workers/studio_gpu.py
```

### Step 3: Launch with 1 Command (Docker Compose)
Run the automated cloud setup script:

```bash
./deploy/cloud_setup.sh
```

Or run Docker Compose directly:
```bash
docker compose up -d --build
```

---

## ⚙️ What Runs Automatically 24/7

1. **Autonomous Scout Daemon (`clipsurge_autonomous_daemon`)**:
   - Continuously monitors creators in `config/live-stream-watchlist.json` (Twitch + YouTube).
   - Whenever an approved creator goes live, it starts clipping with `--auto-upload --auto-upload-min-score 80 --upload-privacy private`.
   - When the stream ends, it flushes clips and waits for the next live stream.

2. **Web Dashboard (`clipsurge_studio`)**:
   - Access the Next.js control panel from your browser at `http://<SERVER-IP>:3000`.
   - Engine API at `http://<SERVER-IP>:8080`.

3. **Scheduled Reviewer & Publisher**:
   - Runs on **GitHub Actions** twice daily (19:00 IST & 10:00 IST).
   - Reviews any private drafts staged by the 24/7 daemon, publishes the approved ones at the best time, and purges the rest.

---

## 📊 Managing the 24/7 Daemon

To view live logs:
```bash
docker compose logs -f autonomous_clipper
```

To stop or restart:
```bash
docker compose restart
docker compose down
```

To modify creators being monitored:
Edit `config/live-stream-watchlist.json` — the daemon automatically picks up changes!
