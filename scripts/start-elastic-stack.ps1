# Start the shared tetrazero-observability stack (sibling repo or clone).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$ObsRoot = if ($env:TETRAZERO_OBSERVABILITY_PATH) {
    $env:TETRAZERO_OBSERVABILITY_PATH
} else {
    Join-Path (Split-Path -Parent $Root) "tetrazero-observability"
}
$ComposeFile = Join-Path $ObsRoot "docker-compose.yml"

if (-not (Test-Path $ComposeFile)) {
    Write-Error @"
Compose file not found: $ComposeFile
Clone https://github.com/WiredMind2/tetrazero-observability or set TETRAZERO_OBSERVABILITY_PATH.
"@
}

Write-Host "Starting tetrazero-observability (Elasticsearch + Kibana + OTel Collector)..."
Push-Location $ObsRoot
try {
    docker compose up -d
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "Kibana:            http://127.0.0.1:5601  (elastic / elastic)"
Write-Host "OTLP HTTP intake:  http://127.0.0.1:4318"
Write-Host ""
Write-Host "Check status: docker compose -f $ComposeFile ps"
