# Dockerfile for CreatorRadar / ClipSurge 24/7 Cloud Deployment
FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Kolkata

# 1. Install system utilities, ffmpeg, streamlink, curl, git, nodejs
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    git \
    build-essential \
    pkg-config \
    ca-certificates \
    gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. Copy dependencies requirements
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir streamlink yt-dlp modal

# 3. Build Next.js Dashboard
COPY dashboard-next/package*.json ./dashboard-next/
RUN cd dashboard-next && npm ci --silent

# 4. Copy repo files
COPY . .

# 5. Build dashboard static / prod
RUN cd dashboard-next && npm run build

EXPOSE 3000 8080

CMD ["./scripts/start_studio.sh"]
