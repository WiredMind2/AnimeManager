# Docker production stack



Production self-hosting for AnimeManager: **3 app services** plus a shared observability stack.



| Service | Role | Host port |

|---------|------|-----------|

| `web` | Next.js UI + `/backend` proxy | `127.0.0.1:${WEB_PORT:-3000}` |

| `backend` | FastAPI + FFmpeg playback | internal `8081` |

| `torrent` | LibTorrent daemon (independent lifecycle) | internal `8090` |



Telemetry (Elasticsearch, Kibana, OTLP collector) runs in the separate **[tetrazero-observability](https://github.com/WiredMind2/tetrazero-observability)** repo on Docker network `tetrazero-observability`.



## Prerequisites



- Docker Engine + Compose v2

- **≥ 4 GB RAM** if running the observability stack on the same host

- [tetrazero-observability](https://github.com/WiredMind2/tetrazero-observability) cloned as a sibling directory (or set `TETRAZERO_OBSERVABILITY_PATH`)



## Quick start



```powershell

# 1. Start shared observability stack

.\scripts\start-elastic-stack.ps1



# 2. Start AnimeManager

Copy-Item .env.docker.example .env

docker compose up -d --build

```



- App UI: http://localhost:3000

- Kibana: http://127.0.0.1:5601 (`elastic` / `elastic`)



Install AnimeManager dashboards after Kibana is healthy:



```powershell

.\scripts\install-kibana-dashboards.ps1

```



## Volumes



| Mount | Services | Purpose |

|-------|----------|---------|

| `animemanager-data` → `/srv/Anime Manager` | `backend` | Settings, SQLite DB, cache, logs |

| `${LIBRARY_PATH}` → `/data` | `backend`, `torrent` | Anime library, downloads, `.libtorrent_resume` |



## Restart semantics



| Command | Torrent downloads | Notes |

|---------|-------------------|-------|

| `docker compose restart backend` | **Continue** | Backend reconnects to torrent daemon |

| `docker compose restart web` | Continue | UI-only restart |

| `docker compose restart torrent` | Brief pause | Resumes from `/data/.libtorrent_resume` |

| Observability stack restart | Continue | Brief telemetry gap; apps reconnect via shared network |



## Environment



Copy [`.env.docker.example`](../.env.docker.example) to `.env`. Key variables:



- `APP_URL` — public browser origin (default `http://localhost:3000`)
- **tetrazero production:** copy [`.env.docker.tetrazero.example`](../.env.docker.tetrazero.example) → `.env` on the server (`APP_URL=https://anime.tetrazero.com`, `WEB_PORT=3010`, `SENTRY_ENVIRONMENT=production`)

- `LIBRARY_PATH` — host path for anime files

- `LIBTORRENT_DAEMON_TOKEN` — shared secret for internal torrent API

- `OTEL_EXPORTER_OTLP_ENDPOINT` — default `http://otel-collector:4318` (requires observability stack)



## Architecture



```

Browser → web:3000 → backend:8081 → torrent:8090 (LibTorrent)

                  ↘ network tetrazero-observability → otel-collector → ES → Kibana

```



The torrent daemon owns the libtorrent session. The backend uses `LIBTORRENT_DAEMON_URL` and the `LibTorrentRemote` adapter so backend restarts do not kill active downloads.



## Public access (Caddy + Cloudflare Access)



See [`setup-cloudflare-access.md`](setup-cloudflare-access.md). Kibana is served from **tetrazero-observability** at `observability.tetrazero.com`.



## Troubleshooting



| Symptom | Fix |

|---------|-----|

| Backend/web fail to export telemetry | Start tetrazero-observability first; verify network exists: `docker network inspect tetrazero-observability` |

| Backend unhealthy | Check `docker compose logs torrent` — daemon must be healthy first |

| No data in Kibana | Exercise the UI; confirm OTLP endpoint and observability stack health |

| Port conflicts | Change `WEB_PORT` or ports in tetrazero-observability `.env` |



## Files



| File | Purpose |

|------|---------|

| [`docker-compose.yml`](../docker-compose.yml) | App services (joins external observability network) |

| [`observability/dashboards/`](../observability/dashboards/) | AnimeManager Kibana dashboard bundle |

| [`docker/settings.docker.json`](settings.docker.json) | First-run settings seed |


