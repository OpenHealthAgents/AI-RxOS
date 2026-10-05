$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$examplePath = Join-Path $repoRoot ".env.example"
$envPath = Join-Path $repoRoot ".env"

if (-not (Test-Path $examplePath)) {
    throw "Missing .env.example at $examplePath"
}

if (-not (Test-Path $envPath)) {
    Copy-Item $examplePath $envPath
}

$lines = Get-Content $envPath
$required = @{
    "POSTGRES_ADMIN_USER" = "ai_rxos";
    "POSTGRES_ADMIN_PASSWORD" = "changeme";
    "POSTGRES_APP_USER" = "ai_rxos_app";
    "POSTGRES_APP_PASSWORD" = "changeme_app";
    "DATABASE_URL" = "postgresql://ai_rxos_app:changeme_app@postgres:5432/ai_rxos";
}

$existing = @{}
foreach ($line in $lines) {
    if ($line -match '^\s*([^#=]+?)\s*=\s*(.*)\s*$') {
        $existing[$matches[1].Trim()] = $matches[2].Trim()
    }
}

foreach ($key in $required.Keys) {
    if (-not $existing.ContainsKey($key)) {
        $existing[$key] = $required[$key]
    }
}

if (-not $existing.ContainsKey("SEARCH_INTERNAL_TOKEN") -or [string]::IsNullOrWhiteSpace($existing["SEARCH_INTERNAL_TOKEN"])) {
    $existing["SEARCH_INTERNAL_TOKEN"] = [guid]::NewGuid().ToString("N")
}

$orderedKeys = @("POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_ADMIN_USER", "POSTGRES_ADMIN_PASSWORD", "POSTGRES_APP_USER", "POSTGRES_APP_PASSWORD", "DATABASE_URL", "SEARCH_INTERNAL_TOKEN")
$updatedLines = @()
foreach ($key in $orderedKeys) {
    if ($existing.ContainsKey($key)) {
        $updatedLines += "$key=$($existing[$key])"
        $existing.Remove($key)
    }
}

foreach ($key in ($existing.Keys | Sort-Object)) {
    $updatedLines += "$key=$($existing[$key])"
}

$updatedLines | Set-Content $envPath -Encoding UTF8

Write-Host "Local .env bootstrap complete; local runtime role and SEARCH_INTERNAL_TOKEN are configured for this repository only."
