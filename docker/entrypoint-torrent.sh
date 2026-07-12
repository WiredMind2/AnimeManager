#!/bin/sh
set -eu

DATA_PATH="${LIBTORRENT_DATA_PATH:-/data}"
mkdir -p "${DATA_PATH}" "${DATA_PATH}/Animes" "${DATA_PATH}/Downloads"

exec uvicorn clients.torrent_daemon.app:app \
  --host 0.0.0.0 \
  --port 8090
