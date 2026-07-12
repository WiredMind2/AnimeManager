# AnimeManager observability artifacts



- **Runtime stack:** [tetrazero-observability](https://github.com/WiredMind2/tetrazero-observability) (Elasticsearch + Kibana + OTLP collector)

- **Dashboards:** [`dashboards/`](dashboards/) — import via `scripts/install-kibana-dashboards.ps1`



## Dashboards

Ten Kibana dashboards are generated from [`dashboards/build.py`](dashboards/build.py):

| Dashboard | Coverage |
|-----------|----------|
| `animemanager-overview` | Full-stack health: HTTP volume/latency/status, runtime gauges, download lifecycle, startup failures, client errors, web vitals |
| `animemanager-http-apm` | HTTP request throughput, status, latency, services, top/slowest routes |
| `animemanager-client-ux` | Browser errors, event dimensions, Core Web Vitals |
| `animemanager-database` | DB commits, queries, upserts, write-queue errors, upsert batch latency |
| `animemanager-ingestion` | Ingestion records collected/persisted, failed providers, latency, coordinator run gauges |
| `animemanager-startup` | Per-job duration/errors/commits, total startup time, failed vs total jobs |
| `animemanager-playback` | Playback sessions, active sessions, create/segment latency, FFmpeg started/failed, playback+FFmpeg spans |
| `animemanager-downloads` | Download queue/active, lifecycle (started/completed/failed), enqueue latency, active torrents, restore/reconcile ops |
| `animemanager-http-errors` | HTTP error trend, errors by status code, errors by exception class, slow requests, slow-request logs |
| `animemanager-catalog` | Catalog merge/identity/enrichment ops, anime writes by source, persisted vs errors, persist latency |

## Regenerating the bundle

```powershell
# Offline (no Kibana required) — writes dashboards/animemanager.ndjson directly:
.\.venv\Scripts\python.exe observability\dashboards\build.py --offline

# Round-trip through a running Kibana (creates objects, then exports the bundle):
.\.venv\Scripts\python.exe observability\dashboards\build.py --kibana-url http://127.0.0.1:5601
```

## Importing

```powershell
.\scripts\install-kibana-dashboards.ps1 -KibanaUrl http://127.0.0.1:5601
```

Local dev: `.\scripts\start-elastic-stack.ps1` (starts the sibling observability repo).



