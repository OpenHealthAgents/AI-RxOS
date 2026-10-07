# AI-RxOS Local Development Environment Setup Script (Windows PowerShell)
# Standardizes environment file, generates secure local tokens, installs dependencies.
$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  AI-RxOS / NeoZenome Local Development Setup (Windows)    " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$repoRoot = Split-Path -Parent $PSScriptRoot
$examplePath = Join-Path $repoRoot ".env.example"
$envPath = Join-Path $repoRoot ".env"

# 1. Verify Prerequisites
Write-Host "`n[1/5] Checking prerequisites..." -ForegroundColor Yellow
$missing = @()

if (-not (Get-Command "node" -ErrorAction SilentlyContinue)) { $missing += "Node.js (>= 20.0.0)" }
if (-not (Get-Command "pnpm" -ErrorAction SilentlyContinue)) { $missing += "pnpm (>= 9.0.0)" }
if (-not (Get-Command "python" -ErrorAction SilentlyContinue)) { $missing += "Python (>= 3.12)" }
if (-not (Get-Command "docker" -ErrorAction SilentlyContinue)) { $missing += "Docker / Docker Desktop" }

if ($missing.Count -gt 0) {
    Write-Warning "The following recommended prerequisites were not found in PATH:"
    foreach ($item in $missing) { Write-Warning "  - $item" }
} else {
    Write-Host "  All core toolchains detected." -ForegroundColor Green
}

# 2. Bootstrap .env from .env.example
Write-Host "`n[2/5] Configuring environment file (.env)..." -ForegroundColor Yellow
if (-not (Test-Path $examplePath)) {
    throw "Missing .env.example at $examplePath"
}

if (-not (Test-Path $envPath)) {
    Copy-Item $examplePath $envPath
    Write-Host "  Created .env from .env.example." -ForegroundColor Green
} else {
    Write-Host "  Existing .env found. Preserving existing values." -ForegroundColor Gray
}

# Ensure critical local development keys are populated with safe local defaults
$lines = Get-Content $envPath
$existing = @{}
foreach ($line in $lines) {
    if ($line -match '^\s*([^#=]+?)\s*=\s*(.*)\s*$') {
        $existing[$matches[1].Trim()] = $matches[2].Trim()
    }
}

$needsUpdate = $false

# Generate safe local tokens if blank
if (-not $existing.ContainsKey("SEARCH_INTERNAL_TOKEN") -or [string]::IsNullOrWhiteSpace($existing["SEARCH_INTERNAL_TOKEN"])) {
    $existing["SEARCH_INTERNAL_TOKEN"] = [guid]::NewGuid().ToString("N")
    $needsUpdate = $true
}

if (-not $existing.ContainsKey("JWT_SECRET") -or [string]::IsNullOrWhiteSpace($existing["JWT_SECRET"]) -or $existing["JWT_SECRET"] -eq "change_this_dev_secret_before_deploying") {
    $existing["JWT_SECRET"] = "dev_" + [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
    $needsUpdate = $true
}

if (-not $existing.ContainsKey("EXECUTION_PAYLOAD_KEY") -or [string]::IsNullOrWhiteSpace($existing["EXECUTION_PAYLOAD_KEY"])) {
    # Generate 32-byte base64 key
    $bytes = New-Object byte[] 32
    (New-Object Security.Cryptography.RNGCryptoServiceProvider).GetBytes($bytes)
    $existing["EXECUTION_PAYLOAD_KEY"] = [Convert]::ToBase64String($bytes)
    $needsUpdate = $true
}

if ($needsUpdate) {
    $updatedLines = @()
    foreach ($key in ($existing.Keys | Sort-Object)) {
        $updatedLines += "$key=$($existing[$key])"
    }
    $updatedLines | Set-Content $envPath -Encoding UTF8
    Write-Host "  Updated .env with generated local cryptographic development tokens." -ForegroundColor Green
}

# 3. Install Monorepo JS/TS Dependencies
Write-Host "`n[3/5] Installing Node/TypeScript dependencies via pnpm..." -ForegroundColor Yellow
if (Get-Command "pnpm" -ErrorAction SilentlyContinue) {
    & pnpm install
    Write-Host "  Node packages installed successfully." -ForegroundColor Green
} else {
    Write-Warning "  pnpm not found. Skipping pnpm install."
}

# 4. Check / Setup Python Virtual Environment
Write-Host "`n[4/5] Checking Python virtual environment..." -ForegroundColor Yellow
$venvDir = Join-Path $repoRoot ".venv"
if (Test-Path $venvDir) {
    Write-Host "  Existing .venv detected at $venvDir." -ForegroundColor Green
} else {
    Write-Host "  Creating virtual environment at $venvDir..." -ForegroundColor Gray
    & python -m venv $venvDir
    Write-Host "  Virtual environment created." -ForegroundColor Green
}

# 5. Final Verification
Write-Host "`n[5/5] Setup Complete!" -ForegroundColor Green
Write-Host "Next steps to start local development:" -ForegroundColor Cyan
Write-Host "  1. Start datastores:  docker compose up -d postgres redis neo4j opensearch" -ForegroundColor Gray
Write-Host "  2. Seed demo data:    powershell ./scripts/seed-db.ps1" -ForegroundColor Gray
Write-Host "  3. Start dev servers: pnpm dev" -ForegroundColor Gray
Write-Host "  OR use one command:   powershell ./scripts/dev-start.ps1`n" -ForegroundColor Cyan
