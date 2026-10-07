# AI-RxOS One-Command Startup Script (Windows PowerShell)
# Launches data stores, initializes seeds, and boots the development workspace.
param(
    [ValidateSet("hybrid", "docker", "datastores")]
    [string]$Mode = "hybrid"
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  AI-RxOS / NeoZenome One-Command Developer Startup       " -ForegroundColor Cyan
Write-Host "  Selected Mode: $Mode                                    " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$repoRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $repoRoot ".env"

# 1. Environment Validation
if (-not (Test-Path $envPath)) {
    Write-Host "`n.env not found. Running dev-setup.ps1..." -ForegroundColor Yellow
    & powershell (Join-Path $PSScriptRoot "dev-setup.ps1")
}

# 2. Start Data Stores
Write-Host "`n[1/3] Booting core data stores (PostgreSQL, Redis, Neo4j, OpenSearch)..." -ForegroundColor Yellow
& docker compose up -d postgres redis neo4j opensearch

Write-Host "Waiting for database readiness..." -ForegroundColor Gray
Start-Sleep -Seconds 4

# 3. Mode Selection
if ($Mode -eq "datastores") {
    Write-Host "`nData stores are running! Ports:" -ForegroundColor Green
    Write-Host "  PostgreSQL: 15432" -ForegroundColor Gray
    Write-Host "  Neo4j:      7474 (browser) / 7687 (bolt)" -ForegroundColor Gray
    Write-Host "  Redis:      6379" -ForegroundColor Gray
    Write-Host "  OpenSearch: 9200" -ForegroundColor Gray
    exit 0
}

if ($Mode -eq "docker") {
    Write-Host "`n[2/3] Launching complete 18-service topology in Docker..." -ForegroundColor Yellow
    & docker compose up -d
    Write-Host "`nFull stack is up!" -ForegroundColor Green
    Write-Host "  Web Workspace:   http://localhost:3000" -ForegroundColor Cyan
    Write-Host "  Admin Console:   http://localhost:3001" -ForegroundColor Cyan
    Write-Host "  API Gateway:     http://localhost:8080" -ForegroundColor Cyan
    Write-Host "  AI Opportunity:  http://localhost:8090/docs" -ForegroundColor Cyan
    exit 0
}

if ($Mode -eq "hybrid") {
    Write-Host "`n[2/3] Running Database Seed & Verification..." -ForegroundColor Yellow
    try {
        & powershell (Join-Path $PSScriptRoot "seed-db.ps1")
    } catch {
        Write-Warning "Seed script notice: $_"
    }

    Write-Host "`n[3/3] Launching Next.js Decision Workspace & Frontends..." -ForegroundColor Yellow
    Write-Host "  Frontend will be live at: http://localhost:3000" -ForegroundColor Green
    Write-Host "  Admin console at:        http://localhost:3001" -ForegroundColor Green
    Write-Host "  Press Ctrl+C to terminate development servers.`n" -ForegroundColor Gray
    
    Push-Location $repoRoot
    & pnpm dev
    Pop-Location
}
