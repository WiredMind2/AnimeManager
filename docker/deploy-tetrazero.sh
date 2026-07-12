#!/bin/bash
set -euo pipefail
DEPLOY_DIR=/home/william/AnimeManager
mkdir -p "$DEPLOY_DIR"
tar -xzf /home/william/animemanager-deploy.tgz -C "$DEPLOY_DIR"
cd "$DEPLOY_DIR"
if [ ! -f .env ]; then
  mkdir -p /home/william/data/anime-library/Animes /home/william/data/anime-library/Downloads
  cat > .env <<EOF
# --- Production (tetrazero) ---
APP_URL=https://anime.tetrazero.com
WEB_PORT=3010
LIBRARY_PATH=/home/william/data/anime-library
ANIMEMANAGER_APPDATA=/srv/Anime Manager
LIBTORRENT_DAEMON_TOKEN=$(openssl rand -hex 32)
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1
SENTRY_PROFILE_SESSION_SAMPLE_RATE=0
NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE=0.1

# --- Telemetry (shared tetrazero-observability stack) ---
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
OTEL_METRICS_EXPORT_INTERVAL_MS=15000
OTEL_LOG_LEVEL=INFO
EOF
fi
docker compose up -d --build
