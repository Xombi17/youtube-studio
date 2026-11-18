#!/usr/bin/env bash
# ==============================================================================
# ClipSurge / CreatorRadar — Automated 24/7 AWS EC2 Production Service Setup
# Configures:
#   1. System dependencies & Redis
#   2. Python 3.12 virtual environment & production dependencies
#   3. Systemd unit: clipsurge-scout.service (Autonomous 24/7 stream clipper)
#   4. Systemd unit: clipsurge-publisher.service (Continuous auto-publish & delete agent)
#   5. Systemd unit: clipsurge-api.service (FastAPI studio backend)
# ==============================================================================

set -euo pipefail

APP_DIR="/home/ubuntu/youtube-studio"
VENV_DIR="$APP_DIR/.venv"
USER="ubuntu"

echo "=== [ClipSurge] Setting up 24/7 Cloud Production Services ==="

cd "$APP_DIR"

# 1. Ensure Redis is active
echo "--> Checking Redis service..."
sudo systemctl enable --now redis-server
redis-cli ping >/dev/null && echo "✅ Redis is online and responding PONG."

# 2. Python Virtual Environment
if [ ! -d "$VENV_DIR" ]; then
  echo "--> Creating virtual environment at $VENV_DIR..."
  python3 -m venv "$VENV_DIR"
fi

echo "--> Installing / updating Python dependencies..."
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r requirements.txt
"$VENV_DIR/bin/pip" install redis uvicorn fastapi gunicorn yt-dlp

# 3. Create Systemd Service: clipsurge-scout (Autonomous 24/7 live clipper)
echo "--> Registering clipsurge-scout.service..."
sudo tee /etc/systemd/system/clipsurge-scout.service > /dev/null <<EOF
[Unit]
Description=ClipSurge Autonomous 24/7 Live Stream Scout & Clipper Daemon
After=network.target redis-server.service
Requires=redis-server.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
EnvironmentFile=-$APP_DIR/.env
Environment=PYTHONUNBUFFERED=1
Environment=REDIS_HOST=localhost
Environment=REDIS_PORT=6379
ExecStart=$VENV_DIR/bin/python $APP_DIR/scripts/autonomous_scout_daemon.py --poll-interval 120 --asr whistle --max-parallel 2 --min-score 80 --privacy private
Restart=always
RestartSec=10
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

# 4. Create Systemd Service: clipsurge-publisher (Continuous auto-publish & delete agent)
echo "--> Registering clipsurge-publisher.service..."
sudo tee /etc/systemd/system/clipsurge-publisher.service > /dev/null <<EOF
[Unit]
Description=ClipSurge Autonomous 24/7 Video Publisher & Lifecycle Agent
After=network.target redis-server.service
Requires=redis-server.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
EnvironmentFile=-$APP_DIR/.env
Environment=PYTHONUNBUFFERED=1
Environment=REDIS_HOST=localhost
Environment=REDIS_PORT=6379
ExecStart=$VENV_DIR/bin/python $APP_DIR/scripts/publish_agent.py --daemon --interval 300 --clean-orphans
Restart=always
RestartSec=15
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

# 5. Create Systemd Service: clipsurge-api (FastAPI Studio Backend on port 8080)
echo "--> Registering clipsurge-api.service..."
sudo tee /etc/systemd/system/clipsurge-api.service > /dev/null <<EOF
[Unit]
Description=ClipSurge FastAPI Studio Backend Server
After=network.target redis-server.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
EnvironmentFile=-$APP_DIR/.env
Environment=PYTHONUNBUFFERED=1
Environment=PORT=8080
ExecStart=$VENV_DIR/bin/python -m uvicorn dashboard.app:app --host 0.0.0.0 --port 8080
Restart=always
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

# 6. Reload Systemd and Enable Services
echo "--> Reloading systemd daemons and enabling services..."
sudo systemctl daemon-reload
sudo systemctl enable clipsurge-scout.service
sudo systemctl enable clipsurge-publisher.service
sudo systemctl enable clipsurge-api.service

# 7. Start Services
echo "--> Starting ClipSurge production services..."
sudo systemctl restart clipsurge-api.service
sudo systemctl restart clipsurge-publisher.service
sudo systemctl restart clipsurge-scout.service

echo ""
echo "=== [ClipSurge] Production Services Deployed Successfully! ==="
echo "API Health:   http://localhost:8080/health"
echo "Check Status: sudo systemctl status clipsurge-scout clipsurge-publisher clipsurge-api"
