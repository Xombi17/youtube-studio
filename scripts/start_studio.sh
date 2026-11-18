#!/usr/bin/env bash
# Launch CreatorRadar Studio Engine API (:8080) + Next.js Studio UI (:3000)
# Pass --with-voicestudio to also start the local VoiceStudio CUDA backend (:3900).

set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PIDS=()
cleanup() {
  echo ""
  echo "Stopping CreatorRadar Studio services..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

if [[ "$1" == "--with-voicestudio" ]]; then
  if [ -x "$ROOT/VoiceStudio/.venv/bin/uvicorn" ]; then
    echo "Starting VoiceStudio CUDA API on http://127.0.0.1:3900..."
    (cd "$ROOT/VoiceStudio" && .venv/bin/uvicorn main:app --app-dir backend --host 127.0.0.1 --port 3900) &
    PIDS+=($!)
  else
    echo "VoiceStudio .venv not found; run ./setup.sh first. Continuing with Edge-TTS fallback."
  fi
fi

PYTHON_BIN="$ROOT/.venv/bin/python"
[ -x "$PYTHON_BIN" ] || PYTHON_BIN="python3"

echo "Starting Studio Engine API on http://127.0.0.1:8080..."
"$PYTHON_BIN" "$ROOT/dashboard/app.py" &
PIDS+=($!)

echo "Starting Next.js Studio UI on http://localhost:3000..."
(cd "$ROOT/dashboard-next" && npm run dev) &
PIDS+=($!)

wait
