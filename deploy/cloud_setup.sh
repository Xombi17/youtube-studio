#!/usr/bin/env bash
# 1-Click Cloud Deployment for CreatorRadar / ClipSurge
# Compatible with Ubuntu 22.04 / 24.04 LTS (Hetzner, DigitalOcean, AWS, Oracle Cloud)

set -euo pipefail

echo "=========================================================="
echo " 🚀 Setting up ClipSurge 24/7 Studio on Cloud Server"
echo "=========================================================="

# 1. Update and install base dependencies
sudo apt-get update
sudo apt-get install -y \
    curl \
    git \
    ffmpeg \
    python3-pip \
    python3-venv \
    ca-certificates \
    gnupg \
    lsb-release

# 2. Install Docker & Docker Compose if missing
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    sudo mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    sudo usermod -aG docker "$USER" || true
fi

# 3. Build & start containers
echo "Starting ClipSurge Studio and 24/7 Autonomous Scout via Docker Compose..."
docker compose build
docker compose up -d

echo ""
echo "=========================================================="
echo " ✅ 24/7 Setup Complete!"
echo " • Web Dashboard:   http://<YOUR-SERVER-IP>:3000"
echo " • Studio API:      http://<YOUR-SERVER-IP>:8080"
echo " • Autonomous Scout: Running in background (logs: docker compose logs -f autonomous_clipper)"
echo " • Review & Publish: Handled automatically by GitHub Actions twice daily"
echo "=========================================================="
