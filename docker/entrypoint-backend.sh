#!/bin/sh
set -eu

APP_DATA="${ANIMEMANAGER_APPDATA:-/srv/Anime Manager}"
SETTINGS="${APP_DATA}/settings.json"
SEED="/app/docker/settings.docker.json"

mkdir -p "${APP_DATA}" /data/Animes /data/Downloads

if [ ! -f "${SETTINGS}" ] && [ -f "${SEED}" ]; then
  cp "${SEED}" "${SETTINGS}"
fi

exec uvicorn clients.http.app:app \
  --host 0.0.0.0 \
  --port 8081 \
  --timeout-graceful-shutdown 8
