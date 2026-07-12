param(
    [string]$KibanaUrl = "http://127.0.0.1:5601",
    [string]$Username = "elastic",
    [string]$Password = "elastic",
    [int]$TimeoutSeconds = 120,
    [string]$BundlePath = ""
)

# Install the versioned AnimeManager dashboards into the local Kibana instance.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

if (-not $BundlePath) {
    $BundlePath = Join-Path $Root "observability\dashboards\animemanager.ndjson"
}
$BundlePath = [IO.Path]::GetFullPath($BundlePath)
$KibanaUrl = $KibanaUrl.TrimEnd("/")

if (-not (Test-Path -LiteralPath $BundlePath -PathType Leaf)) {
    throw "Dashboard bundle not found: $BundlePath"
}

$tokenBytes = [Text.Encoding]::ASCII.GetBytes("${Username}:${Password}")
$headers = @{
    Authorization = "Basic $([Convert]::ToBase64String($tokenBytes))"
    "kbn-xsrf" = "true"
}

Write-Host "Waiting for Kibana at $KibanaUrl ..."
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$ready = $false
do {
    try {
        $status = Invoke-RestMethod `
            -Method Get `
            -Uri "$KibanaUrl/api/status" `
            -Headers $headers `
            -TimeoutSec 5
        if ($status.status.overall.level -eq "available") {
            $ready = $true
            break
        }
    }
    catch {
        # Kibana commonly refuses connections while its plugins initialize.
    }
    Start-Sleep -Seconds 2
} while ((Get-Date) -lt $deadline)

if (-not $ready) {
    throw "Kibana did not become available within $TimeoutSeconds seconds."
}

$curl = Get-Command curl.exe -ErrorAction SilentlyContinue
if (-not $curl) {
    throw "curl.exe is required to upload the Kibana NDJSON bundle."
}

Write-Host "Importing AnimeManager dashboards from $BundlePath ..."
$responseText = & $curl.Source `
    --silent `
    --show-error `
    --user "${Username}:${Password}" `
    --header "kbn-xsrf: true" `
    --form "file=@$BundlePath;type=application/x-ndjson" `
    "$KibanaUrl/api/saved_objects/_import?overwrite=true"

if ($LASTEXITCODE -ne 0) {
    throw "Kibana dashboard import request failed (curl exit $LASTEXITCODE)."
}

try {
    $response = $responseText | ConvertFrom-Json
}
catch {
    throw "Kibana returned an invalid import response: $responseText"
}

if (-not $response.success) {
    $details = $response.errors | ConvertTo-Json -Depth 10 -Compress
    throw "Kibana imported only part of the dashboard bundle: $details"
}

Write-Host ""
Write-Host "Imported $($response.successCount) saved objects successfully."
Write-Host "Dashboards:"
$dashboards = @(
    @{Id="animemanager-overview";        Name="Overview"},
    @{Id="animemanager-http-apm";        Name="HTTP & APM Health"},
    @{Id="animemanager-client-ux";       Name="Client UX & Errors"},
    @{Id="animemanager-database";        Name="Database & Persistence"},
    @{Id="animemanager-ingestion";       Name="Metadata Ingestion & Coordinator"},
    @{Id="animemanager-startup";         Name="Startup Jobs"},
    @{Id="animemanager-playback";        Name="Playback & Transcoding"},
    @{Id="animemanager-downloads";       Name="Downloads & Torrents"},
    @{Id="animemanager-http-errors";     Name="HTTP Errors & Slow Requests"},
    @{Id="animemanager-catalog";         Name="Catalog & Anime Writes"}
)
foreach ($d in $dashboards) {
    Write-Host ("  {0,-32} {1}/app/dashboards#/view/{2}" -f $d.Name, $KibanaUrl, $d.Id)
}
