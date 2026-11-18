# CreatorRadar Studio Dashboard

CreatorRadar uses a unified two-layer dashboard architecture:

1. **Studio Engine API (`dashboard/app.py`)** — Local Python backend on `http://127.0.0.1:8080` exposing live GPU/NVENC telemetry, the 120-style catalog, `ideas-queue.md`, render job execution with streaming logs, QA review reports, voice recording/enrollment, Creator Tools (`hookscore.py` & `title.py`), and HTTP Range video streaming.
2. **Next.js Studio UI (`dashboard-next/`)** — Modern React + TypeScript interface on `http://localhost:3000` (proxies `/api/*` and `/media/*` to `:8080`).
3. **Terminal CLI (`dashboard/radar.py`)** — Fast CLI summary of skills, YPP status, ideas queue, and GTA VI verified facts.

## Start Both Services
```bash
./scripts/start_studio.sh
```
